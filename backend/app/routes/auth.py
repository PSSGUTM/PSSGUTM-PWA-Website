import hashlib
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import config, mailer, models
from ..database import get_db
from ..security import create_token, get_current_user, hash_password, rate_limit, verify_password
from ..services import booking as svc

router = APIRouter(prefix="/auth", tags=["auth"])


def clean_phone(v: str) -> str:
    digits = re.sub(r"[^\d+]", "", v)
    if len(digits) < 9:
        raise ValueError("No. telefon tak sah")
    return digits


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    member_no: str = Field(min_length=3, max_length=30)
    phone: str = Field(min_length=9, max_length=20)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # had bcrypt 72 bytes
    gender: models.Gender | None = None
    college_id: int | None = None
    college_code: str | None = None      # cth: KTF (pilihan dalam borang)
    college_other: str | None = Field(default=None, max_length=60)  # 'Lain-lain': tulis nama kolej
    is_driver: bool = False  # daftar sebagai driver (ada kereta): tak tertakluk syarat penumpang
    short_name: str = Field(default="", max_length=40)   # nama pendek (dipaparkan kepada ahli/prebet lain)
    block: str = Field(default="", max_length=40)        # blok / bilik di kolej
    pickup_point_id: int | None = None                   # checkpoint pilihan (jika kolej ada lebih satu)

    @field_validator("member_no")
    @classmethod
    def up(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("phone")
    @classmethod
    def ph(cls, v: str) -> str:
        return clean_phone(v)


class LoginIn(BaseModel):
    identifier: str  # no. ahli atau email
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    short_name: str = ""
    block: str = ""
    pickup_point_id: int | None = None
    member_no: str
    phone: str
    email: str
    role: models.Role
    gender: models.Gender | None = None
    college_id: int | None = None
    college_other: str = ""
    credit_balance: float = 0.0
    is_treasurer: bool = False
    passenger_ok: bool = False
    passenger_request: bool = False
    theme: str = "auto"
    gender_request: str = ""
    prebet_request: bool = False

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit(10, 3600))])
def register(data: RegisterIn, db: Session = Depends(get_db)):
    # 1. Hanya ahli sah (ada dalam senarai ahli) boleh daftar
    roster = db.query(models.MemberRoster).filter_by(member_no=data.member_no, active=True).first()
    if config.REQUIRE_ROSTER and roster is None:
        if not re.match(config.MEMBER_NO_PATTERN, data.member_no):
            raise HTTPException(400, "Format no. ahli tak sah. Contoh yang betul: SG2627001. "
                                     "Pastikan no. ahli ada dalam senarai ahli sah PSSGUTM.")
        raise HTTPException(400, "No. ahli tiada dalam senarai ahli sah PSSGUTM. Sila hubungi BKK.")

    # 2. Jantina & kolej: senarai ahli didahulukan, kemudian input pendaftar
    # Jantina: pilihan pendaftar didahulukan (fail CSV kadang tersalah). Jika berbeza daripada senarai, senarai dikemas kini
    # dan admin dimaklumkan supaya CSV sumber dibetulkan. Jika pendaftar tak pilih, guna jantina dalam senarai.
    ok_g = (models.Gender.male, models.Gender.female)
    gender = data.gender if data.gender in ok_g else (roster.gender if roster and roster.gender in ok_g else None)
    gender_changed_from = None
    if roster is not None and gender in ok_g:
        if roster.gender in ok_g and roster.gender != gender:
            gender_changed_from = roster.gender
        roster.gender = gender
    col = None
    if roster and roster.college_id:
        col = db.get(models.College, roster.college_id)
    elif data.college_code and data.college_code.strip():
        col = db.query(models.College).filter_by(code=data.college_code.strip().upper()).first()
        if col is None:
            raise HTTPException(400, "Kolej tak dikenali")
    elif data.college_id:
        col = db.get(models.College, data.college_id)
    other = (data.college_other or "").strip() if col is None else ""

    # Sesi luar yang dibenarkan (atau prebet/driver) BOLEH daftar & masuk, tetapi tidak boleh menempah.
    can_book = svc.year_ok(db, data.member_no)
    if not data.is_driver and can_book:
        if gender not in (models.Gender.male, models.Gender.female):
            raise HTTPException(400, "Sila pilih jantina")
        if col is None and not other:
            raise HTTPException(400, "Sila pilih kolej (atau pilih Lain-lain dan tulis nama kolej)")
        if col is not None and not col.transport_available:
            raise HTTPException(400, f"Pengangkutan tidak disediakan untuk {col.code}")
    elif (data.is_driver or not can_book) and gender not in (models.Gender.male, models.Gender.female):
        raise HTTPException(400, "Sila pilih jantina (perlu untuk susunan tempat duduk)")

    owner = db.query(models.User).filter(models.User.member_no == data.member_no).first()
    if owner is not None:
        # No. ahli sudah dipakai: sekat, maklumkan pemilik dan admin (mungkin tersilap atau cubaan guna no. orang lain)
        svc._notify(db, owner.id, "security", "Seseorang cuba daftar guna no. ahli anda",
                    f"Cubaan daftar dengan no. {owner.member_no} (emel: {data.email.lower()}). Jika bukan anda, maklumkan BKK.",
                    severity="info", link="")
        for a in db.query(models.User).filter_by(role=models.Role.admin, active=True):
            svc._notify(db, a.id, "admin_alert", f"No. ahli berulang: {owner.member_no}",
                        f"{data.name.strip()} ({data.email.lower()}, {data.phone}) cuba daftar guna no. ahli {owner.name}. Disekat.",
                        severity="task", link="/admin?tab=more", ref=f"dupno:{owner.id}:{data.email.lower()}")
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "No. ahli ini sudah didaftarkan oleh akaun lain. Jika ini no. ahli anda dan anda tak pernah daftar, sila hubungi BKK.")
    if db.query(models.User).filter(models.User.email == data.email.lower()).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Emel ini sudah didaftarkan. Cuba log masuk, atau guna 'Lupa kata laluan'.")

    user = models.User(
        name=data.name.strip(), member_no=data.member_no, phone=data.phone, email=data.email.lower(),
        password_hash=hash_password(data.password),
        role=models.Role.driver if data.is_driver else models.Role.member,  # prebet terus ke bahagian prebet; admin ditetapkan admin
        gender=gender if gender in (models.Gender.male, models.Gender.female) else None,
        college_id=col.id if col else None, college_other=other,
        short_name=data.short_name.strip(), block=data.block.strip(),
    )
    db.add(user)
    db.flush()
    if data.pickup_point_id:
        if data.pickup_point_id not in {p.id for p in svc.points_for(db, user)}:
            db.rollback()
            raise HTTPException(400, "Checkpoint itu tidak untuk kolej/jantina anda")
        user.pickup_point_id = data.pickup_point_id
    if gender_changed_from is not None:
        svc.notify_gender_change(db, user, gender_changed_from, gender, actor=None, how="semasa pendaftaran")
    if data.is_driver:
        svc._notify(db, user.id, "driver", "Lengkapkan profil prebet",
                    "Muat naik gambar lesen dan tarikh tamat di Profil, kemudian daftar kenderaan di tab Kenderaan.",
                    severity="task", link="/profil")
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_token(user.id), user=user)


