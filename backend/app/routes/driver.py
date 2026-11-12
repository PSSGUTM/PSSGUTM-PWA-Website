import os
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config, models, storage
from ..database import get_db
from ..models import ApprovalStatus, BookingStatus, EventStatus, Gender, Role, VehicleType
from ..security import get_current_user, rate_limit
from ..services import booking as svc
from .bookings import save_upload

router = APIRouter(prefix="/driver", tags=["driver"])

CAR_LAYOUTS = {5: "1,3", 7: "1,3,2"}  # bilangan seat kereta -> baris penumpang (dari hadapan)


class VehicleSubmit(BaseModel):
    name: str = Field(default="", max_length=60)            # cth: "Myvi Ali" (kosong = guna jenama)
    brand: str = Field(default="", max_length=40)           # JENAMA, cth Saga
    colour: str = Field(default="", max_length=30)          # WARNA, cth Silver
    plate_no: str = Field(min_length=1, max_length=20)
    vehicle_type: VehicleType = VehicleType.car
    seats: int = 5                                          # kaedah lama: kereta 5 atau 7 (diabaikan jika kind_id diberi)
    kind_id: int | None = None                              # jenis kenderaan (senarai diurus admin)
    available_days: str = Field(default="2,5", max_length=20)


def _names(data) -> tuple[str, str, str]:
    brand, colour = data.brand.strip(), data.colour.strip()
    name = data.name.strip() or brand
    if not name:
        raise HTTPException(400, "Isi jenama kenderaan (cth Saga)")
    return name, brand, colour


def _days_ok(days: str) -> str:
    parts = [p.strip() for p in days.split(",") if p.strip()]
    if not parts or any(len(p) != 1 or p not in "0123456" for p in parts):
        raise HTTPException(400, "Hari tak sah")
    return ",".join(sorted(set(parts)))


def layout_for(vehicle_type: VehicleType, seats: int) -> tuple[str, int]:
    if vehicle_type == VehicleType.motorcycle:
        return "1", 1
    if seats not in CAR_LAYOUTS:
        raise HTTPException(400, "Kereta mestilah 5 atau 7 tempat duduk")
    rows = CAR_LAYOUTS[seats]
    return rows, sum(int(x) for x in rows.split(","))


def resolve_kind(db: Session, data) -> tuple[VehicleType, str, int, str]:
    """(jenis asas, susun atur seat, kapasiti, nama jenis) daripada jenis yang dipilih, atau kaedah lama."""
    if data.kind_id is not None:
        k = db.get(models.VehicleKind, data.kind_id)
        if k is None or not k.active:
            raise HTTPException(400, "Jenis kenderaan tak sah")
        return VehicleType(k.base), k.seat_rows, sum(int(x) for x in k.seat_rows.split(",")), k.name
    rows, cap = layout_for(data.vehicle_type, data.seats)
    return data.vehicle_type, rows, cap, ""


@router.get("/kinds")
def list_kinds(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": k.id, "name": k.name, "base": k.base, "seat_rows": k.seat_rows,
             "capacity": sum(int(x) for x in k.seat_rows.split(","))}
            for k in db.query(models.VehicleKind).filter_by(active=True).order_by(models.VehicleKind.id)]


def _payout_ok(u: models.User) -> bool:
    return bool(u.payout_qr_file or u.payout_qr2_file or (u.payout_bank and u.payout_account_no))


def _out(db: Session, v: models.Vehicle):
    unav = {r.training_date for r in db.query(models.VehicleUnavailable).filter_by(vehicle_id=v.id)}
    upcoming = []
    for d, s in svc.upcoming_dates(db):
        if str(d.weekday()) not in v.available_days.split(","):
            continue
        ev = svc.event_on(db, d)
        pax = db.query(models.Booking).filter_by(vehicle_id=v.id, training_date=d,
                                                 status=BookingStatus.confirmed).count()
        upcoming.append({"training_date": d.isoformat(), "session_name": s.name,
                         "unavailable": d in unav, "event_status": ev.status.value if ev else "open",
                         "passenger_rows": pax})
    return {"id": v.id, "name": v.name, "brand": v.brand, "colour": v.colour, "desc": svc.vehicle_desc(v),
            "plate_no": v.plate_no, "vehicle_type": v.vehicle_type.value,
            "capacity": v.capacity, "seat_rows": v.seat_rows, "kind_name": v.kind_name or "", "available_days": v.available_days,
            "approval": v.approval.value, "active": v.active, "safety_confirmed": v.safety_confirmed,
            "category": svc.vehicle_category(db, v), "upcoming": upcoming}


@router.get("/vehicles")
def my_vehicles(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"payout_ok": _payout_ok(user), "gender": user.gender.value if user.gender else None,
            "vehicles": [_out(db, v) for v in db.query(models.Vehicle).filter_by(driver_id=user.id)
                         .order_by(models.Vehicle.id)]}


