import csv
import io
import os
import re
import secrets
from datetime import date, time, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
import zipfile

from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config, models, storage
from ..database import get_db
from ..models import ApprovalStatus, BookingStatus, Direction, EventStatus, Gender, PaymentStatus, Role, VehicleType
from ..security import hash_password, require_admin, require_staff
from ..services import booking as svc
from ..services.assign import can_add, parse_rows
from .bookings import PAY_KEYS, read_branding, read_settings, save_upload

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_staff)])


def _get(db, model, id_, msg="Tak jumpa"):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, msg)
    return obj


# ------------------------------------------------------------ dashboard & events

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    svc.ensure_events(db)
    today = svc.today_my()
    events = (db.query(models.TrainingEvent)
              .filter(models.TrainingEvent.training_date >= today,
                      models.TrainingEvent.training_date <= today + timedelta(days=config.GENERATE_DAYS_AHEAD))
              .order_by(models.TrainingEvent.training_date).all())
    return [svc.event_overview(db, ev) for ev in events]


@router.post("/generate")
def generate(db: Session = Depends(get_db)):
    return {"created": svc.generate_bookings(db), "reminders": svc.send_reminders(db),
            "auto_finalised": svc.auto_finalise(db), "safety_reminders": svc.send_safety_reminders(db),
            "prebet_notices": svc.send_prebet_notices(db), "licence_reminders": svc.send_licence_reminders(db),
            "arrears_reminders": svc.send_arrears_reminders(db),
            "tick_warnings": svc.send_tick_warnings(db)}


class VenueSet(BaseModel):
    venue_id: int | None = None


@router.put("/events/{eid}/venue")
def set_venue(eid: int, data: VenueSet, db: Session = Depends(get_db)):
    ev = _get(db, models.TrainingEvent, eid, "Latihan tak jumpa")
    if ev.status == EventStatus.cancelled:
        raise HTTPException(400, "Latihan ini dibatalkan")
    if data.venue_id is not None:
        _get(db, models.Venue, data.venue_id, "Tempat latihan tak jumpa")
    ev.venue_id = data.venue_id
    db.flush()
    svc.apply_venue(db, ev)
    db.commit()
    return svc.event_overview(db, ev)


@router.post("/events/{eid}/finalise")
def finalise(eid: int, db: Session = Depends(get_db)):
    ev = _get(db, models.TrainingEvent, eid, "Latihan tak jumpa")
    try:
        n = svc.finalise_event(db, ev)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"notified": n, "event": svc.event_overview(db, ev)}


@router.post("/events/{eid}/reactivate")
def reactivate(eid: int, db: Session = Depends(get_db), me: models.User = Depends(require_admin)):
    ev = _get(db, models.TrainingEvent, eid, "Latihan tak jumpa")
    try:
        r = svc.reactivate_event(db, ev)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {**r, "event": svc.event_overview(db, ev)}


@router.post("/events/{eid}/unfinalise")
def unfinalise(eid: int, db: Session = Depends(get_db), me: models.User = Depends(require_admin)):
    """Batalkan pengesahan senarai (admin). Admin masih boleh edit selepas disahkan, termasuk auto-sah."""
    ev = _get(db, models.TrainingEvent, eid, "Latihan tak jumpa")
    try:
        r = svc.unfinalise_event(db, ev)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {**r, "event": svc.event_overview(db, ev)}


@router.post("/events/{eid}/cancel")
def cancel_event(eid: int, db: Session = Depends(get_db)):
    ev = _get(db, models.TrainingEvent, eid, "Latihan tak jumpa")
    try:
        n = svc.cancel_event(db, ev)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"notified": n, "event": svc.event_overview(db, ev)}


@router.get("/events/{eid}/seatmap")
def event_seatmap(eid: int, db: Session = Depends(get_db)):
    ev = _get(db, models.TrainingEvent, eid, "Latihan tak jumpa")
    return svc.seat_map(db, ev)


class SeatMove(BaseModel):
    user_id: int
    vehicle_id: int | None = None      # null = keluarkan daripada kenderaan
    direction: Direction | None = None
    row: int | None = None
    col: int | None = None


@router.put("/events/{eid}/seat")
def move_seat(eid: int, data: SeatMove, db: Session = Depends(get_db)):
    """Susun kerusi manual (seret). Peraturan jantina/baris/motosikal tetap dikuatkuasakan."""
    ev = _get(db, models.TrainingEvent, eid, "Latihan tak jumpa")
    if ev.status == EventStatus.cancelled:
        raise HTTPException(400, "Latihan dibatalkan")
    user = _get(db, models.User, data.user_id, "Ahli tak jumpa")
    try:
        svc.move_seat(db, ev, user, data.vehicle_id, data.direction, data.row, data.col)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.commit()
    return svc.seat_map(db, ev)


@router.post("/events/{eid}/reassign")
def reassign(eid: int, db: Session = Depends(get_db)):
    """Susun semula kereta. Selepas disahkan: hanya isi ahli yang belum ada kereta."""
    ev = _get(db, models.TrainingEvent, eid, "Latihan tak jumpa")
    svc.assign_vehicles(db, ev)
    db.commit()
    return svc.event_overview(db, ev)


@router.get("/feedback")
def list_feedback(db: Session = Depends(get_db)):
    rows = (db.query(models.Feedback, models.User)
            .outerjoin(models.User, models.User.id == models.Feedback.user_id)
            .order_by(models.Feedback.created_at.desc()).limit(200).all())
    return [{"id": f.id, "kind": f.kind, "message": f.message, "status": f.status,
             "created_at": f.created_at.isoformat(),
             "from": {"name": u.name, "member_no": u.member_no} if u else None} for f, u in rows]


class FeedbackStatus(BaseModel):
    status: str = Field(pattern="^(baru|dibaca|selesai)$")


@router.put("/feedback/{fid}")
def set_feedback_status(fid: int, data: FeedbackStatus, db: Session = Depends(get_db)):
    f = _get(db, models.Feedback, fid, "Maklum balas tak jumpa")
    f.status = data.status
    db.commit()
    return {"ok": True}


@router.delete("/feedback/{fid}")
def delete_feedback(fid: int, db: Session = Depends(get_db)):
    db.delete(_get(db, models.Feedback, fid, "Maklum balas tak jumpa"))
    db.commit()
    return {"ok": True}


class EhailingIn(BaseModel):
    direction: str | None = Field(default=None, pattern="^(going|returning)$")
    note: str = Field(default="", max_length=250)
    user_ids: list[int] | None = None
    on: bool = True


@router.get("/events/{eid}/needs-transport")
def needs_transport(eid: int, db: Session = Depends(get_db)):
    ev = _get(db, models.TrainingEvent, eid, "Latihan tak jumpa")
    return svc.event_needs_transport(db, ev)


@router.post("/events/{eid}/ehailing")
def ehailing(eid: int, data: EhailingIn, db: Session = Depends(get_db)):
    """BKK tandakan penumpang tanpa kenderaan sebagai e-hailing (BKK yang tempah) dan maklumkan ahli."""
    ev = _get(db, models.TrainingEvent, eid, "Latihan tak jumpa")
    try:
        n = svc.set_ehailing(db, ev, data.on, data.direction, data.note.strip(), data.user_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"notified": n, "event": svc.event_overview(db, ev)}


@router.get("/passengers")
def passengers(training_date: date, db: Session = Depends(get_db)):
    rows = (db.query(models.Booking, models.User)
            .join(models.User, models.User.id == models.Booking.user_id)
            .filter(models.Booking.training_date == training_date)
            .order_by(models.User.name, models.Booking.direction).all())
    points = {p.id: p.name for p in db.query(models.PickupPoint)}
    vehicles = {v.id: v for v in db.query(models.Vehicle)}
    cols = {c.id: c for c in db.query(models.College)}
    colleges = {i: c.code for i, c in cols.items()}
    return [{"booking_id": b.id, "user_id": u.id, "name": u.name, "short_name": svc.short(u), "block": u.block or "",
             "phone": u.phone, "member_no": u.member_no,
             "category": cols[u.college_id].category if u.college_id in cols else None,
             "college": colleges.get(u.college_id), "gender": u.gender.value if u.gender else None,
             "direction": b.direction.value, "status": b.status.value,
             "checkpoint": svc.pickup_label(b, points), "pickup_place": b.pickup_place or "",
             "vehicle_id": b.vehicle_id,
             "vehicle": vehicles[b.vehicle_id].name if b.vehicle_id else None,
             "vehicle_type": vehicles[b.vehicle_id].vehicle_type.value if b.vehicle_id else None} for b, u in rows]


@router.get("/manifest")
def manifest(training_date: date, db: Session = Depends(get_db)):
    return svc.manifest(db, training_date)


class CancelUserIn(BaseModel):
    user_id: int
    training_date: date


@router.post("/bookings/cancel")
def cancel_user(data: CancelUserIn, db: Session = Depends(get_db)):
    user = _get(db, models.User, data.user_id, "Ahli tak jumpa")
    svc.cancel_user_trips(db, user, data.training_date)
    return {"ok": True}


class AssignIn(BaseModel):
    user_id: int
    training_date: date
    vehicle_id: int | None = None


@router.post("/bookings/assign")
def assign_manual(data: AssignIn, db: Session = Depends(get_db)):
    """Tetapkan kenderaan secara manual untuk seorang ahli (pergi + balik kenderaan yang sama).
    Peraturan seat ikut jantina dan motosikal tetap dikuatkuasakan."""
    rows = db.query(models.Booking).filter_by(user_id=data.user_id, training_date=data.training_date,
                                              status=BookingStatus.confirmed).all()
    if not rows:
        raise HTTPException(404, "Ahli tiada booking aktif pada tarikh ini")
    user = _get(db, models.User, data.user_id, "Ahli tak jumpa")
    if data.vehicle_id is not None:
        v = _get(db, models.Vehicle, data.vehicle_id, "Kenderaan tak jumpa")
        if v.approval != ApprovalStatus.approved or not v.active:
            raise HTTPException(400, "Kenderaan belum aktif/diluluskan")
        others = db.query(models.Booking).filter(
            models.Booking.vehicle_id == v.id, models.Booking.training_date == data.training_date,
            models.Booking.status == BookingStatus.confirmed, models.Booking.user_id != data.user_id).all()
        by_user = {}
        for b in others:
            by_user.setdefault(b.user_id, set()).add(b.direction.value)
        genders = {u.id: u.gender.value for u in db.query(models.User).filter(models.User.id.in_(list(by_user) or [0]))}
        current = [{"user_id": uid, "gender": genders.get(uid, "male"), "dirs": dirs} for uid, dirs in by_user.items()]
        cand = {"user_id": user.id, "gender": user.gender.value if user.gender else "male",
                "dirs": {b.direction.value for b in rows}}
        spec = {"id": v.id, "type": v.vehicle_type.value, "driver_gender": v.driver_gender.value,
                "rows": parse_rows(v.seat_rows)}
        if not can_add(spec, current, cand):
            raise HTTPException(400, f"{v.name} tak boleh terima ahli ini (penuh atau melanggar peraturan tempat duduk/jantina)")
    prev = rows[0].vehicle_id
    for b in rows:
        b.vehicle_id = data.vehicle_id
    db.flush()
    ev = svc.event_on(db, data.training_date)
    if ev:
        svc.refresh_fees(db, ev)
    if ev and ev.status == EventStatus.finalised and data.vehicle_id and data.vehicle_id != prev:
        svc._notify(db, data.user_id, "car", f"Kenderaan ditetapkan: {svc.fmt_date(data.training_date)}",
                    svc._car_text(db, db.get(models.Vehicle, data.vehicle_id)), data.training_date)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------ vehicles

class VehicleIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    brand: str = Field(default="", max_length=40)
    colour: str = Field(default="", max_length=30)
    plate_no: str = Field(default="", max_length=20)
    driver_id: int | None = None
    vehicle_type: VehicleType = VehicleType.car
    driver_gender: Gender | None = None       # wajib jika tiada driver dipilih
    seat_rows: str | None = None              # cth "1,3" (5 seat), "1,3,2" (7 seat). Kosong = ikut jenis
    available_days: str = "2,5"
    active: bool = True
    category: str = Field(default="", pattern="^(|dekat|jauh)$")   # "" = ikut kolej pemandu
    kind_id: int | None = None                # jenis kenderaan (jika diberi, ikut susun atur jenis itu)


def _vehicle_out(db, v):
    drv = db.get(models.User, v.driver_id) if v.driver_id else None
    zone, dcode = svc.vehicle_zone(db, v)
    return {"id": v.id, "name": v.name, "brand": v.brand, "colour": v.colour, "desc": svc.vehicle_desc(v),
            "plate_no": v.plate_no, "driver_id": v.driver_id, "driver_college": dcode, "zone": zone,
            "driver_name": drv.name if drv else None, "driver_phone": drv.phone if drv else None,
            "vehicle_type": v.vehicle_type.value, "driver_gender": v.driver_gender.value,
            "seat_rows": v.seat_rows, "capacity": v.capacity, "kind_name": v.kind_name or "", "available_days": v.available_days,
            "approval": v.approval.value, "active": v.active, "safety_confirmed": v.safety_confirmed,
            "category": v.category or "", "category_effective": svc.vehicle_category(db, v),
            "payout_ok": bool(drv and (drv.payout_qr_file or drv.payout_qr2_file or (drv.payout_bank and drv.payout_account_no)))}


def _apply_vehicle(db, v, data: VehicleIn):
    drv = _get(db, models.User, data.driver_id, "Driver tak jumpa") if data.driver_id else None
    gender = drv.gender if drv and drv.gender in (Gender.male, Gender.female) else data.driver_gender
    if gender not in (Gender.male, Gender.female):
        raise HTTPException(400, "Sila nyatakan jantina driver (perlu untuk susunan tempat duduk)")
    kind = None
    if data.kind_id is not None:
        kind = _get(db, models.VehicleKind, data.kind_id, "Jenis kenderaan tak jumpa")
        data.vehicle_type = VehicleType(kind.base)
        rows = kind.seat_rows
    elif data.vehicle_type == VehicleType.motorcycle:
        rows = "1"
    else:
        rows = (data.seat_rows or "1,3").strip()
        try:
            parse_rows(rows)
        except ValueError:
            raise HTTPException(400, "Susun atur seat tak sah. Guna format seperti 1,3 atau 1,3,2")
    if drv and drv.role == Role.member:
        drv.role, drv.passenger_ok = Role.driver, True  # sudah penumpang: kekal boleh menempah
    v.name, v.plate_no = data.name.strip(), data.plate_no.strip().upper()
    v.brand, v.colour = data.brand.strip(), data.colour.strip()
    v.driver_id, v.vehicle_type, v.driver_gender = data.driver_id, data.vehicle_type, gender
    v.seat_rows, v.capacity = rows, sum(parse_rows(rows))
    if kind is not None:
        v.kind_name = kind.name
    v.available_days, v.active = data.available_days, data.active
    v.category = data.category


class KindIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    base: str = Field(default="car", pattern="^(car|motorcycle)$")
    seat_rows: str = Field(default="1,3", max_length=20)   # cth "1,3" (5 seat), "1,2,2,2" (van)
    active: bool = True


def _kind_out(k):
    return {"id": k.id, "name": k.name, "base": k.base, "seat_rows": k.seat_rows,
            "capacity": sum(parse_rows(k.seat_rows)), "active": k.active}


def _kind_rows(data: KindIn) -> str:
    if data.base == "motorcycle":
        return "1"
    try:
        rows = parse_rows(data.seat_rows)
    except ValueError:
        raise HTTPException(400, "Susun atur seat tak sah. Guna format seperti 1,3 atau 1,2,2")
    if len(rows) > 6 or any(r > 6 for r in rows) or sum(rows) > 14:
        raise HTTPException(400, "Susun atur terlalu besar (maks 6 baris, 6 seat sebaris, 14 penumpang)")
    return ",".join(str(r) for r in rows)


@router.get("/vehicle-kinds")
def list_kinds(db: Session = Depends(get_db)):
    return [_kind_out(k) for k in db.query(models.VehicleKind).order_by(models.VehicleKind.id)]


@router.post("/vehicle-kinds", status_code=201)
def add_kind(data: KindIn, db: Session = Depends(get_db)):
    if db.query(models.VehicleKind).filter_by(name=data.name.strip()).first():
        raise HTTPException(400, "Nama jenis sudah ada")
    k = models.VehicleKind(name=data.name.strip(), base=data.base, seat_rows=_kind_rows(data), active=data.active)
    db.add(k)
    db.commit()
    return _kind_out(k)


@router.put("/vehicle-kinds/{kid}")
def edit_kind(kid: int, data: KindIn, db: Session = Depends(get_db)):
    """Ubah jenis tidak mengubah kenderaan yang sudah didaftar (mereka simpan susun atur masing-masing)."""
    k = _get(db, models.VehicleKind, kid, "Jenis tak jumpa")
    clash = db.query(models.VehicleKind).filter(models.VehicleKind.name == data.name.strip(), models.VehicleKind.id != kid).first()
    if clash:
        raise HTTPException(400, "Nama jenis sudah ada")
    k.name, k.base, k.seat_rows, k.active = data.name.strip(), data.base, _kind_rows(data), data.active
    db.commit()
    return _kind_out(k)


@router.delete("/vehicle-kinds/{kid}")
def delete_kind(kid: int, db: Session = Depends(get_db)):
    k = _get(db, models.VehicleKind, kid, "Jenis tak jumpa")
    if db.query(models.VehicleKind).count() <= 1:
        raise HTTPException(400, "Mesti ada sekurang-kurangnya satu jenis")
    db.delete(k)
    db.commit()
    return {"ok": True}


@router.get("/vehicles")
def list_vehicles(db: Session = Depends(get_db)):
    return [_vehicle_out(db, v) for v in db.query(models.Vehicle).order_by(models.Vehicle.approval, models.Vehicle.id)]


@router.post("/vehicles", status_code=201)
def add_vehicle(data: VehicleIn, db: Session = Depends(get_db)):
    """Admin isi sendiri: terus diluluskan."""
    v = models.Vehicle(approval=ApprovalStatus.approved)
    _apply_vehicle(db, v, data)
    db.add(v)
    db.flush()
    _reassign_open(db)
    db.commit()
    return _vehicle_out(db, v)


@router.put("/vehicles/{vid}")
def edit_vehicle(vid: int, data: VehicleIn, db: Session = Depends(get_db)):
    v = _get(db, models.Vehicle, vid, "Kenderaan tak jumpa")
    _apply_vehicle(db, v, data)
    db.flush()
    _reassign_open(db)
    db.commit()
    return _vehicle_out(db, v)


def _reassign_open(db):
    for d, _ in svc.upcoming_dates(db):
        ev = svc.event_on(db, d)
        if ev and ev.status == EventStatus.open:
            svc.assign_vehicles(db, ev)


@router.post("/vehicles/{vid}/approve")
def approve_vehicle(vid: int, db: Session = Depends(get_db)):
    v = _get(db, models.Vehicle, vid, "Kenderaan tak jumpa")
    v.approval = ApprovalStatus.approved
    if v.driver_id:
        drv = db.get(models.User, v.driver_id)
        if drv and drv.role == Role.member:
            drv.role, drv.passenger_ok = Role.driver, True
        svc._notify(db, v.driver_id, "driver", "Kenderaan anda diluluskan",
                    f"{v.name} kini aktif. Anda boleh lihat senarai penumpang di tab Driver.")
    db.flush()
    _reassign_open(db)
    db.commit()
    return _vehicle_out(db, v)


@router.post("/vehicles/{vid}/reject")
def reject_vehicle(vid: int, db: Session = Depends(get_db)):
    v = _get(db, models.Vehicle, vid, "Kenderaan tak jumpa")
    v.approval = ApprovalStatus.rejected
    if v.driver_id:
        svc._notify(db, v.driver_id, "driver", "Kenderaan tidak diluluskan",
                    "Semak maklumat dan hantar semula, atau hubungi BKK.")
    db.flush()
    _reassign_open(db)
    db.commit()
    return _vehicle_out(db, v)