@router.post("/login", response_model=TokenOut, dependencies=[Depends(rate_limit(10, 60))])
def login(data: LoginIn, db: Session = Depends(get_db)):
    ident = data.identifier.strip()
    user = db.query(models.User).filter(
        or_(models.User.member_no == ident.upper(), models.User.email == ident.lower())).first()
    if user is None or not verify_password(data.password, user.password_hash) or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Maklumat login salah")
    return TokenOut(access_token=create_token(user.id), user=user)


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


@router.put("/password", dependencies=[Depends(rate_limit(10, 3600))])
def change_password(data: PasswordIn, user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Kata laluan semasa salah")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------ lupa kata laluan

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _reset_base_url() -> str:
    if config.FRONTEND_URL:
        return config.FRONTEND_URL
    for o in config.CORS_ORIGINS:
        if o and "localhost" not in o:
            return o.rstrip("/")
    return config.CORS_ORIGINS[0].rstrip("/") if config.CORS_ORIGINS else ""


class ForgotIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=120)  # no. ahli atau email


@router.post("/forgot", dependencies=[Depends(rate_limit(5, 900))])
def forgot_password(data: ForgotIn, db: Session = Depends(get_db)):
    """Minta set semula kata laluan. Jawapan SENTIASA sama (tak dedahkan sama ada akaun wujud).
    Ada emel dikonfigurasi: pautan sekali guna dihantar ke emel akaun. Tiada: admin dimaklumkan dan reset manual."""
    ident = data.identifier.strip()
    user = db.query(models.User).filter(
        or_(models.User.member_no == ident.upper(), models.User.email == ident.lower())).first()
    mode = "email" if mailer.configured() else "admin"
    if user is None or not user.active:
        return {"ok": True, "mode": mode}
    sent = False
    if mode == "email":
        token = secrets.token_urlsafe(32)
        db.query(models.PasswordReset).filter_by(user_id=user.id, used=False).update({"used": True})
        db.add(models.PasswordReset(user_id=user.id, token_hash=_hash_token(token),
                                    expires_at=datetime.utcnow() + timedelta(minutes=config.RESET_TOKEN_MINUTES)))
        link = f"{_reset_base_url()}/reset-password?token={token}"
        sent = mailer.send_mail(
            user.email, "Set semula kata laluan PSSGUTM Transport",
            f"Salam {user.name},\n\nKlik pautan ini untuk tetapkan kata laluan baharu "
            f"(sah {config.RESET_TOKEN_MINUTES} minit, sekali guna):\n{link}\n\n"
            "Jika bukan anda yang meminta, abaikan emel ini.")
        db.commit()
    if not sent:
        # Fallback: maklumkan admin (elak spam: satu notifikasi setiap akaun dalam 30 minit)
        title = f"Lupa kata laluan: {user.name} ({user.member_no})"
        since = datetime.utcnow() - timedelta(minutes=30)
        for a in db.query(models.User).filter_by(role=models.Role.admin, active=True):
            dup = db.query(models.Notification).filter(
                models.Notification.user_id == a.id, models.Notification.title == title,
                models.Notification.created_at >= since).first()
            if dup is None:
                svc._notify(db, a.id, "admin_alert", title,
                            f"Tel: {user.phone}. Admin > Lagi > Pengguna > Reset kata laluan, kemudian beri kata laluan sementara.")
        db.commit()
        mode = "admin"
    return {"ok": True, "mode": mode, "email_configured": mailer.configured(),
            "note": ("Emel belum disediakan pada server; permintaan anda dihantar kepada admin." if not mailer.configured() else
                     "Emel tak dapat dihantar buat masa ini; permintaan anda dihantar kepada admin." if mode == "admin" else "")}


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=8, max_length=72)


