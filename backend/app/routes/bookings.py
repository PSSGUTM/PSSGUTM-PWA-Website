import os
import secrets
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config, imaging, models, storage
from ..database import get_db
from ..models import BookingStatus, EventStatus, PaymentStatus
from ..security import get_current_user, rate_limit
from ..services import booking as svc

router = APIRouter(tags=["bookings"])


class FeedbackIn(BaseModel):
    kind: str = Field(default="cadangan", pattern="^(cadangan|masalah|lain)$")
    message: str = Field(min_length=5, max_length=1000)


@router.post("/feedback", status_code=201, dependencies=[Depends(rate_limit(10, 3600))])
def send_feedback(data: FeedbackIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ahli hantar cadangan/aduan. Admin baca dalam Admin > Lagi."""
    db.add(models.Feedback(user_id=user.id, kind=data.kind, message=data.message.strip()))
    db.commit()
    return {"ok": True}


@router.get("/bookings")
def my_bookings(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Trip akan datang (dan latihan terkini yang baru tamat, sehingga latihan seterusnya), dikumpul ikut tarikh."""
    svc.ensure_events(db)
    rows = (db.query(models.Booking)
            .filter(models.Booking.user_id == user.id,
                    models.Booking.training_date >= svc.last_session_date(db))
            .order_by(models.Booking.training_date, models.Booking.direction).all())
    points = {p.id: p.name for p in db.query(models.PickupPoint)}
    vehicles = {v.id: v for v in db.query(models.Vehicle)}
    sessions = {s.id: s for s in db.query(models.TrainingSession)}
    venues = {v.id: v for v in db.query(models.Venue)}
    payments = {p.training_date: p for p in db.query(models.Payment).filter_by(user_id=user.id)}

    grouped: dict[date, dict] = {}
    for b in rows:
        s = sessions[b.session_id]
        ev = svc.event_on(db, b.training_date)
        venue = venues.get(ev.venue_id) if ev and ev.venue_id else None
        g = grouped.setdefault(b.training_date, {
            "training_date": b.training_date.isoformat(), "session_name": s.name,
            "start_time": s.start_time.strftime("%H:%M"), "end_time": s.end_time.strftime("%H:%M"),
            "pickup_window": svc.pickup_window(s), "return_time": svc.fmt12(s.end_time),
            "event_status": ev.status.value if ev else "open",
            "venue": venue.name if venue else None, "trips": [], "payment": None, "car": None,
            "is_activity": s.one_off_date is not None, "trip_only": s.trip_only,
            "past": b.training_date < svc.today_my(),
            "arrive_by": svc.arrive_by(s),
            "closed": svc.member_closed(b.training_date),
            "cutoff": svc.fmt12(svc._hm(config.CUTOFF_TIME)),
            "pay_deadline": svc.pay_deadline(b.training_date).isoformat(),
        })
        g["trips"].append({"id": b.id, "direction": b.direction.value, "status": b.status.value,
                           "checkpoint": svc.pickup_label(b, points), "block": user.block or "",
                           "ehailing": bool(b.ehailing and not b.vehicle_id), "ehailing_note": b.ehailing_note or ""})
        v = vehicles.get(b.vehicle_id) if b.vehicle_id else None
        # Butiran kereta & driver hanya dipaparkan selepas senarai disahkan
        if v and b.status == BookingStatus.confirmed and ev and ev.status == EventStatus.finalised:
            drv = db.get(models.User, v.driver_id) if v.driver_id else None
            g["car"] = {"name": v.name, "plate_no": v.plate_no, "vehicle_type": v.vehicle_type.value,
                        "brand": v.brand, "colour": v.colour, "desc": svc.vehicle_desc(v),
                        "driver_name": svc.short(drv) if drv else None, "driver_phone": drv.phone if drv else None}
        pay = payments.get(b.training_date)
        if pay and pay.status != PaymentStatus.void:  # void (cth e-hailing / dibatalkan) tak dipaparkan
            g["payment"] = {"id": pay.id, "amount": pay.amount, "credit_applied": pay.credit_applied,
                            "due": svc.payment_due(pay), "status": pay.status.value,
                            "can_pay": svc.can_pay(db, pay)}
    return list(grouped.values())


class SkipIn(BaseModel):
    training_date: date
    skip: bool = True


@router.post("/bookings/skip")
def skip(data: SkipIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        changed = svc.set_skip(db, user, data.training_date, data.skip)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    if changed == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tiada booking untuk ditukar pada tarikh ini")
    return {"changed": changed, "skipped": data.skip}


@router.get("/payments/me")
def my_payments(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(models.Payment).filter_by(user_id=user.id)
            .order_by(models.Payment.training_date.desc()).limit(30).all())
    return [{"id": p.id, "training_date": p.training_date.isoformat(), "amount": p.amount,
             "due": svc.payment_due(p), "status": p.status.value, "has_receipt": bool(p.receipt_path),
             "deadline": svc.pay_deadline(p.training_date).isoformat(),
             "overdue": svc.now_my() >= svc.pay_deadline(p.training_date),
             "can_pay": svc.can_pay(db, p)} for p in rows]


@router.get("/payments/summary")
def payments_summary(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Tab Bayaran: tunggakan ahli (dari RM0), maklumat bayaran persatuan."""
    a = svc.arrears(db, user.id)
    return {**a, "info": read_settings(db), "block_days": config.ARREARS_BLOCK_DAYS,
            "deadline_time": svc.fmt12(svc._hm(config.PAY_DEADLINE_TIME))}


ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}
MAGIC = {".jpg": b"\xff\xd8\xff", ".png": b"\x89PNG", ".pdf": b"%PDF"}


async def save_upload(file: UploadFile, prefix: str = "", images_only: bool = False) -> str:
    ext = ALLOWED.get(file.content_type or "")
    if ext is None or (images_only and ext == ".pdf"):
        raise HTTPException(400, "Hanya gambar JPG atau PNG" if images_only else "Hanya JPG, PNG atau PDF")
    content = await file.read(config.MAX_RECEIPT_BYTES + 1)
    if len(content) > config.MAX_RECEIPT_BYTES:
        raise HTTPException(413, "Fail terlalu besar (maks 5MB)")
    if not content.startswith(MAGIC[ext]):
        raise HTTPException(400, "Kandungan fail tak sepadan dengan jenisnya")
    content, ext = imaging.compress(content, ext, prefix)  # kecilkan gambar (fail asal dikekalkan jika gagal)
    name = f"{prefix}{secrets.token_hex(16)}{ext}"  # nama rawak, bukan nama asal
    storage.put(name, content)
    return name


@router.post("/payments/{payment_id}/receipt")
async def upload_receipt(payment_id: int, file: UploadFile = File(...),
                         user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    pay = db.get(models.Payment, payment_id)
    if pay is None or pay.user_id != user.id:
        raise HTTPException(404, "Bayaran tak jumpa")
    if not svc.can_pay(db, pay):
        raise HTTPException(400, "Bayaran belum dibuka (senarai belum disahkan / kereta belum ditetapkan) atau sudah selesai")
    pay.receipt_path = await save_upload(file)
    pay.status = PaymentStatus.pending
    db.commit()
    return {"status": pay.status.value}


# ---- maklumat bayaran (bank/QR) yang dipaparkan kepada ahli ----
PAY_KEYS = ("pay_bank", "pay_account_no", "pay_account_name", "pay_notes")


def read_settings(db: Session) -> dict:
    vals = {s.key: s.value for s in db.query(models.Setting)}
    out = {k: vals.get(k, "") for k in PAY_KEYS}
    out["has_qr"] = bool(vals.get("pay_qr_file"))
    return out


BRAND_DEFAULTS = {"brand_name": "PSSGUTM", "brand_primary": "#a8322a", "brand_accent": "#d4a94e",
                  "contact_whatsapp": "60192278390", "contact_email": "muhammadamirulaiman0808@gmail.com",
                  "wa_group_link": ""}


def read_branding(db: Session) -> dict:
    vals = {s.key: s.value for s in db.query(models.Setting)}
    out = {k: (vals.get(k) or dflt) for k, dflt in BRAND_DEFAULTS.items()}
    out["has_logo"] = bool(vals.get("brand_logo_file"))
    return out


def _may_see_pay_info(db: Session, user: models.User) -> bool:
    """Bank/QR persatuan hanya dipaparkan selepas BKK sahkan senarai (atau auto) supaya ahli tak bayar awal.
    Admin & bendahari sentiasa boleh."""
    return user.role == models.Role.admin or user.is_treasurer or svc.user_can_pay_any(db, user)


@router.get("/payment-info")
def payment_info(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _may_see_pay_info(db, user):
        return {**{k: "" for k in PAY_KEYS}, "has_qr": False, "locked": True}
    return {**read_settings(db), "locked": False}


@router.get("/payment-info/qr")
def payment_qr(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _may_see_pay_info(db, user):
        raise HTTPException(403, "Maklumat bayaran dibuka selepas BKK sahkan senarai")
    s = db.get(models.Setting, "pay_qr_file")
    if not s or not s.value:
        raise HTTPException(404, "Tiada QR")
    return storage.serve(s.value, "Fail QR hilang")


@router.get("/notifications")
def notifications(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    gone = {d.notification_id for d in db.query(models.NotificationDismissal).filter_by(user_id=user.id)}
    rows = (db.query(models.Notification)
            .filter((models.Notification.user_id == user.id) | (models.Notification.user_id.is_(None)))
            .order_by(models.Notification.created_at.desc()).limit(80).all())
    rows = [n for n in rows if n.id not in gone][:50]
    today = svc.today_my()
    order = {"warning": 0, "task": 1, "info": 2}
    rows.sort(key=lambda n: (order.get(n.severity, 2), -n.created_at.timestamp()))
    return [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "severity": n.severity or "info",
             "link": n.link or "", "deletable": svc.warning_deletable(db, n, today),
             "unlock_date": svc.warning_unlock_date(db, n).isoformat() if (n.severity or "info") == "warning" else None,
             "read": n.read if n.user_id else False, "created_at": n.created_at.isoformat()} for n in rows]


@router.delete("/notifications/{nid}")
def delete_notification(nid: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Padam notifikasi (amaran hanya pada tarikh latihan seterusnya)."""
    n = db.get(models.Notification, nid)
    if n is None or (n.user_id is not None and n.user_id != user.id):
        raise HTTPException(404, "Tak jumpa")
    if not svc.warning_deletable(db, n):
        d = svc.warning_unlock_date(db, n)
        raise HTTPException(400, f"Amaran ini boleh dipadam pada {d.strftime('%d/%m/%Y')} (tarikh latihan seterusnya)")
    if n.user_id is None:
        if not db.query(models.NotificationDismissal).filter_by(user_id=user.id, notification_id=nid).first():
            db.add(models.NotificationDismissal(user_id=user.id, notification_id=nid))
    else:
        db.delete(n)
    db.commit()
    return {"ok": True}


@router.post("/notifications/{nid}/read")
def mark_read(nid: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.get(models.Notification, nid)
    if n is None or n.user_id != user.id:
        raise HTTPException(404, "Tak jumpa")
    n.read = True
    db.commit()
    return {"ok": True}