@router.delete("/vehicles/{vid}")
def delete_vehicle(vid: int, me: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Padam kenderaan (cth spam). Jika sudah pernah digunakan, guna Nyahaktif/Tolak."""
    v = _get(db, models.Vehicle, vid, "Kenderaan tak jumpa")
    if db.query(models.Booking).filter_by(vehicle_id=v.id).first() or db.query(models.DriverPayout).filter_by(vehicle_id=v.id).first():
        raise HTTPException(400, "Kenderaan ini sudah digunakan. Guna 'Tolak' atau 'Nyahaktif' sahaja.")
    db.query(models.VehicleUnavailable).filter_by(vehicle_id=v.id).delete()
    db.delete(v)
    db.flush()
    _reassign_open(db)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------ users

@router.get("/users")
def users(db: Session = Depends(get_db)):
    colleges = {c.id: c.code for c in db.query(models.College)}
    points = {p.id: p.name for p in db.query(models.PickupPoint)}
    return [{"id": u.id, "name": u.name, "short_name": u.short_name, "block": u.block,
             "checkpoint": points.get(u.pickup_point_id, ""),
             "member_no": u.member_no, "phone": u.phone, "email": u.email,
             "role": u.role.value, "gender": u.gender.value if u.gender else None,
             "college_id": u.college_id, "college": colleges.get(u.college_id) or (u.college_other or None),
             "college_other": u.college_other,
             "credit_balance": u.credit_balance, "active": u.active, "is_treasurer": u.is_treasurer,
             "passenger_ok": u.passenger_ok, "passenger_request": u.passenger_request,
             "gender_request": u.gender_request or "", "prebet_request": u.prebet_request,
             "has_licence": bool(u.licence_file), "licence_expiry": u.licence_expiry.isoformat() if u.licence_expiry else None,
             "has_insurance": bool(u.insurance_file)}
            for u in db.query(models.User).order_by(models.User.name)]


class TreasurerIn(BaseModel):
    on: bool


@router.put("/users/{uid}/treasurer")
def set_treasurer(uid: int, data: TreasurerIn, me: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    u = _get(db, models.User, uid, "User tak jumpa")
    u.is_treasurer = data.on
    db.commit()
    return {"id": u.id, "is_treasurer": u.is_treasurer}


@router.delete("/users/{uid}")
def delete_user(uid: int, force: bool = False, me: models.User = Depends(require_admin),
                db: Session = Depends(get_db)):
    """Padam akaun. Biasa: hanya jika tiada tempahan/bayaran/kenderaan (cth akaun spam).
    force=true ('Padam paksa', untuk fasa ujian): buang SEMUA rekod akaun ini (tempahan, bayaran, kenderaan
    dan rekod bayar driver kenderaan itu). Tak boleh diundur."""
    u = _get(db, models.User, uid, "User tak jumpa")
    if u.id == me.id:
        raise HTTPException(400, "Tak boleh padam akaun sendiri")
    if u.role == Role.admin:
        raise HTTPException(400, "Turunkan peranan admin dahulu sebelum padam")
    vehicles = db.query(models.Vehicle).filter_by(driver_id=u.id).all()
    bookings = db.query(models.Booking).filter_by(user_id=u.id).all()
    has_history = bool(bookings or vehicles or db.query(models.Payment).filter_by(user_id=u.id).first())
    if has_history and not force:
        raise HTTPException(400, "Akaun ini ada tempahan/bayaran/kenderaan. Guna 'Nyahaktif', atau 'Padam paksa' "
                                 "untuk buang semua rekodnya (tak boleh diundur).")
    dates = {b.training_date for b in bookings}
    for v in vehicles:
        for ob in db.query(models.Booking).filter_by(vehicle_id=v.id).all():
            ob.vehicle_id = None          # penumpang lain disusun semula
            dates.add(ob.training_date)
        db.query(models.DriverPayout).filter_by(vehicle_id=v.id).delete()
        db.query(models.VehicleUnavailable).filter_by(vehicle_id=v.id).delete()
        db.delete(v)
    db.flush()
    db.query(models.Booking).filter_by(user_id=u.id).delete()
    db.query(models.Payment).filter_by(user_id=u.id).delete()
    db.query(models.Preference).filter_by(user_id=u.id).delete()
    db.query(models.Notification).filter_by(user_id=u.id).delete()
    db.query(models.Feedback).filter_by(user_id=u.id).delete()
    db.query(models.PasswordReset).filter_by(user_id=u.id).delete()
    db.delete(u)
    db.flush()
    if dates:
        for ev in db.query(models.TrainingEvent).filter(models.TrainingEvent.training_date.in_(dates)).all():
            if ev.status != EventStatus.cancelled:
                svc.assign_vehicles(db, ev)
    db.commit()
    return {"ok": True, "forced": has_history}


class RoleIn(BaseModel):
    role: Role


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Statistik keseluruhan: berapa ahli sah, berapa dah daftar, penumpang aktif, driver, ikut kolej."""
    all_users = db.query(models.User).all()
    users = [u for u in all_users if u.role != Role.admin]
    registered_nos = {u.member_no for u in all_users}
    roster = db.query(models.MemberRoster).filter_by(active=True).all()
    active_pref = {p.user_id for p in db.query(models.Preference).filter_by(active=True)}
    codes = {c.id: c.code for c in db.query(models.College).order_by(models.College.id)}
    by = {code: {"college": code, "registered": 0, "active_riders": 0} for code in codes.values()}
    other: dict[str, int] = {}
    for u in users:
        if u.college_id in codes:
            row = by[codes[u.college_id]]
            row["registered"] += 1
            row["active_riders"] += int(u.id in active_pref)
        elif u.college_other:
            other[u.college_other.strip()] = other.get(u.college_other.strip(), 0) + 1
    return {
        "roster_total": len(roster),
        "registered": len(users),
        "roster_not_registered": sum(1 for r in roster if r.member_no not in registered_nos),
        "male": sum(1 for u in users if u.gender == Gender.male),
        "female": sum(1 for u in users if u.gender == Gender.female),
        "active_riders": len(active_pref & {u.id for u in users}),
        "drivers": sum(1 for u in users if u.role == Role.driver),
        "vehicles_approved": db.query(models.Vehicle).filter_by(approval=ApprovalStatus.approved, active=True).count(),
        "vehicles_pending": db.query(models.Vehicle).filter_by(approval=ApprovalStatus.pending).count(),
        "by_college": [r for r in by.values() if r["registered"]],
        "other_colleges": [{"name": k, "count": v} for k, v in sorted(other.items())],
    }


@router.put("/users/{uid}/role")
def set_role(uid: int, data: RoleIn, me: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get(db, models.User, uid, "User tak jumpa")
    if u.id == me.id and data.role != Role.admin:
        raise HTTPException(400, "Tak boleh turunkan role diri sendiri")
    u.role = data.role
    db.commit()
    return {"id": u.id, "role": u.role.value}


@router.post("/users/{uid}/reset-password")
def reset_password(uid: int, db: Session = Depends(get_db)):
    """Tetapkan kata laluan sementara (dipaparkan sekali sahaja). Ahli tukar sendiri selepas login."""
    u = _get(db, models.User, uid, "User tak jumpa")
    temp = secrets.token_urlsafe(6)
    u.password_hash = hash_password(temp)
    db.commit()
    return {"temporary_password": temp}


class UserEdit(BaseModel):
    short_name: str | None = Field(default=None, max_length=40)
    block: str | None = Field(default=None, max_length=40)
    college_id: int | None = None
    gender: Gender | None = None
    active: bool | None = None


@router.put("/users/{uid}")
def edit_user(uid: int, data: UserEdit, me: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get(db, models.User, uid, "User tak jumpa")
    if data.active is False and u.id == me.id:
        raise HTTPException(400, "Tak boleh nyahaktifkan akaun sendiri")
    if data.college_id is not None:
        _get(db, models.College, data.college_id, "Kolej tak jumpa")
        u.college_id = data.college_id
        u.college_other = ""
    new_gender = data.gender if data.gender in (Gender.male, Gender.female) else None
    if data.short_name is not None:
        u.short_name = data.short_name.strip()
    if data.block is not None:
        u.block = data.block.strip()
    if data.active is not None:
        u.active = data.active
    db.commit()
    if new_gender is not None and new_gender != u.gender:
        svc.change_gender(db, u, new_gender, actor=me, how="(diubah admin)")
    svc.reconcile_user(db, u)
    return {"ok": True}


class GenderDecision(BaseModel):
    approve: bool


@router.put("/users/{uid}/prebet-request")
def decide_prebet(uid: int, data: GenderDecision, me: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Ahli yang ada kenderaan mohon jadi prebet: BKK lulus/tolak. Selepas lulus: peranan prebet, masih boleh tempah sebagai
    penumpang (admin boleh tarik balik kebenaran penumpang), dan perlu lengkapkan lesen + daftar kenderaan."""
    u = _get(db, models.User, uid, "User tak jumpa")
    if not u.prebet_request or u.role != Role.member:
        raise HTTPException(400, "Tiada permohonan jadi prebet")
    u.prebet_request = False
    if data.approve:
        u.role = Role.driver
        u.passenger_ok = True
        db.flush()
        svc._notify(db, u.id, "driver", "Anda kini prebet",
                    "BKK meluluskan permohonan anda. Muat naik gambar lesen dan tarikh tamat di Profil, kemudian daftar kenderaan di tab Driver. "
                    "Anda masih boleh menempah sebagai penumpang.", severity="task", link="/profil")
    else:
        svc._notify(db, u.id, "driver", "Permohonan jadi prebet ditolak", "Hubungi BKK jika ada pertanyaan.",
                    severity="info", link="/profil")
    db.commit()
    if data.approve:
        svc.reconcile_user(db, u)
    return {"ok": True}


@router.put("/users/{uid}/gender-request")
def decide_gender(uid: int, data: GenderDecision, me: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get(db, models.User, uid, "User tak jumpa")
    if not u.gender_request:
        raise HTTPException(400, "Tiada permohonan tukar jantina")
    new = Gender(u.gender_request)
    if data.approve:
        svc.change_gender(db, u, new, actor=me, how="(permohonan diluluskan)")
        svc._notify(db, u.id, "gender", "Jantina anda dikemas kini", "BKK meluluskan permohonan anda. Susunan tempat duduk disesuaikan.",
                    severity="info", link="/profil")
    else:
        u.gender_request = ""
        svc._notify(db, u.id, "gender", "Permohonan tukar jantina ditolak", "Hubungi BKK jika ada pertanyaan.",
                    severity="info", link="/profil")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------ payments

@router.get("/payments")
def payments(training_date: date | None = None, db: Session = Depends(get_db)):
    q = db.query(models.Payment, models.User).join(models.User, models.User.id == models.Payment.user_id)
    if training_date:
        q = q.filter(models.Payment.training_date == training_date)
    rows = q.order_by(models.Payment.training_date.desc(), models.User.name).limit(300).all()
    return [{"id": p.id, "name": u.name, "member_no": u.member_no, "training_date": p.training_date.isoformat(),
             "amount": p.amount, "due": svc.payment_due(p), "status": p.status.value,
             "has_receipt": bool(p.receipt_path)} for p, u in rows]


@router.get("/payments/{pid}/receipt")
def receipt(pid: int, db: Session = Depends(get_db)):
    p = _get(db, models.Payment, pid, "Bayaran tak jumpa")
    if not p.receipt_path:
        raise HTTPException(404, "Tiada resit")
    return storage.serve(p.receipt_path, "Fail resit hilang")


class VerifyIn(BaseModel):
    amount_paid: float | None = Field(default=None, ge=0, le=500)  # jumlah sebenar pada resit (kosong = tepat)


@router.post("/payments/{pid}/verify")
def verify(pid: int, data: VerifyIn | None = None, db: Session = Depends(get_db)):
    p = _get(db, models.Payment, pid, "Bayaran tak jumpa")
    if p.status != PaymentStatus.pending:
        raise HTTPException(400, "Hanya bayaran yang menunggu pengesahan (ada resit) boleh disahkan. Tiada bayaran tunai.")
    due = svc.payment_due(p)
    paid_amt = data.amount_paid if data and data.amount_paid is not None else due
    if paid_amt < due - 0.005:
        raise HTTPException(400, f"Jumlah pada resit (RM{paid_amt:.2f}) kurang daripada RM{due:.2f}. Tolak resit atau masukkan jumlah betul.")
    excess = round(paid_amt - due, 2)
    p.status = PaymentStatus.paid
    db.flush()
    user = db.get(models.User, p.user_id)
    if excess > 0:  # lebihan dibawa sebagai kredit untuk latihan seterusnya (tiada pemulangan tunai)
        user.credit_balance = round(user.credit_balance + excess, 2)
        svc._notify(db, p.user_id, "payment", "Lebihan bayaran disimpan sebagai kredit",
                    f"Anda bayar lebih RM{excess:.2f} untuk {svc.fmt_date(p.training_date)}. "
                    "Lebihan ini ditolak automatik daripada latihan seterusnya.", p.training_date)
    svc._sync_payment(db, user, p.training_date)  # kalau latihan dibatalkan sementara itu -> jadi kredit
    if p.status == PaymentStatus.paid:
        svc._notify(db, p.user_id, "payment", f"Bayaran {svc.fmt_date(p.training_date)} disahkan",
                    "Terima kasih!", p.training_date)
    db.commit()
    return {"id": p.id, "status": p.status.value}


@router.post("/payments/{pid}/reject")
def reject(pid: int, db: Session = Depends(get_db)):
    p = _get(db, models.Payment, pid, "Bayaran tak jumpa")
    if p.status != PaymentStatus.pending:
        raise HTTPException(400, "Hanya bayaran yang menunggu pengesahan boleh ditolak")
    p.status = PaymentStatus.rejected
    svc._notify(db, p.user_id, "payment", f"Resit {svc.fmt_date(p.training_date)} ditolak",
                "Sila upload semula resit yang jelas.", p.training_date)
    db.commit()
    return {"id": p.id, "status": p.status.value}


class PayInfoIn(BaseModel):
    pay_bank: str = Field(default="", max_length=100)
    pay_account_no: str = Field(default="", max_length=50)
    pay_account_name: str = Field(default="", max_length=100)
    pay_notes: str = Field(default="", max_length=400)


def _set_setting(db, key, value):
    s = db.get(models.Setting, key)
    if s is None:
        db.add(models.Setting(key=key, value=value))
    else:
        s.value = value


class RulesIn(BaseModel):
    text: str = Field(default="", max_length=6000)


@router.get("/settings/rules")
def get_rules_text(db: Session = Depends(get_db)):
    s = db.get(models.Setting, "rules_text")
    return {"text": s.value if s else ""}


@router.put("/settings/rules")
def put_rules_text(data: RulesIn, db: Session = Depends(get_db)):
    """Teks syarat penuh (satu baris = satu syarat). Kosong = guna syarat asal."""
    _set_setting(db, "rules_text", data.text.strip())
    db.commit()
    return {"text": data.text.strip()}


@router.get("/settings/payment")
def get_pay_settings(db: Session = Depends(get_db)):
    return read_settings(db)


@router.put("/settings/payment")
def put_pay_settings(data: PayInfoIn, db: Session = Depends(get_db)):
    for k in PAY_KEYS:
        _set_setting(db, k, getattr(data, k).strip())
    db.commit()
    return read_settings(db)


@router.post("/settings/payment-qr")
async def upload_qr(file: UploadFile = File(...), db: Session = Depends(get_db)):
    _set_setting(db, "pay_qr_file", await save_upload(file, prefix="qr_"))
    db.commit()
    return read_settings(db)


# ------------------------------------------------------------ bayar driver (persatuan = orang tengah)

@router.get("/payouts")
def payouts(training_date: date, db: Session = Depends(get_db)):
    return svc.payout_rows(db, training_date)


class PayoutMark(BaseModel):
    vehicle_id: int
    training_date: date


@router.post("/payouts")
def mark_paid_out(data: PayoutMark, db: Session = Depends(get_db)):
    """Tanda persatuan telah bayar driver (jumlah tertunggak semasa)."""
    row = next((r for r in svc.payout_rows(db, data.training_date) if r["vehicle_id"] == data.vehicle_id), None)
    if row is None:
        raise HTTPException(404, "Tiada rekod untuk kenderaan ini")
    if row["outstanding"] <= 0:
        raise HTTPException(400, "Tiada baki tertunggak untuk dibayar")
    db.add(models.DriverPayout(vehicle_id=data.vehicle_id, training_date=data.training_date,
                               amount=row["outstanding"]))
    v = db.get(models.Vehicle, data.vehicle_id)
    if v and v.driver_id:
        svc._notify(db, v.driver_id, "payout", f"Bayaran {svc.fmt_date(data.training_date)} telah dibuat",
                    f"Persatuan telah membayar RM{row['outstanding']:.2f} kepada anda.", data.training_date)
    db.commit()
    return {"ok": True, "amount": row["outstanding"]}


@router.get("/finance/drivers")
def finance_drivers(db: Session = Depends(get_db)):
    """Direktori bank/QR semua driver dan siapa pemiliknya (untuk bendahari & admin)."""
    vehicles = db.query(models.Vehicle).order_by(models.Vehicle.id).all()
    by_driver: dict[int, list] = {}
    for v in vehicles:
        if v.driver_id:
            by_driver.setdefault(v.driver_id, []).append(
                {"name": v.name, "plate_no": v.plate_no, "type": v.vehicle_type.value,
                 "approval": v.approval.value, "active": v.active})
    users = db.query(models.User).filter(models.User.id.in_(list(by_driver) or [0])).order_by(models.User.name)
    return [{"id": u.id, "name": u.name, "member_no": u.member_no, "phone": u.phone,
             "bank": u.payout_bank, "account_no": u.payout_account_no, "account_name": u.payout_account_name,
             "has_qr": bool(u.payout_qr_file), "has_qr2": bool(u.payout_qr2_file), "vehicles": by_driver[u.id]} for u in users]


@router.get("/drivers/{uid}/payout-qr")
def driver_qr(uid: int, slot: int = 1, db: Session = Depends(get_db)):
    u = _get(db, models.User, uid, "Driver tak jumpa")
    f = u.payout_qr_file if slot == 1 else u.payout_qr2_file
    if not f:
        raise HTTPException(404, "Tiada QR")
    return storage.serve(f, "Fail QR hilang")


# ------------------------------------------------------------ senarai ahli sah

class RosterIn(BaseModel):
    member_no: str = Field(min_length=3, max_length=30)
    name: str = Field(default="", max_length=120)
    gender: Gender | None = None
    college_code: str | None = None
    active: bool = True


def _roster_out(db, r, registered):
    col = db.get(models.College, r.college_id) if r.college_id else None
    return {"id": r.id, "member_no": r.member_no, "name": r.name,
            "gender": r.gender.value if r.gender else None, "college": col.code if col else None,
            "active": r.active, "registered": r.member_no in registered}


@router.get("/roster")
def roster(db: Session = Depends(get_db)):
    registered = {u.member_no for u in db.query(models.User)}
    return [_roster_out(db, r, registered) for r in db.query(models.MemberRoster).order_by(models.MemberRoster.member_no)]


def _upsert_roster(db, colleges, member_no, name, gender, college_code, active: bool | None = True):
    member_no = re.sub(r"\s+", "", (member_no or "")).upper()
    if not member_no:
        raise ValueError("No. ahli kosong")
    if not re.match(config.MEMBER_NO_PATTERN, member_no):
        raise ValueError(f"Format no. ahli tak sah: '{member_no}' (contoh betul: SG2627001)")
    g = None
    if gender:
        gl = str(gender).strip().lower()
        g = {"l": Gender.male, "lelaki": Gender.male, "male": Gender.male, "m": Gender.male,
             "p": Gender.female, "perempuan": Gender.female, "female": Gender.female, "f": Gender.female}.get(gl)
        if g is None:
            raise ValueError(f"Jantina tak dikenali: {gender}")
    col = None
    if college_code and str(college_code).strip():
        col = colleges.get(str(college_code).strip().upper())
        if col is None:
            raise ValueError(f"Kolej tak dikenali: {college_code}")
    r = db.query(models.MemberRoster).filter_by(member_no=member_no).first()
    created = r is None
    if created:
        r = models.MemberRoster(member_no=member_no)
        db.add(r)
    r.name = (name or "").strip() or r.name
    r.gender = g or r.gender
    r.college_id = col.id if col else r.college_id
    if created:
        r.active = True if active is None else active
    elif active is not None:
        r.active = active          # import CSV hantar None: ahli yang dinyahaktifkan kekal nyahaktif
    return created


@router.post("/roster", status_code=201)
def add_roster(data: RosterIn, db: Session = Depends(get_db)):
    colleges = {c.code.upper(): c for c in db.query(models.College)}
    try:
        _upsert_roster(db, colleges, data.member_no, data.name, data.gender.value if data.gender else None,
                       data.college_code, data.active)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"ok": True}


ROSTER_COLS = {
    "member_no": {"member_no", "no_ahli", "no ahli", "noahli", "nombor ahli", "no. ahli", "id"},
    "name": {"name", "nama"},
    "gender": {"gender", "jantina"},
    "college": {"college", "kolej", "college_code"},
}


@router.post("/roster/import")
async def import_roster(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import CSV (kolum: no ahli, nama, jantina, kolej). Hanya no. ahli wajib. Boleh diulang (kemas kini)."""
    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(413, "Fail terlalu besar (maks 2MB)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        raise HTTPException(400, "Fail kosong")
    header = [h.strip().lower() for h in rows[0]]
    idx = {k: next((i for i, h in enumerate(header) if h in names), None) for k, names in ROSTER_COLS.items()}
    if idx["member_no"] is None:
        raise HTTPException(400, "Kolum 'no ahli' tidak dijumpai dalam baris pertama (header)")
    colleges = {c.code.upper(): c for c in db.query(models.College)}
    added = updated = 0
    errors = []
    # No. ahli yang berulang dalam fail yang sama: SEMUA barisnya ditolak (data tak jelas), admin betulkan fail.
    seen_at: dict[str, list[int]] = {}
    for n, r in enumerate(rows[1:], start=2):
        raw = r[idx["member_no"]] if idx["member_no"] < len(r) else ""
        key = re.sub(r"\s+", "", raw).upper()
        if key:
            seen_at.setdefault(key, []).append(n)
    dupes = {k: v for k, v in seen_at.items() if len(v) > 1}
    for n, r in enumerate(rows[1:], start=2):
        get = lambda k: (r[idx[k]].strip() if idx[k] is not None and idx[k] < len(r) else "")
        key = re.sub(r"\s+", "", get("member_no")).upper()
        if key in dupes:
            errors.append(f"Baris {n}: no. ahli {key} berulang dalam fail (baris {', '.join(map(str, dupes[key]))}). Ditolak.")
            continue
        try:
            created = _upsert_roster(db, colleges, get("member_no"), get("name"), get("gender"), get("college"), active=None)
            added += created
            updated += (not created)
        except ValueError as e:
            errors.append(f"Baris {n}: {e}")
    db.commit()
    return {"added": added, "updated": updated, "errors": errors[:30], "error_count": len(errors)}


@router.put("/roster/{rid}")
def toggle_roster(rid: int, active: bool, db: Session = Depends(get_db)):
    r = _get(db, models.MemberRoster, rid, "Tak jumpa")
    r.active = active
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------ branding (logo, warna, nama)

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandingIn(BaseModel):
    brand_name: str = Field(min_length=1, max_length=60)
    brand_primary: str
    brand_accent: str
    contact_whatsapp: str = Field(default="60192278390", max_length=20)   # no. WhatsApp untuk masalah website
    contact_email: str = Field(default="", max_length=120)
    wa_group_link: str = Field(default="", max_length=200)               # pautan kumpulan WhatsApp BKK (e-hailing)


@router.put("/branding")
def put_branding(data: BrandingIn, db: Session = Depends(get_db)):
    if not (HEX.match(data.brand_primary) and HEX.match(data.brand_accent)):
        raise HTTPException(400, "Warna mesti format #rrggbb")
    wa = re.sub(r"\D", "", data.contact_whatsapp)
    if wa.startswith("0"):
        wa = "6" + wa
    if data.wa_group_link.strip() and not data.wa_group_link.strip().startswith("https://"):
        raise HTTPException(400, "Pautan kumpulan WhatsApp mesti bermula dengan https://")
    _set_setting(db, "contact_whatsapp", wa)
    for k in ("brand_name", "brand_primary", "brand_accent", "contact_email", "wa_group_link"):
        _set_setting(db, k, getattr(data, k).strip())
    db.commit()
    return read_branding(db)


@router.post("/branding/reset-colours")
def reset_branding_colours(db: Session = Depends(get_db)):
    """Padam warna jenama tersimpan supaya warna lalai (merah naga + emas) digunakan semula."""
    for k in ("brand_primary", "brand_accent"):
        row = db.get(models.Setting, k)
        if row is not None:
            db.delete(row)
    db.commit()
    return read_branding(db)


@router.post("/branding/logo")
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db)):
    _set_setting(db, "brand_logo_file", await save_upload(file, prefix="logo_", images_only=True))
    db.commit()
    return read_branding(db)


# ------------------------------------------------------------ announcements

class AnnounceIn(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    body: str = Field(default="", max_length=500)


@router.post("/announce", status_code=201)
def announce(data: AnnounceIn, db: Session = Depends(get_db)):
    svc._notify(db, None, "announcement", data.title.strip(), data.body.strip())
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------ reference data

class SessionIn(BaseModel):
    start_time: time
    end_time: time
    pickup_start: time
    pickup_end: time
    active: bool = True


@router.get("/sessions")
def admin_sessions(db: Session = Depends(get_db)):
    f = lambda t: t.strftime("%H:%M")
    return [{"id": s.id, "name": s.name, "day_of_week": s.day_of_week, "start_time": f(s.start_time),
             "end_time": f(s.end_time), "pickup_start": f(s.pickup_start), "pickup_end": f(s.pickup_end),
             "active": s.active, "one_off_date": s.one_off_date.isoformat() if s.one_off_date else None}
            for s in db.query(models.TrainingSession).filter(models.TrainingSession.one_off_date.is_(None))]


class ActivityIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    go_date: date
    return_date: date | None = None       # kosong / sama = aktiviti sehari (pergi & balik hari sama)
    pickup_start: time = time(20, 30)     # pickup pergi
    pickup_end: time = time(20, 45)
    return_time: time = time(23, 0)       # balik bermula
    fee: float = Field(default=0.0, ge=0, le=200)   # RM seorang setiap tarikh; 0 = percuma (kaedah lama)
    km: float | None = Field(default=None, ge=0, le=2000)             # jarak aktiviti (km)
    motor_max_km: float | None = Field(default=None, ge=0, le=2000)   # motosikal dibenarkan jika km <= nilai ini (lalai 10)
    car_price: float | None = Field(default=None, ge=0, le=5000)      # harga SEKENDERAAN (bahagi kapasiti = yuran seorang)
    motor_price: float | None = Field(default=None, ge=0, le=500)     # harga motosikal (lalai RM3)
    pickup_mode: str = Field(default="kedua", pattern="^(kumpul|rumah|kolej|kedua)$")   # cara ambil
    gather_place: str = Field(default="", max_length=120)                              # tempat pergi tetap (mod kumpul)
    return_place: str = Field(default="", max_length=120)                              # tempat balik tetap (kosong = ahli pilih)
    return_same: bool = False                                                          # balik ke tempat pergi tetap
    fee_by_assoc: bool = False                                                         # persatuan tanggung yuran ahli


def _activity_groups(db):
    rows = (db.query(models.TrainingSession).filter(models.TrainingSession.one_off_date.is_not(None))
            .order_by(models.TrainingSession.one_off_date).all())
    groups: dict[str, list] = {}
    for s in rows:
        groups.setdefault(s.activity_group or f"s{s.id}", []).append(s)
    return groups


def _group_out(key, legs):
    f = lambda t: t.strftime("%H:%M")
    go = next((s for s in legs if s.trip_only in (None, "going")), legs[0])
    ret = next((s for s in legs if s.trip_only in (None, "returning")), legs[-1])
    name = go.name.removesuffix(" (pergi)")
    return {"id": key, "name": name, "go_date": go.one_off_date.isoformat(),
            "return_date": ret.one_off_date.isoformat(), "pickup_start": f(go.pickup_start),
            "pickup_end": f(go.pickup_end), "return_time": f(ret.end_time),
            "fee": float(go.activity_fee or 0.0), "km": go.km, "motor_max_km": go.motor_max_km,
            "car_price": go.car_price, "motor_price": go.motor_price,
            "pickup_mode": go.pickup_mode or "kedua", "gather_place": go.gather_place or "",
            "return_place": go.return_place or "", "return_same": bool(go.return_same),
            "fee_by_assoc": bool(go.fee_by_assoc), "assoc_settled": bool(go.assoc_settled)}


@router.get("/activities")
def list_activities(db: Session = Depends(get_db)):
    out = []
    for k, v in _activity_groups(db).items():
        g = _group_out(k, v)
        g["assoc_owed"] = svc.assoc_owed(db, v) if g["fee_by_assoc"] else 0.0
        out.append(g)
    return sorted(out, key=lambda x: x["go_date"], reverse=True)


@router.post("/activities", status_code=201)
def add_activity(data: ActivityIn, db: Session = Depends(get_db)):
    ret = data.return_date or data.go_date
    if data.go_date < svc.today_my():
        raise HTTPException(400, "Tarikh aktiviti sudah lepas")
    if ret < data.go_date:
        raise HTTPException(400, "Tarikh balik mesti sama atau selepas tarikh pergi")
    name = data.name.strip()
    group = secrets.token_hex(8)
    gather = svc.clean_place(data.gather_place)
    if data.return_same and not gather:
        raise HTTPException(400, "Isi tempat pergi dahulu jika balik sama dengan pergi")
    back = "" if data.return_same else svc.clean_place(data.return_place)

    def leg(day, label, trip_only, start_time, end_time):
        s = models.TrainingSession(
            name=f"{name} ({label})" if label else name, day_of_week=day.weekday(),
            start_time=start_time, end_time=end_time, pickup_start=data.pickup_start,
            pickup_end=data.pickup_end, one_off_date=day, trip_only=trip_only,
            activity_group=group, activity_fee=round(data.fee, 2), active=True,
            km=data.km, motor_max_km=data.motor_max_km, car_price=data.car_price, motor_price=data.motor_price,
            pickup_mode=data.pickup_mode, gather_place=gather, return_place=back,
            return_same=bool(data.return_same), fee_by_assoc=bool(data.fee_by_assoc))
        db.add(s)
        return s

    if ret == data.go_date:
        leg(data.go_date, "", None, data.pickup_end, data.return_time)
    else:
        leg(data.go_date, "pergi", "going", data.pickup_end, data.pickup_end)
        leg(ret, "balik", "returning", data.return_time, data.return_time)
    db.commit()
    when = svc.fmt_date(data.go_date) + (f" – {svc.fmt_date(ret)}" if ret != data.go_date else "")
    svc._notify(db, None, "announcement", f"Aktiviti baharu: {name} ({when})",
                "Terbuka untuk semua ahli. Perlukan prebet? Tick dalam Tetapan.")
    db.commit()
    return _group_out(group, _activity_groups(db)[group])


class ActivityFeeIn(BaseModel):
    fee: float = Field(default=0.0, ge=0, le=200)
    km: float | None = Field(default=None, ge=0, le=2000)
    motor_max_km: float | None = Field(default=None, ge=0, le=2000)
    car_price: float | None = Field(default=None, ge=0, le=5000)
    motor_price: float | None = Field(default=None, ge=0, le=500)


@router.put("/activities/{key}/fee")
def set_activity_fee(key: str, data: ActivityFeeIn, db: Session = Depends(get_db)):
    """Tukar yuran (atau jadikan percuma). Hanya untuk senarai yang belum disahkan."""
    legs = _activity_groups(db).get(key)
    if not legs:
        raise HTTPException(404, "Aktiviti tak jumpa")
    ids = [s.id for s in legs]
    locked = db.query(models.TrainingEvent).filter(
        models.TrainingEvent.session_id.in_(ids), models.TrainingEvent.status != EventStatus.open).first()
    if locked:
        raise HTTPException(400, "Senarai sudah disahkan/dibatalkan; yuran tak boleh diubah lagi.")
    for s in legs:
        s.activity_fee = round(data.fee, 2)
        s.km, s.motor_max_km = data.km, data.motor_max_km
        s.car_price, s.motor_price = data.car_price, data.motor_price
    db.flush()
    for ev in db.query(models.TrainingEvent).filter(models.TrainingEvent.session_id.in_(ids)):
        uids = {r[0] for r in db.query(models.Booking.user_id).filter_by(
            session_id=ev.session_id, training_date=ev.training_date)}
        for u in db.query(models.User).filter(models.User.id.in_(list(uids) or [0])):
            svc._sync_payment(db, u, ev.training_date)
        svc.refresh_fees(db, ev)
    db.commit()
    return _group_out(key, _activity_groups(db)[key])


class ActivityPickupIn(BaseModel):
    pickup_mode: str = Field(pattern="^(kumpul|rumah|kolej|kedua)$")
    gather_place: str = Field(default="", max_length=120)   # tempat pergi tetap
    return_place: str = Field(default="", max_length=120)   # tempat balik tetap (kosong = ahli pilih)
    return_same: bool = False                               # balik ke tempat pergi tetap


@router.put("/activities/{key}/pickup")
def set_activity_pickup(key: str, data: ActivityPickupIn, db: Session = Depends(get_db)):
    """Tetapkan tempat pergi/balik aktiviti (tetap atau pilihan ahli). Tempahan sedia ada ikut tempat tetap."""
    legs = _activity_groups(db).get(key)
    if not legs:
        raise HTTPException(404, "Aktiviti tak jumpa")
    try:
        n = svc.admin_set_activity_pickup(db, legs, data.pickup_mode, data.gather_place, data.return_place,
                                          data.return_same)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.commit()
    return {**_group_out(key, _activity_groups(db)[key]), "changed": n}


class ActivityFundingIn(BaseModel):
    fee_by_assoc: bool | None = None   # true = persatuan tanggung; false = ahli bayar (lalai)
    assoc_settled: bool | None = None  # persatuan sudah serah kepada BKK


@router.put("/activities/{key}/funding")
def set_activity_funding(key: str, data: ActivityFundingIn, db: Session = Depends(get_db)):
    """Pilih siapa tanggung yuran pengangkutan aktiviti: ahli (lalai) atau persatuan."""
    legs = _activity_groups(db).get(key)
    if not legs:
        raise HTTPException(404, "Aktiviti tak jumpa")
    try:
        svc.admin_set_activity_funding(db, legs, data.fee_by_assoc, data.assoc_settled)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.commit()
    g = _group_out(key, _activity_groups(db)[key])
    g["assoc_owed"] = svc.assoc_owed(db, _activity_groups(db)[key]) if g["fee_by_assoc"] else 0.0
    return g


class MemberPickupIn(BaseModel):
    user_id: int
    training_date: date
    place: str = Field(default="", max_length=120)   # kosong = kembali ke checkpoint kolej ahli
    direction: str | None = Field(default=None, pattern="^(going|returning)$")   # kosong = pergi dan balik


@router.put("/bookings/pickup")
def set_member_pickup(data: MemberPickupIn, db: Session = Depends(get_db)):
    """Admin tetapkan tempat ambil seorang ahli untuk aktiviti luar."""
    user = _get(db, models.User, data.user_id, "Ahli tak jumpa")
    try:
        n = svc.admin_set_member_pickup(db, user, data.training_date, data.place, data.direction)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.commit()
    return {"ok": True, "changed": n}


@router.delete("/activities/{key}")
def delete_activity(key: str, db: Session = Depends(get_db)):
    legs = _activity_groups(db).get(key)
    if not legs:
        raise HTTPException(404, "Aktiviti tak jumpa")
    ids = [s.id for s in legs]
    if db.query(models.Booking).filter(models.Booking.session_id.in_(ids)).first():
        raise HTTPException(400, "Sudah ada tempahan. Batalkan acara itu dahulu (Ringkasan), jangan padam.")
    db.query(models.TrainingEvent).filter(models.TrainingEvent.session_id.in_(ids)).delete(synchronize_session=False)
    db.query(models.Preference).filter(models.Preference.session_id.in_(ids)).delete(synchronize_session=False)
    for s in legs:
        db.delete(s)
    db.commit()
    return {"ok": True}


class EligibilityIn(BaseModel):
    years: list[str]


@router.get("/settings/eligibility")
def get_eligibility(db: Session = Depends(get_db)):
    known = {svc.member_year(r[0]) for r in db.query(models.MemberRoster.member_no)}
    known |= {svc.member_year(r[0]) for r in db.query(models.User.member_no)}
    chosen = svc.eligible_years(db)
    return {"years": chosen, "available": sorted((known | set(chosen)) - {None})}


@router.put("/settings/eligibility")
def set_eligibility(data: EligibilityIn, db: Session = Depends(get_db)):
    years = sorted({y.strip() for y in data.years if y.strip()})
    if "*" in years:
        years = ["*"]
    if not years or any(y != "*" and not re.fullmatch(r"\d{4}", y) for y in years):
        raise HTTPException(400, "Isi sekurang-kurangnya satu sesi, 4 digit (cth 2627), atau * untuk semua")
    _set_setting(db, "eligible_years", ",".join(years))
    db.commit()
    for u in db.query(models.User).filter_by(active=True):
        svc.reconcile_user(db, u)
    db.commit()
    return {"years": years}


@router.put("/sessions/{sid}")
def edit_session(sid: int, data: SessionIn, db: Session = Depends(get_db)):
    s = _get(db, models.TrainingSession, sid, "Sesi tak jumpa")
    for k, v in data.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return {"ok": True}


class VenueIn(BaseModel):
    name: str = Field(default="", max_length=120)   # kosong jika pilih kolej: guna nama kolej
    college_code: str = Field(default="", max_length=10)   # pilih kolej: ahli kolej itu berjalan kaki (tak perlu prebet)
    excluded_codes: list[str] = []
    active: bool = True


def _venue_out(v):
    return {"id": v.id, "name": v.name, "college_code": v.college_code or "",
            "excluded_codes": [c for c in v.excluded_codes.split(",") if c], "active": v.active}


def _venue_fields(db, data: VenueIn, old_code: str = "") -> tuple[str, str, str]:
    """(nama, kod kolej, senarai terkecuali). Memilih kolej: nama = 'Dewan, KOLEJ' jika tiada nama, dan kolej itu
    ditambah ke senarai terkecuali (boleh diubah). Tempat bukan kolej (cth L50): tiada siapa dikecualikan melainkan dipilih."""
    code = data.college_code.strip().upper()
    if code and db.query(models.College).filter_by(code=code).first() is None:
        raise HTTPException(400, "Kolej tak dikenali")
    name = data.name.strip() or (f"Dewan {code}" if code else "")
    if not name:
        raise HTTPException(400, "Isi nama tempat atau pilih kolej")
    ex = [c.strip().upper() for c in data.excluded_codes if c.strip()]
    if code and code != old_code and code not in ex:
        ex.append(code)
    return name, code, ",".join(dict.fromkeys(ex))


@router.get("/venues")
def venues(db: Session = Depends(get_db)):
    return [_venue_out(v) for v in db.query(models.Venue).order_by(models.Venue.name)]


@router.post("/venues", status_code=201)
def add_venue(data: VenueIn, db: Session = Depends(get_db)):
    name, code, ex = _venue_fields(db, data)
    if db.query(models.Venue).filter_by(name=name).first():
        raise HTTPException(409, "Nama tempat dah wujud")
    v = models.Venue(name=name, active=data.active, excluded_codes=ex, college_code=code)
    db.add(v)
    db.commit()
    return _venue_out(v)


@router.put("/venues/{vid}")
def edit_venue(vid: int, data: VenueIn, db: Session = Depends(get_db)):
    v = _get(db, models.Venue, vid, "Tempat tak jumpa")
    name, code, ex = _venue_fields(db, data, old_code=v.college_code or "")
    v.name, v.active, v.college_code, v.excluded_codes = name, data.active, code, ex
    db.flush()
    for ev in db.query(models.TrainingEvent).filter(models.TrainingEvent.venue_id == v.id,
                                                    models.TrainingEvent.status != EventStatus.cancelled,
                                                    models.TrainingEvent.training_date >= svc.today_my()):
        svc.apply_venue(db, ev)
    db.commit()
    return _venue_out(v)


@router.delete("/venues/{vid}")
def delete_venue(vid: int, db: Session = Depends(get_db)):
    v = _get(db, models.Venue, vid, "Tempat tak jumpa")
    if db.query(models.TrainingEvent).filter_by(venue_id=v.id).first():
        raise HTTPException(400, "Tempat ini sudah digunakan pada latihan. Guna 'Nyahaktif' sahaja.")
    db.delete(v)
    db.commit()
    return {"ok": True}


class CollegeIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(pattern="^(dekat|jauh)$")
    transport_available: bool = True


@router.get("/colleges")
def colleges(db: Session = Depends(get_db)):
    return [{"id": c.id, "code": c.code, "name": c.name, "category": c.category,
             "transport_available": c.transport_available} for c in db.query(models.College).order_by(models.College.id)]


@router.put("/colleges/{cid}")
def edit_college(cid: int, data: CollegeIn, db: Session = Depends(get_db)):
    c = _get(db, models.College, cid, "Kolej tak jumpa")
    c.name, c.category, c.transport_available = data.name, data.category, data.transport_available
    db.commit()
    return {"ok": True}


class PointIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    college_id: int
    gender: Gender = Gender.any
    active: bool = True


def _point_out(db, p):
    col = db.get(models.College, p.college_id)
    return {"id": p.id, "name": p.name, "college_id": p.college_id, "college": col.code if col else None,
            "gender": p.gender.value, "active": p.active}


@router.get("/pickup-points")
def admin_points(db: Session = Depends(get_db)):
    return [_point_out(db, p) for p in db.query(models.PickupPoint).order_by(models.PickupPoint.college_id)]


@router.post("/pickup-points", status_code=201)
def add_point(data: PointIn, db: Session = Depends(get_db)):
    _get(db, models.College, data.college_id, "Kolej tak jumpa")
    if db.query(models.PickupPoint).filter_by(college_id=data.college_id, gender=data.gender, name=data.name.strip()).first():
        raise HTTPException(409, "Checkpoint dengan nama ini dah wujud untuk kolej & jantina ini")
    p = models.PickupPoint(name=data.name.strip(), college_id=data.college_id, gender=data.gender, active=data.active)
    db.add(p)
    db.commit()
    return _point_out(db, p)


@router.put("/pickup-points/{pid}")
def edit_point(pid: int, data: PointIn, db: Session = Depends(get_db)):
    p = _get(db, models.PickupPoint, pid, "Checkpoint tak jumpa")
    p.name, p.college_id, p.gender, p.active = data.name.strip(), data.college_id, data.gender, data.active
    db.commit()
    return _point_out(db, p)


@router.delete("/pickup-points/{pid}")
def delete_point(pid: int, move_to: int | None = None, db: Session = Depends(get_db),
                 me: models.User = Depends(require_admin)):
    """Padam checkpoint. Jika ahli masih memilihnya, mesti pilih checkpoint lain (kolej sama) untuk memindahkan mereka."""
    p = _get(db, models.PickupPoint, pid, "Checkpoint tak jumpa")
    users = db.query(models.User).filter_by(pickup_point_id=pid).all()
    books = db.query(models.Booking).filter_by(pickup_point_id=pid).all()
    if (users or books) and move_to is None:
        raise HTTPException(409, f"{len(users)} ahli dan {len(books)} tempahan masih guna checkpoint ini. "
                                 "Pilih checkpoint lain untuk memindahkan mereka.")
    if move_to is not None:
        if move_to == pid:
            raise HTTPException(400, "Pilih checkpoint yang berbeza")
        t = _get(db, models.PickupPoint, move_to, "Checkpoint destinasi tak jumpa")
        if t.college_id != p.college_id:
            raise HTTPException(400, "Checkpoint destinasi mesti kolej yang sama")
        for u in users:
            u.pickup_point_id = t.id
        for b in books:
            b.pickup_point_id = t.id
    db.delete(p)
    db.commit()
    return {"ok": True, "moved_users": len(users), "moved_bookings": len(books)}


# ------------------------------------------------------------ cuti

class HolidayIn(BaseModel):
    training_date: date
    note: str = Field(default="Cuti", max_length=120)


@router.get("/holidays")
def list_holidays(db: Session = Depends(get_db)):
    return [{"id": h.id, "training_date": h.training_date.isoformat(), "note": h.note}
            for h in db.query(models.Holiday).filter(models.Holiday.training_date >= svc.today_my() - timedelta(days=30))
            .order_by(models.Holiday.training_date)]


@router.post("/holidays", status_code=201)
def add_holiday(data: HolidayIn, db: Session = Depends(get_db)):
    """Tandakan tarikh cuti: tiada pengangkutan. Tempahan sedia ada pada tarikh itu dibatalkan dan ahli dimaklumkan."""
    if data.training_date < svc.today_my():
        raise HTTPException(400, "Tarikh sudah lepas")
    h = db.query(models.Holiday).filter_by(training_date=data.training_date).first()
    note = (data.note or "Cuti").strip() or "Cuti"
    if h is None:
        db.add(models.Holiday(training_date=data.training_date, note=note))
    else:
        h.note = note
    db.flush()
    d = data.training_date
    affected = 0
    for ev in db.query(models.TrainingEvent).filter_by(training_date=d):
        if ev.status == EventStatus.cancelled:
            continue
        rows = db.query(models.Booking).filter_by(training_date=d, session_id=ev.session_id).all()
        if rows:
            affected += svc.cancel_event(db, ev)
        else:
            ev.status = EventStatus.cancelled
    svc._notify(db, None, "announcement", f"Cuti: {svc.fmt_date(d)}",
                f"{note}. Tiada pengangkutan pada tarikh ini.", d, severity="info", link="")
    db.commit()
    return {"ok": True, "cancelled_members": affected}


@router.delete("/holidays/{hid}")
def delete_holiday(hid: int, db: Session = Depends(get_db)):
    h = _get(db, models.Holiday, hid)
    d = h.training_date
    db.delete(h)
    db.flush()
    # buka semula latihan yang dibatalkan kerana cuti (tiada tempahan)
    for ev in db.query(models.TrainingEvent).filter_by(training_date=d, status=EventStatus.cancelled):
        if not db.query(models.Booking).filter_by(training_date=d, session_id=ev.session_id,
                                                  status=BookingStatus.confirmed).first():
            ev.status = EventStatus.open
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------ prebet: senarai & sahkan bagi pihak

@router.get("/prebet")
def prebet_list(training_date: date, db: Session = Depends(get_db)):
    return svc.prebet_status_list(db, training_date)


class AvailOnBehalf(BaseModel):
    user_id: int
    training_date: date
    available: bool


@router.put("/prebet/availability")
def prebet_on_behalf(data: AvailOnBehalf, db: Session = Depends(get_db)):
    u = _get(db, models.User, data.user_id, "Prebet tak jumpa")
    try:
        svc.set_availability(db, u, data.training_date, data.available, by_admin=True)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return svc.prebet_status_list(db, data.training_date)


@router.get("/users/{uid}/licence")
def user_licence(uid: int, db: Session = Depends(get_db)):
    u = _get(db, models.User, uid)
    if not u.licence_file:
        raise HTTPException(404, "Tiada gambar lesen")
    return storage.serve(u.licence_file, "Fail hilang")


@router.get("/users/{uid}/insurance")
def user_insurance(uid: int, db: Session = Depends(get_db)):
    u = _get(db, models.User, uid)
    if not u.insurance_file:
        raise HTTPException(404, "Tiada gambar insurans")
    return storage.serve(u.insurance_file, "Fail hilang")


class PaxApproveIn(BaseModel):
    approve: bool


@router.put("/users/{uid}/passenger")
def passenger_approval(uid: int, data: PaxApproveIn, me: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Luluskan/tarik balik kebenaran prebet untuk turut menempah sebagai penumpang."""
    u = _get(db, models.User, uid)
    u.passenger_ok = data.approve
    u.passenger_request = False
    svc.resolve_warning(db, me.id, f"paxreq:{u.id}")
    for a in db.query(models.User).filter_by(role=Role.admin, active=True):
        svc.resolve_warning(db, a.id, f"paxreq:{u.id}")
    svc._notify(db, u.id, "driver", "Permohonan penumpang " + ("diluluskan" if data.approve else "ditolak"),
                "Anda kini boleh menempah sebagai penumpang di tab Penumpang." if data.approve else
                "Hubungi BKK jika perlu.", severity="info", link="/profil")
    db.commit()
    return {"id": u.id, "passenger_ok": u.passenger_ok}


# ------------------------------------------------------------ jadual harga

class RatesIn(BaseModel):
    fees: dict[str, dict[str, float | None]] = {}
    payouts: dict[str, dict[str, float | None]] = {}


@router.get("/settings/rates")
def get_rates(db: Session = Depends(get_db)):
    return svc.fee_tables(db)


@router.put("/settings/rates")
def put_rates(data: RatesIn, me: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Jadual yuran penumpang dan kadar bayaran prebet (kereta/motosikal x dekat/jauh).
    Kadar prebet kosong = nilai lalai config (PAYOUT_*). HANYA ADMIN boleh ubah. Menjejaskan bayaran yang belum dibayar sahaja."""
    for table, prefix in ((data.fees, "fee"), (data.payouts, "payout")):
        for k, row in table.items():
            if k not in ("car", "motorcycle"):
                raise HTTPException(400, "Jenis kenderaan tak sah")
            for c, v in row.items():
                if c not in ("dekat", "jauh"):
                    raise HTTPException(400, "Kategori tak sah")
                if v is not None and (v < 0 or v > 500):
                    raise HTTPException(400, "Harga mesti antara RM0 dan RM500")
                if prefix == "fee" and v is None:
                    continue
                _set_setting(db, f"{prefix}_{k}_{c}", "" if v is None else str(round(v, 2)))
    db.flush()
    for ev in db.query(models.TrainingEvent).filter(models.TrainingEvent.training_date >= svc.today_my(),
                                                    models.TrainingEvent.status == EventStatus.open):
        svc.refresh_fees(db, ev)
    db.commit()
    return svc.fee_tables(db)


# ------------------------------------------------------------ bayar prebet dengan resit

@router.get("/payouts/overview")
def payouts_overview(db: Session = Depends(get_db)):
    """Bendahari: baki bayaran ikut prebet (digabung), butiran tiap tarikh, tanda 'sampai'/'hantar', QR bank."""
    return svc.payout_overview(db)


@router.get("/payouts/history")
def payouts_history(db: Session = Depends(get_db)):
    return svc.payout_history(db)


@router.post("/payouts/driver")
async def pay_one_driver(driver_id: int = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Bayar seorang prebet sekali gus (semua baki, digabung) dan muat naik satu resit."""
    _get(db, models.User, driver_id, "Prebet tak jumpa")
    name = await save_upload(file, prefix="payout_receipt_")
    try:
        res = svc.pay_driver(db, driver_id, name)
    except ValueError as e:
        db.rollback()
        storage.delete(name)
        raise HTTPException(400, str(e))
    db.commit()
    return {"ok": True, **res}


class PayoutModeIn(BaseModel):
    mode: str = Field(pattern="^(latihan|mingguan|bulanan)$")


@router.get("/settings/payout-mode")
def get_payout_mode(db: Session = Depends(get_db)):
    return {"mode": svc.payout_mode(db), "modes": svc.PAYOUT_MODES}


@router.put("/settings/payout-mode")
def put_payout_mode(data: PayoutModeIn, me: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin tetapkan kekerapan bayaran prebet. Prebet dan bendahari dimaklumkan."""
    old = svc.payout_mode(db)
    _set_setting(db, "payout_mode", data.mode)
    if old != data.mode:
        rule = {"latihan": "bayaran dibuat selepas setiap latihan (sebelum tengah malam hari selepas latihan)",
                "mingguan": "bayaran digabung seminggu (Isnin–Ahad), dibayar sebelum tengah malam hari Ahad",
                "bulanan": "bayaran digabung sebulan, dibayar sebelum tengah malam hari terakhir bulan"}[data.mode]
        targets = {u.id for u in svc.prebet_users(db)} | {u.id for u in db.query(models.User).filter_by(
            is_treasurer=True, active=True)}
        for uid in targets:
            svc._notify(db, uid, "payout", f"Kaedah bayaran prebet ditukar: {svc.PAYOUT_MODES[data.mode]}",
                        f"Mulai sekarang {rule}. Latihan yang belum dibayar digabung dalam bayaran seterusnya.",
                        severity="info", link="/pendapatan" if uid not in {t.id for t in db.query(models.User).filter_by(is_treasurer=True)} else "/bendahari")
    db.commit()
    return {"mode": data.mode, "modes": svc.PAYOUT_MODES}


@router.post("/payouts/receipt")
async def payout_with_receipt(vehicle_id: int = Form(...), training_date: date = Form(...),
                              file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Bendahari tandakan sudah bayar prebet dan muat naik resit. Prebet dimaklumkan dan boleh tanda 'diterima'."""
    row = next((r for r in svc.payout_rows(db, training_date) if r["vehicle_id"] == vehicle_id), None)
    if row is None:
        raise HTTPException(404, "Tiada rekod untuk kenderaan ini")
    if row["outstanding"] <= 0:
        raise HTTPException(400, "Tiada baki tertunggak untuk dibayar")
    name = await save_upload(file, prefix="payout_receipt_")
    p = models.DriverPayout(vehicle_id=vehicle_id, training_date=training_date, amount=row["outstanding"], receipt_file=name)
    db.add(p)
    db.flush()
    v = db.get(models.Vehicle, vehicle_id)
    if v and v.driver_id:
        svc._notify(db, v.driver_id, "payout", f"Bayaran {svc.fmt_date(training_date)}: RM{row['outstanding']:.2f}",
                    "Persatuan telah membayar anda. Lihat resit dan tekan 'Diterima'.", training_date,
                    severity="warning", link="/pendapatan", ref=f"payout:{p.id}")
    db.commit()
    return {"ok": True, "amount": row["outstanding"], "id": p.id}


@router.get("/payouts/{pid}/receipt")
def payout_receipt(pid: int, db: Session = Depends(get_db)):
    r = _get(db, models.DriverPayout, pid)
    if not r.receipt_file:
        raise HTTPException(404, "Tiada resit")
    return storage.serve(r.receipt_file, "Fail hilang")


# ------------------------------------------------------------ reset data ujian

def _csv(headers: list[str], rows: list[list]) -> str:
    """CSV selamat dibuka di Excel: awalan = + - @ diberi petikan tunggal supaya tidak jadi formula."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(headers)
    for r in rows:
        w.writerow([("'" + v) if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else ("" if v is None else v) for v in r])
    return "\ufeff" + out.getvalue()


@router.get("/export")
def export_backup(db: Session = Depends(get_db), me: models.User = Depends(require_admin)):
    """Sandaran data dalam fail BKK (zip berisi CSV). TIDAK termasuk: kata laluan, gambar lesen/resit/QR (fail),
    dan no. akaun bank penuh (hanya nama bank + 4 digit akhir). Hanya admin."""
    cols = {c.id: c.code for c in db.query(models.College)}
    users = db.query(models.User).order_by(models.User.id).all()
    uname = {u.id: u.name for u in users}
    pts = {p.id: p.name for p in db.query(models.PickupPoint)}
    files = {}
    files["ahli_dan_prebet.csv"] = _csv(
        ["id", "no_ahli", "nama", "nama_pendek", "peranan", "bendahari", "aktif", "jantina", "telefon", "emel", "kolej",
         "kolej_lain", "blok", "checkpoint", "kredit_RM", "bank_prebet", "akaun_4_digit_akhir", "tarikh_tamat_lesen", "didaftar"],
        [[u.id, u.member_no, u.name, u.short_name, u.role.value, u.is_treasurer, u.active, u.gender.value if u.gender else "",
          u.phone, u.email, cols.get(u.college_id, ""), u.college_other, u.block, pts.get(u.pickup_point_id, ""),
          u.credit_balance, u.payout_bank, (u.payout_account_no or "")[-4:], u.licence_expiry or "",
          u.created_at.strftime("%Y-%m-%d %H:%M")] for u in users])
    files["kenderaan.csv"] = _csv(
        ["id", "prebet", "nama", "jenama", "warna", "no_plat", "jenis", "kategori", "tempat_duduk", "kelulusan", "aktif"],
        [[v.id, uname.get(v.driver_id, ""), v.name, v.brand, v.colour, v.plate_no, v.vehicle_type.value, v.category,
          v.capacity, v.approval.value, v.active] for v in db.query(models.Vehicle).order_by(models.Vehicle.id)])
    files["tempahan.csv"] = _csv(
        ["tarikh", "ahli", "arah", "status", "kenderaan_id", "e_hailing", "checkpoint"],
        [[b.training_date, uname.get(b.user_id, ""), b.direction.value, b.status.value, b.vehicle_id or "", b.ehailing,
          b.pickup_place or pts.get(b.pickup_point_id, "")] for b in db.query(models.Booking).order_by(models.Booking.training_date, models.Booking.user_id)])
    files["bayaran_ahli.csv"] = _csv(
        ["tarikh", "ahli", "jumlah_RM", "kredit_digunakan_RM", "status"],
        [[p.training_date, uname.get(p.user_id, ""), p.amount, p.credit_applied, p.status.value]
         for p in db.query(models.Payment).order_by(models.Payment.training_date, models.Payment.user_id)])
    veh_driver = {v.id: v.driver_id for v in db.query(models.Vehicle)}
    files["bayaran_prebet.csv"] = _csv(
        ["tarikh_latihan", "prebet", "jumlah_RM", "dibayar_pada", "kumpulan_resit", "diterima_prebet"],
        [[r.training_date, uname.get(r.driver_id or veh_driver.get(r.vehicle_id), ""), r.amount,
          r.paid_at.strftime("%Y-%m-%d %H:%M"), r.batch, r.received] for r in db.query(models.DriverPayout).order_by(models.DriverPayout.id)])
    files["BACA_SAYA.txt"] = (
        "Sandaran PSSGUTM Transport (" + svc.now_my().strftime("%Y-%m-%d %H:%M") + ")\r\n"
        "Data peribadi: simpan dalam folder persendirian BKK (2-3 orang sahaja). Jangan kongsi di WhatsApp.\r\n"
        "Tidak termasuk: kata laluan, gambar lesen/resit/QR, no. akaun bank penuh.\r\n"
        "Gambar (lesen, resit, QR) disandar berasingan: Supabase > Storage > bucket uploads.\r\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    fname = f"sandaran-pssgutm-{svc.today_my().isoformat()}.zip"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/reset/status")
def reset_status(me: models.User = Depends(require_admin)):
    return {"allowed": config.ALLOW_RESET}


class ResetIn(BaseModel):
    confirm: str


@router.post("/reset")
def reset_all(data: ResetIn, me: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Padam semua data ujian supaya sistem nampak baharu. Hanya jika ALLOW_RESET=true dan taip RESET.
    Kekal: akaun admin yang sedang guna, senarai ahli sah, kolej, checkpoint, tempat latihan, jenis kenderaan, jadual Rabu/Sabtu."""
    if not config.ALLOW_RESET:
        raise HTTPException(403, "Reset dimatikan. Tetapkan ALLOW_RESET=true pada server jika perlu.")
    if data.confirm.strip() != "RESET":
        raise HTTPException(400, "Taip RESET untuk mengesahkan")
    M = models
    for model in (M.NotificationDismissal, M.Notification, M.PasswordReset, M.Feedback, M.DriverPayout,
                  M.Payment, M.Booking, M.VehicleUnavailable, M.PrebetAvailability, M.DutyTick, M.AdminDuty, M.Preference, M.Holiday,
                  M.TrainingEvent):
        db.query(model).delete(synchronize_session=False)
    db.query(M.Vehicle).delete(synchronize_session=False)
    db.query(M.TrainingSession).filter(M.TrainingSession.one_off_date.isnot(None)).delete(synchronize_session=False)
    db.query(M.User).filter(M.User.id != me.id).delete(synchronize_session=False)
    db.query(M.Setting).delete(synchronize_session=False)
    me.payout_bank = me.payout_account_no = me.payout_account_name = ""
    me.payout_qr_file = me.payout_qr2_file = me.licence_file = me.insurance_file = None
    me.licence_expiry, me.credit_balance = None, 0.0
    me.passenger_ok = me.passenger_request = False
    me.short_name = me.block = ""
    me.pickup_point_id = None
    db.commit()
    removed = storage.delete_all()
    return {"ok": True, "files_removed": removed}


@router.get("/arrears")
def arrears_list(db: Session = Depends(get_db)):
    """Tunggakan semua ahli (untuk bendahari & admin), dari RM0."""
    uids = {r[0] for r in db.query(models.Payment.user_id).filter(
        models.Payment.status.in_((PaymentStatus.unpaid, PaymentStatus.rejected))).distinct()}
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(list(uids) or [0]))}
    out = []
    for uid in uids:
        a = svc.arrears(db, uid)
        if a["total"] > 0:
            u = users[uid]
            out.append({"user_id": uid, "name": u.name, "member_no": u.member_no, "phone": u.phone,
                        "total": a["total"], "count": a["count"], "oldest": a["oldest"], "blocked": a["blocked"]})
    return sorted(out, key=lambda r: (not r["blocked"], r["oldest"] or ""))


# ------------------------------------------------------------ admin tambah / buang ahli secara manual (selepas waktu tutup 5 petang)

class AdminBookIn(BaseModel):
    user_id: int
    training_date: date
    session_id: int
    going: bool = True
    returning: bool = True


@router.post("/bookings/add")
def admin_add_booking(data: AdminBookIn, db: Session = Depends(get_db)):
    """Admin tambah (atau buang, jika kedua-dua false) ahli pada satu tarikh walaupun waktu tutup ahli sudah lepas."""
    u = _get(db, models.User, data.user_id, "Ahli tak jumpa")
    try:
        svc.book_date(db, u, data.training_date, data.session_id, data.going, data.returning, by_admin=True)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return {"ok": True}


# ------------------------------------------------------------ admin bertugas (ikut bulan)

class DutyIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    weekdays: list[int] = []
    phone: str = Field(default="", max_length=20)
    user_id: int | None = None      # kosong = diri sendiri


@router.get("/duty")
def list_duty(month: str | None = None, db: Session = Depends(get_db)):
    month = month or svc.today_my().strftime("%Y-%m")
    rows = {r.user_id: r for r in db.query(models.AdminDuty).filter_by(month=month)}
    out = []
    for a in db.query(models.User).filter_by(role=Role.admin, active=True).order_by(models.User.name):
        r = rows.get(a.id)
        out.append({"user_id": a.id, "name": a.name, "short_name": svc.short(a), "profile_phone": a.phone,
                    "weekdays": [int(x) for x in r.weekdays.split(",") if x] if r else [],
                    "phone": (r.phone if r and r.phone else ""), "set": r is not None})
    return {"month": month, "admins": out, "site": {"name": config.SITE_CONTACT_NAME, "phone": config.SITE_CONTACT_PHONE}}


@router.put("/duty")
def put_duty(data: DutyIn, me: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    uid = data.user_id or me.id
    if uid != me.id and me.role != Role.admin:
        raise HTTPException(403, "Hanya admin")
    target = _get(db, models.User, uid, "Admin tak jumpa")
    if target.role != Role.admin:
        raise HTTPException(400, "Bukan admin")
    if any(d < 0 or d > 6 for d in data.weekdays):
        raise HTTPException(400, "Hari tak sah")
    r = db.query(models.AdminDuty).filter_by(user_id=uid, month=data.month).first()
    if r is None:
        r = models.AdminDuty(user_id=uid, month=data.month)
        db.add(r)
    r.weekdays = ",".join(str(d) for d in sorted(set(data.weekdays)))
    r.phone = re.sub(r"[^\d+]", "", data.phone)
    db.commit()
    return list_duty(data.month, db)


# ------------------------------------------------------------ penyata untung rugi (admin sahaja; bendahari tak boleh)

@router.get("/profit")
def profit(month: str | None = None, me: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    if month and not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(400, "Format bulan YYYY-MM")
    return svc.profit_statement(db, month)