@router.post("/reset", dependencies=[Depends(rate_limit(10, 3600))])
def reset_password(data: ResetIn, db: Session = Depends(get_db)):
    row = db.query(models.PasswordReset).filter_by(token_hash=_hash_token(data.token)).first()
    if row is None or row.used or row.expires_at < datetime.utcnow():
        raise HTTPException(400, "Pautan tak sah atau sudah tamat tempoh. Sila minta pautan baharu.")
    user = db.get(models.User, row.user_id)
    if user is None or not user.active:
        raise HTTPException(400, "Pautan tak sah atau sudah tamat tempoh. Sila minta pautan baharu.")
    user.password_hash = hash_password(data.new_password)
    db.query(models.PasswordReset).filter_by(user_id=user.id, used=False).update({"used": True})
    db.commit()
    return {"ok": True}


@router.get("/forgot/info")
def forgot_info():
    """Frontend tahu cara reset yang tersedia (emel automatik atau melalui admin)."""
    return {"mode": "email" if mailer.configured() else "admin"}


class GoogleIn(BaseModel):
    credential: str = Field(min_length=20)
    # Hanya untuk pendaftaran kali pertama (emel Google belum ada akaun)
    name: str | None = None
    member_no: str | None = None
    phone: str | None = None
    gender: models.Gender | None = None
    college_code: str | None = None
    college_other: str | None = Field(default=None, max_length=60)
    is_driver: bool = False
    short_name: str = Field(default="", max_length=40)
    block: str = Field(default="", max_length=40)
    pickup_point_id: int | None = None


