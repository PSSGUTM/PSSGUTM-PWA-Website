from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..security import get_current_user
from ..services import booking as svc
from .auth import UserOut, clean_phone

router = APIRouter(tags=["member"])


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=9, max_length=20)
    college_id: int | None = None
    college_other: str | None = Field(default=None, max_length=60)  # 'Lain-lain'
    gender: models.Gender | None = None  # hanya diterima jika jantina belum ditetapkan
    short_name: str | None = Field(default=None, max_length=40)
    block: str | None = Field(default=None, max_length=40)
    pickup_point_id: int | None = None

    @field_validator("phone")
    @classmethod
    def ph(cls, v):
        return clean_phone(v)


@router.get("/profile", response_model=UserOut)
def get_profile(user: models.User = Depends(get_current_user)):
    return user


@router.put("/profile", response_model=UserOut)
def update_profile(data: ProfileUpdate, user: models.User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    user.name, user.phone = data.name.strip(), data.phone
    if data.short_name is not None:
        user.short_name = data.short_name.strip()
    if data.block is not None:
        user.block = data.block.strip()
    if user.gender is None and data.gender in (models.Gender.male, models.Gender.female):
        user.gender = data.gender
        r = db.query(models.MemberRoster).filter_by(member_no=user.member_no).first()
        if r is not None:
            r.gender = data.gender
    if data.college_id and data.college_id != user.college_id:
        col = db.get(models.College, data.college_id)
        is_prebet = user.role == models.Role.driver
        if col is None or (not col.transport_available and not is_prebet):
            raise HTTPException(400, "Kolej tak sah atau tiada perkhidmatan pengangkutan")
        user.college_id = col.id
        user.college_other = ""
        db.flush()
        user.pickup_point_id = None   # kolej bertukar: checkpoint lama tak sah lagi
        db.commit()
        svc.reconcile_user(db, user)
    elif not data.college_id and (data.college_other or "").strip() and \
            (user.college_id is not None or user.college_other != data.college_other.strip()):
        user.college_id, user.college_other = None, data.college_other.strip()
        db.commit()
        svc.reconcile_user(db, user)
    if data.pickup_point_id is not None:
        if data.pickup_point_id not in {p.id for p in svc.points_for(db, user)}:
            db.rollback()
            raise HTTPException(400, "Checkpoint itu tidak untuk kolej/jantina anda")
        user.pickup_point_id = data.pickup_point_id
        db.flush()
        for ev_b in db.query(models.Booking).filter(models.Booking.user_id == user.id,
                                                    models.Booking.training_date >= svc.today_my()):
            ev = svc.event_on(db, ev_b.training_date)
            if ev is not None and ev.status == models.EventStatus.open:
                ev_b.pickup_point_id = user.pickup_point_id
    db.commit()
    if user.role == models.Role.driver:
        svc.sync_driver_vehicles(db, user)
    db.refresh(user)
    return user


@router.post("/profile/prebet-request")
def prebet_request(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ahli yang ada kenderaan dan mahu jadi prebet: mohon kelulusan BKK."""
    if user.role != models.Role.member:
        raise HTTPException(400, "Hanya akaun ahli boleh mohon jadi prebet")
    if user.prebet_request:
        raise HTTPException(400, "Permohonan anda sedang menunggu kelulusan BKK")
    user.prebet_request = True
    for a in db.query(models.User).filter_by(role=models.Role.admin, active=True):
        svc._notify(db, a.id, "admin_alert", f"Mohon jadi prebet: {user.name}",
                    f"{user.member_no} ({user.phone}) ada kenderaan dan mohon jadi prebet. Lulus atau tolak di Admin › Lagi.",
                    severity="task", link="/admin?tab=more", ref=f"prebetreq:{user.id}")
    db.commit()
    return {"prebet_request": True}


@router.delete("/profile/prebet-request")
def prebet_request_cancel(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.prebet_request = False
    db.commit()
    return {"prebet_request": False}


class GenderRequestIn(BaseModel):
    gender: models.Gender


@router.post("/profile/gender-request")
def gender_request(data: GenderRequestIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Jantina tersilap? Mohon tukar: perlu kelulusan BKK. Admin dimaklumkan."""
    if data.gender not in (models.Gender.male, models.Gender.female):
        raise HTTPException(400, "Jantina tak sah")
    if user.gender is None:
        raise HTTPException(400, "Jantina belum ditetapkan; pilih terus di Profil")
    if data.gender == user.gender:
        raise HTTPException(400, "Itu jantina anda sekarang")
    user.gender_request = data.gender.value
    lbl = {"male": "Lelaki", "female": "Perempuan"}
    for a in db.query(models.User).filter_by(role=models.Role.admin, active=True):
        svc._notify(db, a.id, "admin_alert", f"Mohon tukar jantina: {user.name}",
                    f"{user.member_no}: {lbl[user.gender.value]} → {lbl[data.gender.value]}. Lulus atau tolak di Admin › Lagi.",
                    severity="task", link="/admin?tab=more", ref=f"genderreq:{user.id}")
    db.commit()
    return {"gender_request": user.gender_request}


@router.delete("/profile/gender-request")
def gender_request_cancel(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.gender_request = ""
    db.commit()
    return {"gender_request": ""}


class ThemeIn(BaseModel):
    theme: str = Field(pattern="^(auto|light|dark)$")


@router.put("/profile/theme")
def set_theme(data: ThemeIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pilihan paparan cerah/gelap disimpan pada akaun (ikut ke peranti lain)."""
    user.theme = data.theme
    db.commit()
    return {"theme": user.theme}


@router.get("/checkpoints")
def my_checkpoints(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Checkpoint yang boleh dipilih ahli + yang sedang digunakan."""
    cur = svc.resolve_point(db, user)
    return {"current": cur.id if cur else None,
            "points": [{"id": p.id, "name": p.name} for p in svc.points_for(db, user)]}


class PreferenceItem(BaseModel):
    session_id: int
    active: bool = True
    going: bool = True
    returning: bool = True


class PreferencesIn(BaseModel):
    items: list[PreferenceItem]


def _serialize(db: Session, user: models.User):
    today = svc.today_my()
    sessions = [s for s in db.query(models.TrainingSession).filter_by(active=True)
                if s.one_off_date is None or s.one_off_date >= today]
    sessions.sort(key=lambda s: (s.one_off_date is not None, s.one_off_date or today, s.day_of_week))
    prefs = {p.session_id: p for p in db.query(models.Preference).filter_by(user_id=user.id)}
    return {
        "eligibility": svc.eligibility(db, user),
        "activity_eligibility": svc.eligibility(db, user, activity=True),
        "sessions": [{
            "session_id": s.id, "session_name": s.name,
            "one_off_date": s.one_off_date.isoformat() if s.one_off_date else None,
            "trip_only": s.trip_only,
            "fee": float(s.activity_fee or 0.0) if s.one_off_date else None,
            "start_time": s.start_time.strftime("%H:%M"), "end_time": s.end_time.strftime("%H:%M"),
            "pickup_window": svc.pickup_window(s),
            "active": bool(prefs.get(s.id) and prefs[s.id].active),
            "going": prefs[s.id].going if s.id in prefs else True,
            "returning": prefs[s.id].returning if s.id in prefs else True,
        } for s in sessions],
    }


@router.get("/transport/preferences")
def get_preferences(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _serialize(db, user)


@router.put("/transport/preferences")
def set_preferences(data: PreferencesIn, user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    sess = {s.id: s for s in db.query(models.TrainingSession).filter_by(active=True)}
    valid = set(sess)
    elig_regular = svc.eligibility(db, user)
    elig_activity = svc.eligibility(db, user, activity=True)
    seen = set()
    for it in data.items:
        if it.session_id not in valid or it.session_id in seen:
            raise HTTPException(400, "Hari latihan tak sah")
        seen.add(it.session_id)
        if it.active:
            elig = elig_activity if sess[it.session_id].one_off_date else elig_regular
            if not elig["eligible"]:
                raise HTTPException(400, elig["reason"])
            if not (it.going or it.returning):
                raise HTTPException(400, "Pilih sekurang-kurangnya pergi atau balik")

    existing = {p.session_id: p for p in db.query(models.Preference).filter_by(user_id=user.id)}
    for it in data.items:
        p = existing.get(it.session_id)
        if p is None:
            p = models.Preference(user_id=user.id, session_id=it.session_id)
            db.add(p)
        p.active, p.going, p.returning = it.active, it.going, it.returning
    db.commit()
    svc.reconcile_user(db, user)
    return _serialize(db, user)


class DateChoice(BaseModel):
    training_date: date
    session_id: int
    going: bool = False
    returning: bool = False   # kedua-duanya false = batal tarikh ini
    pickup: str | None = Field(default=None, pattern="^(kolej|tempat)$")   # aktiviti luar: ambil di kolej atau tempat lain
    place: str = Field(default="", max_length=120)                          # nama tempat (jika pickup = tempat)
    return_pickup: str | None = Field(default=None, pattern="^(kolej|tempat)$")   # tempat hantar balik (kosong = sama dengan pergi)
    return_place: str = Field(default="", max_length=120)


@router.get("/transport/dates")
def get_dates(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Tarikh latihan/aktiviti akan datang untuk dipilih ikut tarikh (selain jadual berulang)."""
    svc.ensure_events(db)
    return svc.date_options(db, user)


@router.put("/transport/dates")
def set_date(data: DateChoice, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        svc.book_date(db, user, data.training_date, data.session_id, data.going, data.returning,
                      pickup=data.pickup, place=data.place,
                      return_pickup=data.return_pickup, return_place=data.return_place)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return svc.date_options(db, user)