@router.post("/vehicles", status_code=201, dependencies=[Depends(rate_limit(10, 3600))])
def submit_vehicle(data: VehicleSubmit, user: models.User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if user.role == Role.admin:
        raise HTTPException(400, "Admin tambah kenderaan melalui Panel BKK")
    if user.gender not in (Gender.male, Gender.female):
        raise HTTPException(400, "Sila lengkapkan jantina dalam Tetapan dahulu (perlu untuk susunan tempat duduk)")
    if config.REQUIRE_LICENCE and (not user.licence_file or user.licence_expiry is None):
        raise HTTPException(400, "Sila muat naik gambar lesen dan tarikh tamat di Profil dahulu.")
    if db.query(models.Vehicle).filter_by(driver_id=user.id).count() >= 5:
        raise HTTPException(400, "Had 5 kenderaan seorang. Hubungi BKK jika perlu tambah.")
    vtype, rows, cap, kname = resolve_kind(db, data)
    name, brand, colour = _names(data)
    v = models.Vehicle(name=name, brand=brand, colour=colour, plate_no=data.plate_no.strip().upper(), driver_id=user.id,
                       vehicle_type=vtype, driver_gender=user.gender, seat_rows=rows, capacity=cap, kind_name=kname,
                       available_days=_days_ok(data.available_days), approval=ApprovalStatus.pending, active=True)
    db.add(v)
    for a in db.query(models.User).filter_by(role=Role.admin, active=True):
        svc._notify(db, a.id, "admin_alert", "Kenderaan baru menunggu kelulusan",
                    f"{user.name}: {v.name} ({v.plate_no}), {v.capacity} penumpang.")
    db.commit()
    return _out(db, v)


@router.put("/vehicles/{vid}")
def edit_vehicle(vid: int, data: VehicleSubmit, user: models.User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    v = db.get(models.Vehicle, vid)
    if v is None or v.driver_id != user.id:
        raise HTTPException(404, "Kenderaan tak jumpa")
    if v.approval == ApprovalStatus.approved:
        # Selepas diluluskan, driver hanya boleh ubah hari tersedia, jenama & warna; lain-lain melalui BKK
        v.available_days = _days_ok(data.available_days)
        v.brand, v.colour = data.brand.strip() or v.brand, data.colour.strip() or v.colour
        db.flush()
        for d, _ in svc.upcoming_dates(db):
            ev = svc.event_on(db, d)
            if ev and ev.status == EventStatus.open:
                svc.assign_vehicles(db, ev)
    else:
        vtype, rows, cap, kname = resolve_kind(db, data)
        v.name, v.brand, v.colour = _names(data)
        v.plate_no = data.plate_no.strip().upper()
        v.vehicle_type, v.seat_rows, v.capacity, v.kind_name = vtype, rows, cap, kname
        v.available_days = _days_ok(data.available_days)
        v.approval = ApprovalStatus.pending
    db.commit()
    return _out(db, v)


class SafetyIn(BaseModel):
    confirmed: bool


@router.post("/vehicles/{vid}/safety")
def set_safety(vid: int, data: SafetyIn, user: models.User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """Akuan keselamatan: lesen sah, insurans (dan helmet penumpang untuk motosikal). Boleh dibuat kemudian."""
    v = db.get(models.Vehicle, vid)
    if v is None or v.driver_id != user.id:
        raise HTTPException(404, "Kenderaan tak jumpa")
    v.safety_confirmed = data.confirmed
    db.commit()
    return _out(db, v)


class UnavailableIn(BaseModel):
    training_date: date
    unavailable: bool = True


@router.post("/vehicles/{vid}/unavailable")
def set_unavailable(vid: int, data: UnavailableIn, user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    v = db.get(models.Vehicle, vid)
    if v is None or v.driver_id != user.id:
        raise HTTPException(404, "Kenderaan tak jumpa")
    if data.training_date < svc.today_my():
        raise HTTPException(400, "Tarikh dah lepas")
    ev = svc.event_on(db, data.training_date)
    if data.unavailable and ev and ev.status == EventStatus.finalised:
        has_pax = db.query(models.Booking).filter_by(vehicle_id=v.id, training_date=data.training_date,
                                                     status=BookingStatus.confirmed).first()
        if has_pax:
            raise HTTPException(400, "Senarai dah disahkan dan ada penumpang. Sila hubungi BKK.")
    row = db.query(models.VehicleUnavailable).filter_by(vehicle_id=v.id, training_date=data.training_date).first()
    if data.unavailable and row is None:
        db.add(models.VehicleUnavailable(vehicle_id=v.id, training_date=data.training_date))
    elif not data.unavailable and row is not None:
        db.delete(row)
    db.flush()
    if ev and ev.status == EventStatus.open:
        svc.assign_vehicles(db, ev)
    db.commit()
    return _out(db, v)


@router.get("/manifest")
def my_manifest(training_date: date, user: models.User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Senarai penumpang untuk kenderaan milik driver ini (nama, telefon, checkpoint)."""
    if user.role not in (Role.driver, Role.admin):
        raise HTTPException(403, "Untuk driver sahaja")
    ids = {v.id for v in db.query(models.Vehicle).filter_by(driver_id=user.id)}
    return svc.manifest(db, training_date, vehicle_ids=ids, for_driver=user.role == Role.driver)


# ---- Maklumat bayaran driver (persatuan bayar driver; hanya admin & pemilik boleh lihat) ----

class PayoutIn(BaseModel):
    payout_bank: str = Field(default="", max_length=100)
    payout_account_no: str = Field(default="", max_length=50)
    payout_account_name: str = Field(default="", max_length=100)


def _payout_out(u: models.User):
    return {"payout_bank": u.payout_bank, "payout_account_no": u.payout_account_no,
            "payout_account_name": u.payout_account_name, "has_qr": bool(u.payout_qr_file),
            "has_qr2": bool(u.payout_qr2_file)}


@router.get("/payout")
def get_payout(user: models.User = Depends(get_current_user)):
    return _payout_out(user)


@router.put("/payout")
def put_payout(data: PayoutIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.payout_bank = data.payout_bank.strip()
    user.payout_account_no = data.payout_account_no.strip()
    user.payout_account_name = data.payout_account_name.strip()
    db.commit()
    return _payout_out(user)


def _qr_attr(slot: int) -> str:
    if slot not in (1, 2):
        raise HTTPException(400, "Slot QR tak sah")
    return "payout_qr_file" if slot == 1 else "payout_qr2_file"


@router.get("/payout-qr")
def get_payout_qr(slot: int = 1, user: models.User = Depends(get_current_user)):
    f = getattr(user, _qr_attr(slot))
    if not f:
        raise HTTPException(404, "Tiada QR")
    return storage.serve(f, "Fail QR hilang")


@router.delete("/payout-qr")
def delete_payout_qr(slot: int = 1, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    attr = _qr_attr(slot)
    storage.delete(getattr(user, attr))
    setattr(user, attr, None)
    db.commit()
    return _payout_out(user)


@router.delete("/payout-bank")
def delete_payout_bank(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.payout_bank = user.payout_account_no = user.payout_account_name = ""
    db.commit()
    return _payout_out(user)


@router.post("/payout-qr")
async def upload_payout_qr(slot: int = 1, file: UploadFile = File(...), user: models.User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    attr = _qr_attr(slot)
    old = getattr(user, attr)
    setattr(user, attr, await save_upload(file, prefix="payout_", images_only=True))
    db.commit()
    storage.delete(old)
    return _payout_out(user)


# ---- Dokumen prebet: lesen (wajib), insurans (pilihan) ----

def _docs_out(u: models.User):
    return {"has_licence": bool(u.licence_file), "licence_expiry": u.licence_expiry.isoformat() if u.licence_expiry else None,
            "has_insurance": bool(u.insurance_file), "passenger_ok": u.passenger_ok,
            "passenger_request": u.passenger_request}


@router.get("/docs")
def get_docs(user: models.User = Depends(get_current_user)):
    return _docs_out(user)


class LicenceExpiryIn(BaseModel):
    licence_expiry: date


@router.put("/docs/licence-expiry")
def put_licence_expiry(data: LicenceExpiryIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.licence_expiry = data.licence_expiry
    db.flush()
    svc.send_licence_reminders(db)
    db.commit()
    return _docs_out(user)


@router.post("/docs/licence")
async def upload_licence(file: UploadFile = File(...), user: models.User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    old = user.licence_file
    user.licence_file = await save_upload(file, prefix="licence_", images_only=True)
    db.commit()
    storage.delete(old)
    return _docs_out(user)


@router.get("/docs/licence")
def get_licence(user: models.User = Depends(get_current_user)):
    if not user.licence_file:
        raise HTTPException(404, "Tiada gambar lesen")
    return storage.serve(user.licence_file, "Fail hilang")


@router.post("/docs/insurance")
async def upload_insurance(file: UploadFile = File(...), user: models.User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    old = user.insurance_file
    user.insurance_file = await save_upload(file, prefix="insurance_", images_only=True)
    db.commit()
    storage.delete(old)
    return _docs_out(user)


@router.get("/docs/insurance")
def get_insurance(user: models.User = Depends(get_current_user)):
    if not user.insurance_file:
        raise HTTPException(404, "Tiada gambar insurans")
    return storage.serve(user.insurance_file, "Fail hilang")


@router.delete("/docs/insurance")
def delete_insurance(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    storage.delete(user.insurance_file)
    user.insurance_file = None
    db.commit()
    return _docs_out(user)


@router.post("/request-passenger")
def request_passenger(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Prebet mohon turut jadi penumpang. Perlu kelulusan admin."""
    if user.role != Role.driver:
        raise HTTPException(400, "Untuk akaun prebet sahaja")
    if user.passenger_ok:
        raise HTTPException(400, "Anda sudah dibenarkan menjadi penumpang")
    user.passenger_request = True
    for a in db.query(models.User).filter_by(role=Role.admin, active=True):
        svc._notify(db, a.id, "admin_alert", f"Permohonan jadi penumpang: {user.name}",
                    "Prebet ini mohon turut menempah sebagai penumpang. Luluskan di Admin > Lagi > Pengguna.",
                    severity="task", link="/admin?tab=more", ref=f"paxreq:{user.id}")
    db.commit()
    return _docs_out(user)


# ---- Kehadiran per tarikh ----

@router.get("/dates")
def prebet_dates(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.ensure_events(db)
    return svc.prebet_options(db, user)


class AvailIn(BaseModel):
    training_date: date
    available: bool
    vehicle_id: int | None = None      # kenderaan yang digunakan pada tarikh ini (jika ada lebih satu)


@router.put("/availability")
def put_availability(data: AvailIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.query(models.Vehicle).filter_by(driver_id=user.id, approval=ApprovalStatus.approved, active=True).first() is None:
        raise HTTPException(400, "Perlu sekurang-kurangnya satu kenderaan yang diluluskan dahulu")
    try:
        svc.set_availability(db, user, data.training_date, data.available, vehicle_id=data.vehicle_id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return svc.prebet_options(db, user)


class TickIn(BaseModel):
    training_date: date
    kind: str = Field(pattern="^(arrived|delivered)$")
    on: bool = True


@router.put("/tick")
def put_tick(data: TickIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Prebet tanda: 'arrived' = dah sampai tempat latihan; 'delivered' = dah hantar semua selepas latihan."""
    try:
        svc.set_tick(db, user, data.training_date, data.kind, data.on)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.commit()
    return svc.prebet_options(db, user)


# ---- Bayaran daripada bendahari ----

@router.get("/payouts")
def my_payouts(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Bayaran yang telah dibuat kepada saya (satu resit = satu bayaran, dengan pecahan tarikh)."""
    return svc.payout_history(db, driver_id=user.id, limit=60)


@router.get("/income")
def my_income(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pendapatan belum dibayar (baki yang akan dibayar bendahari) + kaedah bayaran semasa."""
    items = [i for i in svc.payout_items(db, driver_id=user.id)]
    mine = [{"training_date": i["date"].isoformat(), "vehicle": i["vehicle"], "amount": i["outstanding"],
             "period": i["period"], "deadline": i["deadline"].isoformat(), "overdue": i["overdue"]} for i in items]
    mode = svc.payout_mode(db)
    return {"mode": mode, "mode_label": svc.PAYOUT_MODES[mode], "pending": mine,
            "pending_total": round(sum(i["amount"] for i in mine), 2),
            "note": svc._carry_note(mine)}


def _my_payout(db: Session, user: models.User, pid: int) -> models.DriverPayout:
    """Bayaran prebet ini sahaja (ikut driver_id, atau pemilik kenderaan bagi data lama)."""
    r = db.get(models.DriverPayout, pid)
    if r is None:
        raise HTTPException(404, "Bayaran tak jumpa")
    owner = r.driver_id
    if owner is None and r.vehicle_id:
        v = db.get(models.Vehicle, r.vehicle_id)
        owner = v.driver_id if v else None
    if owner != user.id:
        raise HTTPException(404, "Bayaran tak jumpa")
    return r


@router.get("/payouts/{pid}/receipt")
def my_payout_receipt(pid: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _my_payout(db, user, pid)
    if not r.receipt_file:
        raise HTTPException(404, "Tiada resit")
    return storage.serve(r.receipt_file, "Fail hilang")


@router.post("/payouts/{pid}/received")
def payout_received(pid: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _my_payout(db, user, pid)
    group = db.query(models.DriverPayout).filter_by(batch=r.batch).all() if r.batch else [r]
    for g in group:
        g.received, g.received_at = True, svc.now_my()
        svc.resolve_warning(db, user.id, f"payout:{g.id}")
    for t in db.query(models.User).filter_by(is_treasurer=True, active=True):
        svc._notify(db, t.id, "payout", f"{user.short_name or user.name} sahkan terima bayaran",
                    f"RM{sum(g.amount for g in group):.2f} diterima.", r.training_date, severity="info", link="/bendahari")
    db.commit()
    return {"ok": True}