@router.get("/formats")
def formats():
    """Format medan untuk borang (dipaparkan sebagai contoh kepada pengguna)."""
    return {"member_no_pattern": config.MEMBER_NO_PATTERN, "member_no_example": "SG2627001"}


@router.get("/google/info")
def google_info():
    return {"client_id": config.GOOGLE_CLIENT_ID}


@router.post("/google", response_model=None, dependencies=[Depends(rate_limit(20, 60))])
def google_login(data: GoogleIn, db: Session = Depends(get_db)):
    """Log masuk dengan Google. Emel padan akaun sedia ada: terus masuk. Emel baru: perlu no. ahli (mesti dalam senarai)."""
    try:
        from .. import google_auth  # import ketika diperlukan: server tak tumbang jika fail ini tertinggal
    except ImportError:
        raise HTTPException(503, "Log masuk Google belum dipasang (fail google_auth.py tiada di server)")
    try:
        info = google_auth.verify(data.credential)
    except google_auth.GoogleAuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))
    user = db.query(models.User).filter(models.User.email == info["email"]).first()
    if user is not None:
        if not user.active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Akaun dinyahaktifkan. Hubungi BKK.")
        return TokenOut(access_token=create_token(user.id), user=user)
    # Emel ada dalam senarai ahli/alumni yang diimport admin: akaun dicipta terus, tiada borang daftar
    from ..models_main import Person
    person = db.query(Person).filter(Person.email == info["email"], Person.active.is_(True)).first()
    if person is not None and not data.member_no:
        col = db.query(models.College).filter_by(code=person.college).first() if person.college else None
        mno = person.member_no or f"P{person.id}"
        if db.query(models.User).filter(models.User.member_no == mno).first():
            mno = f"{mno}-{person.id}"   # no. SSG tidak unik: jadikan unik untuk akaun log masuk
        user = models.User(
            name=person.name, member_no=mno, phone=person.phone or "0000000000", email=info["email"],
            password_hash=hash_password(secrets.token_urlsafe(24)), role=models.Role.member,
            gender=models.Gender(person.gender) if person.gender in ("male", "female") else None,
            college_id=col.id if col else None, college_other="" if col else person.college,
            block=person.block or "")
        db.add(user)
        db.commit()
        db.refresh(user)
        return TokenOut(access_token=create_token(user.id), user=user)
    if not data.member_no or not data.phone:
        return {"needs_registration": True, "email": info["email"], "name": info["name"]}
    try:
        reg = RegisterIn(name=(data.name or info["name"] or "Ahli").strip() or "Ahli", member_no=data.member_no,
                         phone=data.phone, email=info["email"], password=secrets.token_urlsafe(24),
                         gender=data.gender, college_code=data.college_code, college_other=data.college_other,
                         is_driver=data.is_driver, short_name=data.short_name, block=data.block,
                         pickup_point_id=data.pickup_point_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return register(reg, db)   # peraturan senarai ahli, kolej dan checkpoint yang sama dengan pendaftaran biasa
