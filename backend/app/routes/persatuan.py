"""Modul utama PSSGUTM: ahli/alumni, bengkung, jawatan, import, SG->SSG, kehadiran (QR), inventori."""
import csv
import io
import re
import secrets
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, storage
from ..database import get_db
from ..models_main import (AttendRecord, Attendance, BeltHistory, BeltLevel, Biro, Item, Loan, Person, Post)
from ..security import get_current_user, require_admin
from ..services import people as pp
from ..services import booking as svc
from .bookings import save_upload

# Pautan senarai ahli rasmi (untuk rujukan semak nombor ahli)
ROSTER_SHEET_URL = "https://docs.google.com/spreadsheets/d/1RkEQYsnG3n7-_fg98flrrQajSXWy2uYKXW2uVkC8xYE/edit?usp=sharing"


def is_valid_sg_intake(intake: str) -> bool:
    """Semak sama ada kod intake SG sah (4 digit, tahun bersebelahan: yy2 = yy1 + 1).
    Contoh sah:   2425, 2526, 2627, 2728
    Contoh tidak sah: 2626 (sama), 2628 (tak bersebelahan), 2436 (jauh)
    """
    if not intake or len(intake) != 4:
        return False
    try:
        y1, y2 = int(intake[:2]), int(intake[2:])
        return y2 == y1 + 1
    except ValueError:
        return False


def is_valid_sg_no(mno: str) -> bool:
    """Semak sama ada nombor ahli SG sah format dan kod tahun."""
    if not mno:
        return False
    m = re.match(r'^SG(\d{4})(\d{3})$', mno.strip().upper())
    if not m:
        return False
    return is_valid_sg_intake(m.group(1))

router = APIRouter(prefix="/persatuan", tags=["persatuan"])

DEFAULT_BIROS = (("BKK", False, False), ("BIT", False, False), ("BLG", True, False))


def migrate_legacy_members(db: Session) -> None:
    """Salin semua rekod ahli dan prebet sedia ada (MemberRoster & User) ke jadual Person."""
    from ..models import College, MemberRoster, User

    colleges = db.query(College).all()
    code_by_id = {c.id: c.code for c in colleges}

    existing_emails = {p[0].lower() for p in db.query(Person.email).all() if p[0]}
    existing_mno = {p[0].upper() for p in db.query(Person.member_no).all() if p[0]}

    # A. Daripada akaun User sedia ada
    for u in db.query(User).all():
        mno = (u.member_no or "").strip().upper()
        if not mno or mno == "ADMIN":
            continue
        email = (u.email or "").strip().lower()
        if not email:
            continue

        if email in existing_emails or mno in existing_mno:
            p = db.query(Person).filter(func.lower(Person.email) == email).first()
            if not p and mno:
                p = db.query(Person).filter_by(member_no=mno).first()
            if p:
                col_code = code_by_id.get(u.college_id, "")
                if not p.phone and u.phone:
                    p.phone = u.phone
                if not p.block and u.block:
                    p.block = u.block
                if not p.college and col_code:
                    p.college = col_code
                if not p.member_no and mno:
                    p.member_no = mno
        else:
            intake = mno[2:6] if (mno.startswith("SG") and len(mno) >= 6) else ""
            kind = "SSG" if mno.startswith("SSG") else "SG"
            col_code = code_by_id.get(u.college_id, "")
            p_new = Person(
                name=u.name,
                email=email,
                phone=u.phone or "",
                gender=u.gender.value if u.gender else None,
                intake=intake,
                kind=kind,
                member_no=mno,
                college=col_code,
                block=u.block or "",
                active=u.active,
            )
            db.add(p_new)
            existing_emails.add(email)
            existing_mno.add(mno)
    try:
        db.commit()
    except Exception:
        db.rollback()

    # B. Daripada MemberRoster sedia ada (ahli yang belum daftar akaun)
    for r in db.query(MemberRoster).all():
        mno = (r.member_no or "").strip().upper()
        if not mno or mno in existing_mno:
            continue

        candidate_email = f"{mno.lower()}@pssgutm.local"
        if candidate_email in existing_emails:
            candidate_email = f"{mno.lower()}_{r.id}@pssgutm.local"

        intake = mno[2:6] if (mno.startswith("SG") and len(mno) >= 6) else ""
        kind = "SSG" if mno.startswith("SSG") else "SG"
        col_code = code_by_id.get(r.college_id, "")
        p_new = Person(
            name=r.name or mno,
            email=candidate_email,
            gender=r.gender.value if r.gender else None,
            intake=intake,
            kind=kind,
            member_no=mno,
            college=col_code,
            active=r.active,
        )
        db.add(p_new)
        existing_emails.add(candidate_email)
        existing_mno.add(mno)
    try:
        db.commit()
    except Exception:
        db.rollback()


def notify_invalid_member_nos(db: Session) -> None:
    """Scan semua no ahli SG, cari yang tahunnya bukan bersebelahan (cth SG2626xxx, SG2628xxx),
    dan hantar notifikasi kepada pengguna yang mempunyai no ahli tersebut.
    Guard menggunakan Setting supaya notifikasi tidak dihantar berulang kali."""
    from sqlalchemy import or_
    GUARD_KEY = "notified_invalid_sg_no_v1"
    guard = db.get(models.Setting, GUARD_KEY)
    if guard is not None:
        return  # sudah dijalankan sebelum ini

    invalid_persons = [
        p for p in db.query(Person).filter(Person.member_no.like("SG%")).all()
        if p.member_no and not is_valid_sg_no(p.member_no)
    ]

    notified = 0
    for p in invalid_persons:
        mno = (p.member_no or "").strip().upper()
        # Cari User berdaftar
        user = db.query(models.User).filter(
            or_(func.lower(models.User.email) == (p.email or "").strip().lower(),
                models.User.member_no == mno)
        ).first()
        if user:
            svc._notify(
                db,
                user.id,
                "member_no_invalid",
                f"Semak Nombor Ahli Anda: {mno}",
                f"Nombor ahli anda ({mno}) mengandungi ralat susunan tahun (contoh betul: SG2425xxx, SG2627xxx).\n\n"
                f"Adakah anda {p.name}? Jika nombor ini bukan milik asal anda, nombor ahli anda akan dipindahkan ke nombor yang betul, "
                f"dan SEMUA maklumat anda (rekod kehadiran, jawatan biro/MT, bengkung) akan dipindahkan ke nombor baharu tersebut tanpa hilang rekod.\n\n"
                f"Sila buat semakan di senarai rasmi: {ROSTER_SHEET_URL}",
                severity="warning",
                link="/profil-saya",
                ref=f"invalid_sg_{mno}"
            )
            notified += 1

    # Tandakan bahawa semakan ini telah selesai
    db.merge(models.Setting(key=GUARD_KEY, value=f"done:{notified} notified"))
    try:
        db.commit()
    except Exception:
        db.rollback()


def broadcast_member_no_verification_notice(db: Session) -> None:
    """Pastikan notifikasi siaran amaran pengesahan nombor ahli wujud untuk semua ahli."""
    REF_KEY = "verify_member_no_broadcast_v1"
    body_text = (
        "Sila pastikan nombor ahli semasa anda adalah milik asal anda.\n\n"
        "Jika nombor ini bukan milik asal anda (atau berlaku ralat susunan nombor): "
        "nombor ahli anda akan dipindahkan ke nombor yang betul mengikut senarai rasmi, "
        "dan SEMUA maklumat anda (sejarah jawatan biro/MT, rekod kehadiran latihan, bengkung, serta perkhidmatan pengangkutan) "
        "akan dipindahkan sepenuhnya ke nombor baharu tersebut tanpa kehilangan sebarang rekod.\n\n"
        f"Semak senarai rasmi ahli di: {ROSTER_SHEET_URL}"
    )
    existing = db.query(models.Notification).filter_by(user_id=None, ref=REF_KEY).first()
    if existing is None:
        db.add(models.Notification(
            user_id=None,
            kind="member_no_verify",
            title="Pengesahan Nombor Ahli PSSGUTM",
            body=body_text[:500],
            severity="warning",
            link="/profil-saya",
            ref=REF_KEY
        ))
    else:
        existing.title = "Pengesahan Nombor Ahli PSSGUTM"
        existing.body = body_text[:500]
        existing.severity = "warning"
        existing.link = "/profil-saya"
    try:
        db.commit()
    except Exception:
        db.rollback()


def sync_canonical_roster_and_dedup(db: Session) -> None:
    """Penyelarasan tepat senarai ahli Person & MemberRoster berasaskan fail rasmi roster_official.csv (203 ahli).
    - Menghapuskan sebarang sesi 2626 (tidak wujud).
    - Memulihkan nama-nama yang hilang / terpadam (cth: SG2425024 Muhammad Aliuddin Bin Mohd Anuar).
    - Membetulkan kes tertukar Amirul Aiman (SG2425025) vs Aliuddin (SG2425024).
    - Menghapuskan semua rekod duplikasi Person & MemberRoster (cth 2x Haaziq Syahmi, 2x Amirul Aiman).
    - Memindahkan relasi ForeignKey (Post, AttendRecord, BeltHistory, Loan) ke rekod master sebelum menghapus duplikasi.
    - Menyelaraskan User berdaftar ke rekod Person kanonikal."""
    import os, csv
    from sqlalchemy import or_

    try:
        csv_candidates = [
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "roster_official.csv"),
            os.path.join(os.getcwd(), "backend", "app", "data", "roster_official.csv"),
            os.path.join(os.getcwd(), "app", "data", "roster_official.csv"),
        ]
        csv_path = next((p for p in csv_candidates if os.path.exists(p)), None)
        if not csv_path:
            return

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            official_rows = list(reader)

        canonical_map: dict[str, dict[str, str]] = {}
        for r in official_rows:
            mno = (r.get("no ahli") or r.get("member_no") or "").strip().upper()
            name = (r.get("nama") or r.get("name") or "").strip().upper()
            gender = (r.get("jantina") or r.get("gender") or "L").strip().upper()
            if not mno:
                continue
            intake = mno[2:6] if (mno.startswith("SG") and len(mno) >= 6) else ""
            canonical_map[mno] = {
                "name": name,
                "gender": "P" if gender == "P" else "L",
                "intake": intake,
            }
        canonical_mnos = set(canonical_map.keys())

        # A. Disambiguate placeholder emails so there are no unique constraint clashes during sync
        for p in db.query(Person).all():
            if p.email and p.email.endswith("@pssgutm.local"):
                p.email = f"{p.member_no.lower()}_{p.id}@pssgutm.local" if p.member_no else f"person_{p.id}@pssgutm.local"
        db.flush()

        # B. Selaraskan sesi 2626 -> 2627 untuk sebarang rekod Person atau Post yang lama
        for p in db.query(Person).filter((Person.intake == "2626") | (Person.member_no.like("SG2626%"))).all():
            p.intake = "2627"
            if p.member_no and p.member_no.startswith("SG2626"):
                seq = p.member_no[6:] if len(p.member_no) >= 7 else "006"
                p.member_no = f"SG2627{seq}"

        for post in db.query(Post).filter(Post.session == "2626").all():
            post.session = "2627"

        # C. Selaraskan User Amirul Aiman
        amirul_user = db.query(models.User).filter(func.lower(models.User.email) == "amirul-05@graduate.utm.my").first()
        if amirul_user:
            amirul_user.member_no = "SG2425025"
            amirul_user.gender = models.Gender.male
            amirul_user.phone = amirul_user.phone or "0192278390"

        # D. Selaraskan setiap ahli kanonikal (203 ahli)
        for mno, info in canonical_map.items():
            # Padankan terutamanya mengikut member_no
            candidates = db.query(Person).filter_by(member_no=mno).all()
            if not candidates:
                # Jika tiada yang memegang member_no ini, cari mengikut nama yang belum terikat dengan no kanonikal lain
                by_name = db.query(Person).filter(
                    func.upper(Person.name) == info["name"],
                    (Person.member_no.is_(None)) | (~Person.member_no.in_(canonical_mnos))
                ).all()
                if by_name:
                    candidates = by_name

            if candidates:
                # Pilih rekod master tunggal
                if mno == "SG2425025":
                    master = next((c for c in candidates if (c.email or "").lower() == "amirul-05@graduate.utm.my"), candidates[0])
                else:
                    master = next((c for c in candidates if c.email and not c.email.endswith("@pssgutm.local")), candidates[0])

                # Gabungkan dan pindahkan rekod duplikasi ke master
                for dup in candidates:
                    if dup.id == master.id:
                        continue

                    # 1. Pindahkan Post
                    for p_post in db.query(Post).filter_by(person_id=dup.id).all():
                        existing_post = db.query(Post).filter_by(
                            person_id=master.id, session=p_post.session, title=p_post.title
                        ).first()
                        if existing_post:
                            db.delete(p_post)
                        else:
                            p_post.person_id = master.id

                    # 2. Pindahkan AttendRecord
                    for p_att in db.query(AttendRecord).filter_by(person_id=dup.id).all():
                        existing_att = db.query(AttendRecord).filter_by(
                            person_id=master.id, attendance_id=p_att.attendance_id
                        ).first()
                        if existing_att:
                            db.delete(p_att)
                        else:
                            p_att.person_id = master.id

                    # 3. Pindahkan BeltHistory
                    for p_belt in db.query(BeltHistory).filter_by(person_id=dup.id).all():
                        existing_belt = db.query(BeltHistory).filter_by(
                            person_id=master.id, belt_id=p_belt.belt_id
                        ).first()
                        if existing_belt:
                            db.delete(p_belt)
                        else:
                            p_belt.person_id = master.id

                    # 4. Pindahkan Loan
                    for p_loan in db.query(Loan).filter_by(person_id=dup.id).all():
                        p_loan.person_id = master.id

                    # Padam rekod Person duplikasi
                    db.delete(dup)

                master.name = info["name"]
                master.member_no = mno
                master.gender = info["gender"]
                master.intake = info["intake"]
                master.kind = "SG"
                master.active = True
                if not master.email or master.email.endswith("@pssgutm.local"):
                    master.email = f"{mno.lower()}@pssgutm.local"
            else:
                # Wujudkan rekod Person baharu jika tiada (memulihkan ahli hilang)
                master = Person(
                    name=info["name"],
                    member_no=mno,
                    gender=info["gender"],
                    intake=info["intake"],
                    kind="SG",
                    email=f"{mno.lower()}@pssgutm.local",
                    active=True,
                )
                db.add(master)

            if mno == "SG2425025":
                master.email = "amirul-05@graduate.utm.my"
                master.phone = "0192278390"
                master.college = "KTC"

            if mno == "SG2425024":
                master.name = "MUHAMMAD ALIUDDIN BIN MOHD ANUAR"
                if master.email == "amirul-05@graduate.utm.my":
                    master.email = "aliuddin@pssgutm.local"

        # D. Pastikan Aliuddin (SG2425024) dan Amirul Aiman (SG2425025) tidak bersilang
        p24 = db.query(Person).filter_by(member_no="SG2425024").first()
        p25 = db.query(Person).filter_by(member_no="SG2425025").first()
        if p24 and p25 and p24.id != p25.id:
            for post in db.query(Post).filter_by(person_id=p24.id).all():
                if "kebajikan" in (post.title or "").lower() or post.biro_id == 5:
                    existing = db.query(Post).filter_by(person_id=p25.id, session=post.session, title=post.title).first()
                    if existing:
                        db.delete(post)
                    else:
                        post.person_id = p25.id
            for att_rec in db.query(AttendRecord).filter_by(person_id=p24.id).all():
                existing_att = db.query(AttendRecord).filter_by(attendance_id=att_rec.attendance_id, person_id=p25.id).first()
                if existing_att:
                    db.delete(att_rec)
                else:
                    att_rec.person_id = p25.id

        # E. Selaraskan User berdaftar ke Person kanonikal (termasuk nama)
        for u in db.query(models.User).filter(models.User.role != models.Role.admin).all():
            u_email = (u.email or "").strip().lower()
            if not u_email:
                continue
            p = db.query(Person).filter(func.lower(Person.email) == u_email).first()
            if not p and u.member_no:
                p = db.query(Person).filter_by(member_no=u.member_no).first()
            if p:
                # Kemaskini nama User supaya ikut nama kanonikal (buang matric number dll)
                if p.name and p.name.strip() and u.name != p.name:
                    u.name = p.name
                if u.member_no and p.member_no and u.member_no != p.member_no:
                    u.member_no = p.member_no
                if u.phone and not p.phone:
                    p.phone = u.phone
                if not p.email or p.email.endswith("@pssgutm.local"):
                    p.email = u_email
            elif u.member_no:
                p_mno = db.query(Person).filter_by(member_no=u.member_no).first()
                if p_mno and (p_mno.email.endswith("@pssgutm.local") or not p_mno.email):
                    p_mno.email = u_email

        # F. Selaraskan jadual MemberRoster (203 rekod unik)
        for mno, info in canonical_map.items():
            rosters = db.query(models.MemberRoster).filter_by(member_no=mno).all()
            g_enum = models.Gender.male if info["gender"] == "L" else models.Gender.female
            if rosters:
                master_r = rosters[0]
                master_r.name = info["name"]
                master_r.gender = g_enum
                master_r.active = True
                for dup_r in rosters[1:]:
                    db.delete(dup_r)
            else:
                db.add(models.MemberRoster(
                    member_no=mno,
                    name=info["name"],
                    gender=g_enum,
                    active=True,
                ))

        for r in db.query(models.MemberRoster).filter(models.MemberRoster.member_no.like("SG%")).all():
            if r.member_no not in canonical_mnos or r.member_no.startswith("SG2626"):
                db.delete(r)

        for p in db.query(Person).filter(Person.kind == "SG", Person.member_no.like("SG2626%")).all():
            db.delete(p)

        db.commit()
    except Exception:
        db.rollback()


def ensure_seed(db: Session) -> None:
    """Biro asas dan penyelarasan awal. Dijalankan setiap deploy, selamat diulang."""
    try:
        if db.query(Biro).count() == 0:
            for name, att, inv in DEFAULT_BIROS:
                db.add(Biro(name=name, can_attendance=att, can_inventory=inv))
            db.commit()
    except Exception:
        db.rollback()

    # 1. Pastikan brand_name ialah PSSGUTM
    try:
        bname = db.get(models.Setting, "brand_name")
        if bname is not None and "transport" in (bname.value or "").lower():
            bname.value = "PSSGUTM"
            db.commit()
        elif bname is None:
            db.merge(models.Setting(key="brand_name", value="PSSGUTM"))
            db.commit()
    except Exception:
        db.rollback()

    # 2. Migrasi ahli daripada MemberRoster & User ke Person
    try:
        migrate_legacy_members(db)
    except Exception:
        db.rollback()

    # 3. Semak dan notifikasi ahli yang ada nombor ahli tidak sah (tahun bukan bersebelahan)
    try:
        notify_invalid_member_nos(db)
    except Exception:
        db.rollback()

    # 4. Notifikasi broadcast pengesahan nombor ahli untuk semua pengguna
    try:
        broadcast_member_no_verification_notice(db)
    except Exception:
        db.rollback()

    # 5. Penyelarasan penuh ahli & direktori berasaskan fail rasmi 203 ahli
    try:
        sync_canonical_roster_and_dedup(db)
    except Exception:
        db.rollback()

    # 6. Pastikan akaun Admin BKK wujud & aktif berdasarkan ADMIN_EMAIL di env
    try:
        ensure_admin_user(db)
    except Exception:
        db.rollback()


def ensure_admin_user(db: Session) -> None:
    """Pastikan kedua-dua emel admin (persatuan + developer) diangkat terus menjadi Admin."""
    import os, secrets
    from ..security import hash_password

    raw = os.getenv("ADMIN_EMAILS") or os.getenv("ADMIN_EMAIL") or ""
    # Hardcode kedua-dua: emel persatuan + emel peribadi developer
    hardcoded = {"pssgutm@gmail.com", "muhammadamirulaiman0808@gmail.com"}
    admin_emails = list(hardcoded | {e.strip().strip("\"'").lower() for e in raw.split(",") if e.strip()})

    admin_password = os.getenv("ADMIN_PASSWORD")

    for a_email in admin_emails:
        # Cari user sedia ada dengan emel ini
        u = db.query(models.User).filter(func.lower(models.User.email) == a_email).first()
        if u:
            # Dah ada — angkat sahaja ke admin
            u.role = models.Role.admin
            u.active = True
        else:
            # Belum ada akaun — buat baru dengan member_no unik
            # Admin tak perlu member_no sah — guna ADM_XXXXXX
            mno = f"ADM_{secrets.token_hex(4).upper()}"
            # Pastikan tiada clash (walaupun sangat jarang)
            while db.query(models.User).filter_by(member_no=mno).first():
                mno = f"ADM_{secrets.token_hex(4).upper()}"

            name = "Admin PSSGUTM" if "pssgutm" in a_email else "Developer PSSGUTM"
            db.add(models.User(
                name=name,
                member_no=mno,
                phone="0000000000",
                email=a_email,
                password_hash=hash_password(admin_password or secrets.token_urlsafe(16)),
                role=models.Role.admin,
                active=True,
            ))
    db.commit()


# ---------------------------------------------------------------- bantuan

def person_of(db: Session, user: models.User) -> Person | None:
    if user.email:
        p = db.query(Person).filter(func.lower(Person.email) == user.email.strip().lower()).first()
        if p:
            return p
    if user.member_no:
        p = db.query(Person).filter_by(member_no=user.member_no.strip().upper()).first()
        if p:
            return p
    return None


def is_persatuan_admin(db: Session, user: models.User) -> bool:
    """Admin utama (role == admin) ATAU pemegang jawatan aktif dalam Majlis Tertinggi (MT) / mana-mana Biro."""
    if user.role == models.Role.admin:
        return True
    p = person_of(db, user)
    if p is None:
        return False
    cur_sess = pp.session_now(db, svc.today_my())
    # Semak sama ada orang ini memegang sebarang jawatan aktif (MT atau Biro)
    has_post = db.query(Post).filter(
        Post.person_id == p.id,
        Post.current.is_(True),
        (Post.session == cur_sess) | (Post.session == "") | (Post.session.is_(None))
    ).first()
    if not has_post:
        has_post = db.query(Post).filter_by(person_id=p.id, current=True).first()
    return has_post is not None


def require_persatuan_admin(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)) -> models.User:
    if not is_persatuan_admin(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya admin atau MT/Biro yang dibenarkan")
    return user


def can(db: Session, user: models.User, flag: str) -> bool:
    """Admin utama dan MT/Biro sentiasa boleh. Selain itu: semak flag kebenaran biro."""
    if user.role == models.Role.admin or is_persatuan_admin(db, user):
        return True
    p = person_of(db, user)
    if p is None:
        return False
    cur_sess = pp.session_now(db, svc.today_my())
    if flag == "can_attendance":      # semua pemegang jawatan semasa (jawatankuasa = MT + biro + seki) boleh ambil kehadiran
        return db.query(Post).filter_by(person_id=p.id, session=cur_sess, current=True).first() is not None
    for post in db.query(Post).filter_by(person_id=p.id, session=cur_sess, current=True):
        if not post.biro_id:  # Majlis Tertinggi (MT) ada akses penuh (kehadiran & inventori)
            return True
        b = db.get(Biro, post.biro_id) if post.biro_id else None
        while b is not None:
            if getattr(b, flag):
                return True
            b = db.get(Biro, b.parent_id) if b.parent_id else None
    return False


def need(flag: str):
    def dep(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
        if not can(db, user, flag):
            raise HTTPException(403, "Tiada kebenaran")
        return user
    return dep


def _belt_name(db, p):
    b = db.get(BeltLevel, p.belt_id) if p.belt_id else None
    return b.name if b else ""


def person_out(db, p: Person, today: date | None = None) -> dict:
    today = today or svc.today_my()
    return {"id": p.id, "name": p.name, "email": p.email, "phone": p.phone, "gender": p.gender,
            "intake": p.intake, "intake_label": pp.session_label(p.intake) if pp.valid_session(p.intake) else "",
            "kind": p.kind, "member_no": p.member_no,
            "study_end": p.study_end.isoformat() if p.study_end else None, "study_level": p.study_level,
            "college": p.college, "block": p.block, "is_coach": p.is_coach,
            "belt_id": p.belt_id, "belt": _belt_name(db, p),
            "belt_date": p.belt_date.isoformat() if p.belt_date else None, "note": p.note, "active": p.active,
            "due": pp.due_for_conversion(p.kind, p.study_end, today)}


def _posts_out(db, person_id):
    out = []
    for x in db.query(Post).filter_by(person_id=person_id).order_by(Post.id.desc()):
        b = db.get(Biro, x.biro_id) if x.biro_id else None
        parent = db.get(Biro, b.parent_id) if b and b.parent_id else None
        out.append({"id": x.id, "session": x.session, "label": pp.session_label(x.session), "level": x.level,
                    "biro": (parent.name if parent else (b.name if b else "")),
                    "seki": (b.name if parent else ""), "title": x.title, "current": x.current})
    return out


# ---------------------------------------------------------------- saya

@router.get("/me")
def me(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = person_of(db, user)
    n = db.query(AttendRecord).filter_by(person_id=p.id).count() if p else 0
    is_admin = is_persatuan_admin(db, user)
    return {"person": person_out(db, p) if p else None, "posts": _posts_out(db, p.id) if p else [],
            "attended": n,
            "perms": {"admin": is_admin, "attendance": can(db, user, "can_attendance") or is_admin,
                      "inventory": can(db, user, "can_inventory") or is_admin}}


@router.get("/me/belts")
def my_belts(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = person_of(db, user)
    if not p or p.kind != "SG":
        return []
    rows = db.query(BeltHistory).filter_by(person_id=p.id).order_by(BeltHistory.id.desc())
    out = []
    for h in rows:
        b = db.get(BeltLevel, h.belt_id) if h.belt_id else None
        out.append({"belt": b.name if b else "", "date": h.on_date.isoformat() if h.on_date else None})
    return out


# ---------------------------------------------------------------- bengkung

class BeltIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.get("/belts")
def list_belts(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": b.id, "name": b.name, "rank": b.rank}
            for b in db.query(BeltLevel).order_by(BeltLevel.rank, BeltLevel.id)]


@router.post("/belts", dependencies=[Depends(require_persatuan_admin)])
def add_belt(data: BeltIn, db: Session = Depends(get_db)):
    name = data.name.strip()
    if db.query(BeltLevel).filter(func.lower(BeltLevel.name) == name.lower()).first():
        raise HTTPException(409, "Nama bengkung itu sudah ada")
    top = db.query(func.max(BeltLevel.rank)).scalar()
    b = BeltLevel(name=name, rank=(top if top is not None else -1) + 1)
    db.add(b)
    db.commit()
    return {"id": b.id}


@router.put("/belts/order", dependencies=[Depends(require_persatuan_admin)])
def order_belts(ids: list[int], db: Session = Depends(get_db)):
    for i, bid in enumerate(ids):
        b = db.get(BeltLevel, bid)
        if b:
            b.rank = i
    db.commit()
    return {"ok": True}


@router.put("/belts/{bid}", dependencies=[Depends(require_persatuan_admin)])
def rename_belt(bid: int, data: BeltIn, db: Session = Depends(get_db)):
    b = db.get(BeltLevel, bid)
    if b is None:
        raise HTTPException(404, "Tak jumpa")
    name = data.name.strip()
    other = db.query(BeltLevel).filter(func.lower(BeltLevel.name) == name.lower(), BeltLevel.id != bid).first()
    if other:
        raise HTTPException(409, "Nama bengkung itu sudah ada")
    b.name = name
    db.commit()
    return {"ok": True}


@router.delete("/belts/{bid}", dependencies=[Depends(require_persatuan_admin)])
def delete_belt(bid: int, db: Session = Depends(get_db)):
    if db.query(Person).filter_by(belt_id=bid).count():
        raise HTTPException(400, "Masih ada ahli pada peringkat ini. Tukar peringkat mereka dahulu.")
    b = db.get(BeltLevel, bid)
    if b:
        db.query(BeltHistory).filter_by(belt_id=bid).delete()
        db.delete(b)
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- ahli & alumni

class PersonIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=120)
    phone: str = ""
    gender: str | None = None
    intake: str
    kind: str = "SG"
    member_no: str = ""
    study_end: date | None = None
    study_level: str = ""
    college: str = ""
    block: str = ""
    is_coach: bool = False
    belt_id: int | None = None
    belt_date: date | None = None
    note: str = ""
    active: bool = True


def _apply(db, p: Person, d: PersonIn, existing_sg: set[str]):
    if not pp.valid_session(d.intake):
        raise HTTPException(400, "Sesi masuk tak sah (4 digit, cth 2425)")
    if d.kind not in ("SG", "SSG"):
        raise HTTPException(400, "Jenis mesti SG atau SSG")
    if not pp.EMAIL_RE.match(d.email.strip()):
        raise HTTPException(400, "Emel tak sah")
    if d.kind == "SG" and d.gender not in ("male", "female"):
        raise HTTPException(400, "Jantina diperlukan untuk ahli semasa")
    old_kind, old_intake = p.kind, p.intake
    p.name = d.name.strip(); p.email = d.email.strip().lower(); p.phone = pp.clean_phone(d.phone)
    p.gender = d.gender; p.intake = d.intake; p.kind = d.kind
    p.study_end = d.study_end if d.kind == "SG" else None
    p.study_level = d.study_level.strip(); p.college = d.college.strip().upper(); p.block = d.block.strip()
    p.is_coach = d.is_coach; p.note = d.note.strip(); p.active = d.active
    if d.belt_id is not None and db.get(BeltLevel, d.belt_id) is None:
        raise HTTPException(400, "Peringkat bengkung tak wujud")
    if d.kind == "SSG":      # alumni: bengkung tidak disimpan
        d.belt_id, d.belt_date = None, None
    p.belt_id, p.belt_date = d.belt_id, d.belt_date
    if d.member_no and d.member_no.strip():
        p.member_no = d.member_no.strip().upper()
    elif not p.member_no or old_kind != p.kind or old_intake != p.intake:
        if p.kind == "SSG":
            p.member_no = pp.ssg_no(p.intake)
        else:
            p.member_no = pp.next_sg_no(p.intake, existing_sg)
            existing_sg.add(p.member_no)


def _sg_numbers(db) -> set[str]:
    return {n for (n,) in db.query(Person.member_no).filter(Person.member_no.like("SG%")) if n}


def sync_person_to_roster(db: Session, p: Person, old_mno: str | None = None):
    """Selaraskan rekod Person ke MemberRoster (Transport) dan User jika ada perubahan nombor ahli."""
    try:
        if not p.member_no or p.kind != "SG":
            return
        mno = p.member_no.strip().upper()
        col = db.query(models.College).filter_by(code=p.college.upper()).first() if p.college else None

        # Jika nombor ahli berubah daripada nombor lama
        if old_mno and old_mno.strip().upper() != mno:
            old_upper = old_mno.strip().upper()
            old_r = db.query(models.MemberRoster).filter_by(member_no=old_upper).first()
            if old_r:
                existing_new_r = db.query(models.MemberRoster).filter_by(member_no=mno).first()
                if existing_new_r:
                    db.delete(old_r)
                else:
                    old_r.member_no = mno

            # Kemas kini akaun User berdaftar dan hantar notifikasi
            from sqlalchemy import or_
            user = db.query(models.User).filter(
                or_(func.lower(models.User.email) == (p.email or "").strip().lower(),
                    models.User.member_no == old_upper)
            ).first()
            if user and user.member_no != mno:
                prev_user_mno = user.member_no
                # Elak pertembungan unique constraint pada User.member_no
                clash_user = db.query(models.User).filter_by(member_no=mno).first()
                if clash_user and clash_user.id != user.id:
                    clash_user.member_no = f"{mno}_old_{clash_user.id}"
                    db.flush()
                user.member_no = mno
                svc._notify(
                    db,
                    user.id,
                    "member_no",
                    f"Nombor Ahli Dipindahkan: {prev_user_mno} → {mno}",
                    f"Nombor ahli PSSGUTM anda telah dipindahkan daripada {prev_user_mno} kepada {mno}.\n\n"
                    f"Adakah anda {p.name}? Jika nombor lama ({prev_user_mno}) bukan milik asal anda, "
                    f"semua maklumat dan rekod anda (rekod jawatan biro/MT, kehadiran latihan, bengkung, serta perkhidmatan pengangkutan) "
                    f"telah dipindahkan secara automatik ke nombor ahli baharu ({mno}) tanpa sebarang rekod yang hilang.\n\n"
                    f"Sila buat semakan di senarai rasmi ahli PSSGUTM:\n{ROSTER_SHEET_URL}\n\n"
                    f"Sila gunakan nombor ahli baharu ({mno}) untuk sebarang urusan dan log masuk.",
                    severity="warning",
                    link="/profil-saya",
                    ref=f"mno_change_{mno}"
                )

        r = db.query(models.MemberRoster).filter_by(member_no=mno).first()
        if r is None:
            r = models.MemberRoster(member_no=mno)
            db.add(r)
        r.name = p.name or r.name
        if p.gender in ("male", "female"):
            r.gender = models.Gender(p.gender)
        if col:
            r.college_id = col.id
        r.active = p.active
    except Exception:
        pass


@router.get("/people", dependencies=[Depends(require_persatuan_admin)])
def list_people(q: str = "", kind: str = "", due: bool = False, limit: int = 300, offset: int = 0,
                db: Session = Depends(get_db)):
    if db.query(Person).count() == 0:
        migrate_legacy_members(db)

    qs = db.query(Person)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        qs = qs.filter(func.lower(Person.name).like(like) | func.lower(Person.email).like(like)
                       | func.lower(Person.member_no).like(like))
    if kind in ("SG", "SSG"):
        qs = qs.filter(Person.kind == kind)
    total = qs.count()
    rows = qs.order_by(func.lower(Person.name)).offset(max(offset, 0)).limit(min(max(limit, 1), 500)).all()
    today = svc.today_my()
    items = [person_out(db, p, today) for p in rows]
    if due:
        items = [i for i in items if i["due"]]
    return {"total": total, "items": items}


@router.get("/people/search")
def search_people(q: str = "", user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Carian ringkas (nama) untuk kehadiran manual dan pinjaman: pengurus kehadiran/inventori sahaja."""
    if not (can(db, user, "can_attendance") or can(db, user, "can_inventory")):
        raise HTTPException(403, "Tiada kebenaran")
    if len(q.strip()) < 2:
        return []
    like = f"%{q.strip().lower()}%"
    rows = (db.query(Person).filter(Person.active.is_(True), func.lower(Person.name).like(like))
            .order_by(func.lower(Person.name)).limit(20).all())
    return [{"id": p.id, "name": p.name, "member_no": p.member_no, "kind": p.kind} for p in rows]


@router.post("/people", dependencies=[Depends(require_persatuan_admin)])
def create_person(data: PersonIn, db: Session = Depends(get_db)):
    if db.query(Person).filter(func.lower(Person.email) == data.email.strip().lower()).first():
        raise HTTPException(409, "Emel itu sudah ada dalam senarai")
    p = Person()
    db.add(p)
    sg = _sg_numbers(db)
    _apply(db, p, data, sg)
    db.flush()
    if p.belt_id:
        db.add(BeltHistory(person_id=p.id, belt_id=p.belt_id, on_date=p.belt_date))
    sync_person_to_roster(db, p)
    db.commit()
    return person_out(db, p)


@router.put("/people/{pid}", dependencies=[Depends(require_persatuan_admin)])
def update_person(pid: int, data: PersonIn, db: Session = Depends(get_db)):
    p = db.get(Person, pid)
    if p is None:
        raise HTTPException(404, "Tak jumpa")
    other = db.query(Person).filter(func.lower(Person.email) == data.email.strip().lower(), Person.id != pid).first()
    if other:
        raise HTTPException(409, "Emel itu dipakai rekod lain")
    old_mno = p.member_no
    prev = (p.belt_id, p.belt_date)
    _apply(db, p, data, _sg_numbers(db))
    if p.belt_id and (p.belt_id, p.belt_date) != prev:
        db.add(BeltHistory(person_id=p.id, belt_id=p.belt_id, on_date=p.belt_date))
    sync_person_to_roster(db, p, old_mno=old_mno)
    db.commit()
    return person_out(db, p)


@router.get("/people/{pid}", dependencies=[Depends(require_persatuan_admin)])
def get_person(pid: int, db: Session = Depends(get_db)):
    p = db.get(Person, pid)
    if p is None:
        raise HTTPException(404, "Tak jumpa")
    return {"person": person_out(db, p), "posts": _posts_out(db, pid),
            "attended": db.query(AttendRecord).filter_by(person_id=pid).count()}


@router.delete("/people/{pid}", dependencies=[Depends(require_persatuan_admin)])
def delete_person(pid: int, db: Session = Depends(get_db)):
    p = db.get(Person, pid)
    if p is None:
        raise HTTPException(404, "Tak jumpa")
    db.query(BeltHistory).filter_by(person_id=pid).delete()
    db.query(Post).filter_by(person_id=pid).delete()
    db.query(AttendRecord).filter_by(person_id=pid).delete()
    db.query(Loan).filter_by(person_id=pid).delete()
    db.delete(p)
    db.commit()
    return {"ok": True, "id": pid}


# ---------------------------------------------------------------- SG -> SSG

class ConvertIn(BaseModel):
    action: str                 # convert | extend
    new_end: date | None = None


@router.get("/conversions", dependencies=[Depends(require_persatuan_admin)])
def conversions(db: Session = Depends(get_db)):
    today = svc.today_my()
    rows = (db.query(Person).filter(Person.kind == "SG", Person.study_end.isnot(None), Person.study_end <= today,
                                    Person.active.is_(True)).order_by(Person.study_end, func.lower(Person.name)))
    return [person_out(db, p, today) for p in rows]


@router.post("/conversions/{pid}", dependencies=[Depends(require_persatuan_admin)])
def convert(pid: int, data: ConvertIn, db: Session = Depends(get_db)):
    p = db.get(Person, pid)
    if p is None or p.kind != "SG":
        raise HTTPException(404, "Ahli semasa tak jumpa")
    if data.action == "convert":
        p.kind = "SSG"
        p.member_no = pp.ssg_no(p.intake)
        p.study_end = None
        p.belt_id, p.belt_date = None, None            # alumni: bengkung tidak disimpan
        db.query(BeltHistory).filter_by(person_id=p.id).delete()
    elif data.action == "extend":
        if data.new_end is None or data.new_end <= svc.today_my():
            raise HTTPException(400, "Tarikh tamat baharu mesti selepas hari ini")
        p.study_end = data.new_end
    else:
        raise HTTPException(400, "Tindakan tak sah")
    db.commit()
    return person_out(db, p)


# ---------------------------------------------------------------- import Excel

@router.post("/import", dependencies=[Depends(require_persatuan_admin)])
async def import_xlsx(file: UploadFile = File(...), dry_run: bool = Form(True), db: Session = Depends(get_db)):
    raw = await file.read(8_000_001)
    if len(raw) > 8_000_000:
        raise HTTPException(413, "Fail terlalu besar")
    try:
        parsed = pp.parse_workbook(raw)
    except Exception:
        raise HTTPException(400, "Fail tak boleh dibaca. Guna format-import-PSSGUTM.xlsx (.xlsx).")
    stats = {"belts_new": 0, "people_new": 0, "people_updated": 0, "posts_new": 0, "belts_created_from_people": 0}

    # bengkung (ikut susunan dalam fail: bawah ke atas)
    def belt_get(name: str, create_flag: str | None = None):
        row = db.query(BeltLevel).filter(func.lower(BeltLevel.name) == name.lower()).first()
        if row is None:
            top = db.query(func.max(BeltLevel.rank)).scalar()
            row = BeltLevel(name=name, rank=(top if top is not None else -1) + 1)
            db.add(row)
            db.flush()
            stats[create_flag or "belts_new"] += 1
        return row

    for b in parsed["belts"]:
        belt_get(b["name"])

    sg = _sg_numbers(db)
    by_email = {}
    for rec in parsed["members"] + parsed["alumni"]:
        p = db.query(Person).filter(func.lower(Person.email) == rec["email"]).first()
        new = p is None
        if new:
            p = Person(email=rec["email"], name=rec["name"], intake=rec["intake"], kind=rec["kind"])
            db.add(p)
        old = (p.kind, p.intake)
        p.name, p.phone, p.gender = rec["name"], rec["phone"] or p.phone, rec["gender"] or p.gender
        p.intake, p.kind, p.study_end = rec["intake"], rec["kind"], rec["study_end"]
        p.study_level, p.college, p.block = rec["study_level"], rec["college"], rec["block"]
        p.is_coach, p.note = rec["is_coach"], rec["note"]
        if not p.member_no or old != (p.kind, p.intake):
            if p.kind == "SSG":
                p.member_no = pp.ssg_no(p.intake)
            else:
                p.member_no = pp.next_sg_no(p.intake, sg)
                sg.add(p.member_no)
        if rec["belt"] and rec["belt"].lower() != "tidak diketahui":
            belt = belt_get(rec["belt"], "belts_created_from_people")
            if p.belt_id != belt.id or p.belt_date != rec["belt_date"]:
                p.belt_id, p.belt_date = belt.id, rec["belt_date"]
                db.flush()
                db.add(BeltHistory(person_id=p.id, belt_id=belt.id, on_date=rec["belt_date"]))
        db.flush()
        by_email[rec["email"]] = p
        stats["people_new" if new else "people_updated"] += 1

    latest = max((pp.session_year(x["session"]) for x in parsed["posts"]), default=0)
    errors = list(parsed["errors"])
    for x in parsed["posts"]:
        p = by_email.get(x["email"]) or db.query(Person).filter(func.lower(Person.email) == x["email"]).first()
        if p is None:
            errors.append({"sheet": pp.SHEET_POSTS, "row": x["row"], "msg": f"Emel tiada dalam senarai ahli/alumni: {x['email']}"})
            continue
        biro = db.query(Biro).filter(func.lower(Biro.name) == x["biro"].lower()).first()
        if biro is None:
            biro = Biro(name=x["biro"])
            db.add(biro)
            db.flush()
        target = biro
        if x["seki"]:
            target = db.query(Biro).filter(func.lower(Biro.name) == x["seki"].lower()).first()
            if target is None:
                target = Biro(name=x["seki"], parent_id=biro.id)
                db.add(target)
                db.flush()
        level = "Sekretariat" if x["seki"] else x["level"]
        dup = db.query(Post).filter_by(person_id=p.id, session=x["session"], biro_id=target.id, title=x["title"]).first()
        if dup:
            continue
        db.add(Post(person_id=p.id, session=x["session"], level=level, biro_id=target.id, title=x["title"],
                    current=pp.session_year(x["session"]) == latest))
        stats["posts_new"] += 1
    if dry_run:
        db.rollback()
    else:
        for p in by_email.values():
            sync_person_to_roster(db, p)
        db.commit()
    return {"dry_run": dry_run, "stats": stats, "errors": errors[:200], "error_count": len(errors),
            "counts": {"belts": len(parsed["belts"]), "members": len(parsed["members"]),
                       "alumni": len(parsed["alumni"]), "posts": len(parsed["posts"])}}


# ---------------------------------------------------------------- import CSV
CSV_ROSTER_COLS = {
    "member_no": {"member_no", "no_ahli", "no ahli", "noahli", "nombor ahli", "no. ahli", "id"},
    "name": {"name", "nama"},
    "gender": {"gender", "jantina"},
    "college": {"college", "kolej", "college_code"},
    "email": {"email", "emel"},
    "phone": {"phone", "telefon", "no_telefon", "no telefon", "tel"},
    "intake": {"intake", "sesi", "sesi masuk", "sesi_masuk"},
    "kind": {"kind", "jenis"},
}


@router.post("/import-csv", dependencies=[Depends(require_persatuan_admin)])
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import CSV ringkas (no ahli, nama, jantina, kolej, emel, telefon).
    Automatik kemas kini modul Persatuan (Person) DAN kelayakan pengangkutan (MemberRoster)."""
    import re
    raw = await file.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise HTTPException(413, "Fail terlalu besar (maks 4MB)")
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
    idx = {k: next((i for i, h in enumerate(header) if h in names), None) for k, names in CSV_ROSTER_COLS.items()}
    if idx["member_no"] is None and idx["name"] is None:
        raise HTTPException(400, "Kolum 'no ahli' atau 'nama' tidak dijumpai dalam baris tajuk fail CSV")

    sg = _sg_numbers(db)
    added = updated = 0
    errors = []

    for n, r in enumerate(rows[1:], start=2):
        get = lambda k: (r[idx[k]].strip() if idx[k] is not None and idx[k] < len(r) else "")
        mno = re.sub(r"\s+", "", get("member_no")).upper()
        name = get("name")
        email = get("email").lower()
        phone = pp.clean_phone(get("phone"))
        college = get("college").upper()
        gender_raw = get("gender").lower()
        gender = None
        if gender_raw in ("l", "lelaki", "male", "m"):
            gender = "male"
        elif gender_raw in ("p", "perempuan", "female", "f"):
            gender = "female"

        intake = get("intake")
        if not intake and mno.startswith("SG") and len(mno) >= 6:
            intake = mno[2:6]
        elif not intake and mno.startswith("SSG") and len(mno) >= 7:
            intake = mno[3:7]
        if not intake:
            intake = "2627"

        kind = get("kind").upper()
        if kind not in ("SG", "SSG"):
            kind = "SSG" if mno.startswith("SSG") else "SG"

        if not mno and not name:
            continue

        p = None
        # 1. Padankan mengikut emel dahulu (supaya jika nombor ahli berubah, rekod lama tetap dijumpai)
        if email and "@" in email and not email.endswith("@pssgutm.local"):
            p = db.query(Person).filter(func.lower(Person.email) == email).first()
        # 2. Jika tiada emel, padankan mengikut nombor ahli
        if p is None and mno:
            p = db.query(Person).filter_by(member_no=mno).first()
        # 3. Jika masih tiada, padankan mengikut nama penuh yang tepat
        if p is None and name and len(name.strip()) >= 3:
            p = db.query(Person).filter(func.lower(Person.name) == name.strip().lower()).first()

        old_mno = p.member_no if p else None

        created = p is None
        if created:
            if not email or "@" not in email:
                base_em = f"{mno.lower() if mno else 'ahli'}@pssgutm.local"
                email = base_em
                suffix = 1
                while db.query(Person).filter(func.lower(Person.email) == email).first():
                    email = f"{base_em.split('@')[0]}_{suffix}@pssgutm.local"
                    suffix += 1
            p = Person(email=email)
            db.add(p)

        p.name = name or p.name or mno
        if email and "@" in email and not email.endswith("@pssgutm.local"):
            p.email = email
        if phone:
            p.phone = phone
        if gender:
            p.gender = gender
        if college:
            p.college = college
        p.intake = intake
        p.kind = kind
        p.active = True
        if mno:
            p.member_no = mno
        elif not p.member_no:
            p.member_no = pp.next_sg_no(intake, sg)
            sg.add(p.member_no)

        db.flush()
        sync_person_to_roster(db, p, old_mno=old_mno)
        added += created
        updated += (not created)

    db.commit()
    return {"added": added, "updated": updated, "errors": errors[:30], "error_count": len(errors)}


# ---------------------------------------------------------------- semak nombor ahli tidak sah

@router.get("/people/invalid-member-nos", dependencies=[Depends(require_persatuan_admin)])
def list_invalid_member_nos(db: Session = Depends(get_db)):
    """Senarai ahli dengan nombor ahli SG yang tahunnya bukan bersebelahan."""
    invalids = [
        {"id": p.id, "name": p.name, "member_no": p.member_no,
         "intake": p.intake, "email": p.email}
        for p in db.query(Person).filter(Person.member_no.like("SG%")).all()
        if p.member_no and not is_valid_sg_no(p.member_no)
    ]
    return {"count": len(invalids), "items": invalids}


@router.post("/people/notify-invalid-member-nos", dependencies=[Depends(require_persatuan_admin)])
def retrigger_invalid_member_no_notify(db: Session = Depends(get_db)):
    """Reset guard dan hantar semula notifikasi kepada ahli dengan no ahli tidak sah."""
    GUARD_KEY = "notified_invalid_sg_no_v1"
    guard = db.get(models.Setting, GUARD_KEY)
    if guard:
        db.delete(guard)
        db.commit()
    notify_invalid_member_nos(db)
    guard = db.get(models.Setting, GUARD_KEY)
    return {"ok": True, "result": guard.value if guard else "done"}


# ---------------------------------------------------------------- biro, seki, jawatan

class BiroIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: int | None = None
    can_attendance: bool = False
    can_inventory: bool = False


@router.get("/biros")
def list_biros(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": b.id, "name": b.name, "parent_id": b.parent_id, "can_attendance": b.can_attendance,
             "can_inventory": b.can_inventory} for b in db.query(Biro).order_by(Biro.parent_id.isnot(None), Biro.name)]


@router.post("/biros", dependencies=[Depends(require_persatuan_admin)])
def add_biro(data: BiroIn, db: Session = Depends(get_db)):
    if db.query(Biro).filter(func.lower(Biro.name) == data.name.strip().lower()).first():
        raise HTTPException(409, "Nama itu sudah ada")
    b = Biro(name=data.name.strip(), parent_id=data.parent_id, can_attendance=data.can_attendance,
             can_inventory=data.can_inventory)
    db.add(b)
    db.commit()
    return {"id": b.id}


@router.put("/biros/{bid}", dependencies=[Depends(require_persatuan_admin)])
def edit_biro(bid: int, data: BiroIn, db: Session = Depends(get_db)):
    b = db.get(Biro, bid)
    if b is None:
        raise HTTPException(404, "Tak jumpa")
    other = db.query(Biro).filter(func.lower(Biro.name) == data.name.strip().lower(), Biro.id != bid).first()
    if other:
        raise HTTPException(409, "Nama itu sudah ada")
    b.name, b.parent_id = data.name.strip(), (data.parent_id if data.parent_id != bid else None)
    b.can_attendance, b.can_inventory = data.can_attendance, data.can_inventory
    db.commit()
    return {"ok": True}


@router.delete("/biros/{bid}", dependencies=[Depends(require_persatuan_admin)])
def delete_biro(bid: int, db: Session = Depends(get_db)):
    if db.query(Post).filter_by(biro_id=bid).count() or db.query(Biro).filter_by(parent_id=bid).count():
        raise HTTPException(400, "Masih ada jawatan atau seki di bawahnya")
    b = db.get(Biro, bid)
    if b:
        db.delete(b)
        db.commit()
    return {"ok": True}


class PostIn(BaseModel):
    person_id: int
    session: str
    level: str = "Biro"
    biro_id: int | None = None
    title: str = Field(min_length=1, max_length=80)
    current: bool = True


@router.post("/posts", dependencies=[Depends(require_persatuan_admin)])
def add_post(data: PostIn, db: Session = Depends(get_db)):
    if not pp.valid_session(data.session):
        raise HTTPException(400, "Sesi tak sah (cth 2425)")
    if db.get(Person, data.person_id) is None or (data.biro_id and db.get(Biro, data.biro_id) is None):
        raise HTTPException(404, "Orang atau biro tak jumpa")
    x = Post(person_id=data.person_id, session=data.session, level=data.level, biro_id=data.biro_id,
             title=data.title.strip(), current=data.current)
    db.add(x)
    db.commit()
    return {"id": x.id}


@router.put("/posts/{xid}", dependencies=[Depends(require_persatuan_admin)])
def edit_post(xid: int, current: bool, db: Session = Depends(get_db)):
    x = db.get(Post, xid)
    if x is None:
        raise HTTPException(404, "Tak jumpa")
    x.current = current
    db.commit()
    return {"ok": True}


@router.delete("/posts/{xid}", dependencies=[Depends(require_persatuan_admin)])
def delete_post(xid: int, db: Session = Depends(get_db)):
    x = db.get(Post, xid)
    if x:
        db.delete(x)
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- kehadiran

class AttIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    on_date: date


def _att_out(db, a: Attendance):
    return {"id": a.id, "title": a.title, "date": a.on_date.isoformat(), "open": a.open, "token": a.token,
            "count": db.query(AttendRecord).filter_by(attendance_id=a.id).count()}


@router.get("/attendances")
def list_att(user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    return [_att_out(db, a) for a in db.query(Attendance).order_by(Attendance.on_date.desc(), Attendance.id.desc()).limit(100)]


@router.post("/attendances")
def create_att(data: AttIn, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = Attendance(title=data.title.strip(), on_date=data.on_date, token=secrets.token_urlsafe(12), created_by=user.id)
    db.add(a)
    db.commit()
    return _att_out(db, a)


def _att(db, aid) -> Attendance:
    a = db.get(Attendance, aid)
    if a is None:
        raise HTTPException(404, "Kehadiran tak jumpa")
    return a


@router.get("/attendances/{aid}")
def att_detail(aid: int, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = _att(db, aid)
    rows = (db.query(AttendRecord, Person).join(Person, Person.id == AttendRecord.person_id)
            .filter(AttendRecord.attendance_id == aid).order_by(func.lower(Person.name)).all())
    return {**_att_out(db, a), "records": [
        {"id": r.id, "person_id": p.id, "name": p.name, "member_no": p.member_no, "kind": p.kind,
         "manual": r.manual, "at": r.at.isoformat()} for r, p in rows]}


@router.get("/attendances/{aid}/qr")
def att_qr(aid: int, base: str, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = _att(db, aid)
    if not base.startswith(("http://", "https://")):
        raise HTTPException(400, "Alamat asas tak sah")
    url = f"{base.rstrip('/')}/hadir/{a.token}"
    img = None
    try:
        import segno
        img = segno.make(url, error="m").svg_data_uri(scale=8, border=2)
    except Exception:
        img = None   # pustaka QR tiada: paparkan pautan sahaja
    return {"url": url, "image": img}


@router.put("/attendances/{aid}/open")
def att_open(aid: int, open: bool, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = _att(db, aid)
    a.open = open
    db.commit()
    return _att_out(db, a)


class AddIn(BaseModel):
    person_id: int


@router.post("/attendances/{aid}/add")
def att_add(aid: int, data: AddIn, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    _att(db, aid)
    if db.get(Person, data.person_id) is None:
        raise HTTPException(404, "Orang tak jumpa")
    if db.query(AttendRecord).filter_by(attendance_id=aid, person_id=data.person_id).first():
        return {"ok": True, "already": True}
    db.add(AttendRecord(attendance_id=aid, person_id=data.person_id, manual=True))
    db.commit()
    return {"ok": True}


@router.delete("/attendances/{aid}/records/{rid}")
def att_remove(aid: int, rid: int, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    r = db.get(AttendRecord, rid)
    if r and r.attendance_id == aid:
        db.delete(r)
        db.commit()
    return {"ok": True}


@router.delete("/attendances/{aid}")
def att_delete(aid: int, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = _att(db, aid)
    db.query(AttendRecord).filter_by(attendance_id=aid).delete()
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.get("/attendances/{aid}/csv")
def att_csv(aid: int, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = att_detail(aid, user, db)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Nama", "No. ahli", "Jenis", "Cara", "Masa"])
    for r in a["records"]:
        w.writerow([r["name"], r["member_no"], r["kind"], "manual" if r["manual"] else "QR", r["at"]])
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="kehadiran.csv"'})


@router.get("/hadir/{token}")
def hadir_info(token: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Attendance).filter_by(token=token).first()
    if a is None:
        raise HTTPException(404, "Kod kehadiran tak sah")
    return {"title": a.title, "date": a.on_date.isoformat(), "open": a.open}


@router.post("/hadir/{token}")
def hadir(token: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ahli imbas QR lalu tekan hadir. Hanya yang ada dalam senarai ahli/alumni (emel padan) direkodkan."""
    a = db.query(Attendance).filter_by(token=token).first()
    if a is None:
        raise HTTPException(404, "Kod kehadiran tak sah")
    if not a.open:
        raise HTTPException(400, "Kehadiran ini sudah ditutup")
    p = person_of(db, user)
    if p is None:
        raise HTTPException(400, "Emel anda tiada dalam senarai ahli/alumni. Hubungi BLG untuk direkodkan secara manual.")
    if db.query(AttendRecord).filter_by(attendance_id=a.id, person_id=p.id).first():
        return {"ok": True, "already": True, "title": a.title}
    db.add(AttendRecord(attendance_id=a.id, person_id=p.id))
    db.commit()
    return {"ok": True, "title": a.title}


# ---------------------------------------------------------------- inventori

class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = ""
    total: int = Field(default=1, ge=0, le=100000)
    note: str = Field(default="", max_length=300)
    image: str = ""
    active: bool = True


def _out_qty(db, item_id) -> int:
    return int(db.query(func.coalesce(func.sum(Loan.qty), 0)).filter(Loan.item_id == item_id,
                                                                     Loan.returned_at.is_(None)).scalar() or 0)


@router.get("/inventory/items")
def items(user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    rows = db.query(Item).order_by(func.lower(Item.name)).all()
    return [{"id": i.id, "name": i.name, "category": i.category, "total": i.total, "note": i.note,
             "image": i.image or "", "active": i.active, "out": _out_qty(db, i.id), "available": i.total - _out_qty(db, i.id)} for i in rows]


@router.post("/inventory/items")
def add_item(data: ItemIn, user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    i = Item(name=data.name.strip(), category=data.category.strip(), total=data.total, note=data.note.strip(),
             image=data.image.strip() if data.image else None, active=data.active)
    db.add(i)
    db.commit()
    return {"id": i.id}


@router.put("/inventory/items/{iid}")
def edit_item(iid: int, data: ItemIn, user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    i = db.get(Item, iid)
    if i is None:
        raise HTTPException(404, "Tak jumpa")
    i.name, i.category, i.total, i.note, i.active = data.name.strip(), data.category.strip(), data.total, data.note.strip(), data.active
    if data.image is not None:
        i.image = data.image.strip() or None
    db.commit()
    return {"ok": True}


@router.post("/inventory/items/{iid}/image")
async def upload_item_image(iid: int, file: UploadFile = File(...), user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    """Muat naik gambar barang inventori (pilihan)."""
    i = db.get(Item, iid)
    if i is None:
        raise HTTPException(404, "Barang tak jumpa")
    if i.image:
        try:
            storage.delete(i.image)
        except Exception:
            pass
    name = await save_upload(file, prefix="item_", images_only=True)
    i.image = name
    db.commit()
    return {"image": i.image}


@router.delete("/inventory/items/{iid}/image")
def delete_item_image(iid: int, user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    """Padam gambar barang inventori."""
    i = db.get(Item, iid)
    if i and i.image:
        try:
            storage.delete(i.image)
        except Exception:
            pass
        i.image = None
        db.commit()
    return {"ok": True}


def _loan_out(db, l: Loan):
    it, p = db.get(Item, l.item_id), db.get(Person, l.person_id)
    return {"id": l.id, "item": it.name if it else "", "item_id": l.item_id, "person": p.name if p else "",
            "person_id": l.person_id, "qty": l.qty, "taken_at": l.taken_at.isoformat(),
            "due_date": l.due_date.isoformat() if l.due_date else None, "taken_note": l.taken_note,
            "taken_photo": l.taken_photo, "returned_at": l.returned_at.isoformat() if l.returned_at else None,
            "return_note": l.return_note, "return_photo": l.return_photo,
            "overdue": bool(l.returned_at is None and l.due_date and l.due_date < svc.today_my())}


@router.get("/inventory/loans")
def loans(open_only: bool = False, user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    qs = db.query(Loan)
    if open_only:
        qs = qs.filter(Loan.returned_at.is_(None))
    return [_loan_out(db, l) for l in qs.order_by(Loan.id.desc()).limit(300)]


@router.post("/inventory/loans")
async def lend(item_id: int = Form(...), person_id: int = Form(...), qty: int = Form(1),
               due_date: str = Form(""), note: str = Form(""), file: UploadFile | None = File(None),
               user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    it = db.get(Item, item_id)
    if it is None or not it.active or db.get(Person, person_id) is None:
        raise HTTPException(404, "Barang atau peminjam tak jumpa")
    if qty < 1 or qty > it.total - _out_qty(db, item_id):
        raise HTTPException(400, "Kuantiti melebihi baki yang ada")
    try:
        due = pp.parse_date(due_date) if due_date else None
    except ValueError as e:
        raise HTTPException(400, str(e))
    photo = await save_upload(file, "inv_", images_only=True) if file is not None and file.filename else None
    l = Loan(item_id=item_id, person_id=person_id, qty=qty, due_date=due, taken_note=note.strip()[:300],
             taken_photo=photo, recorded_by=user.id)
    db.add(l)
    db.commit()
    return _loan_out(db, l)


@router.post("/inventory/loans/{lid}/return")
async def give_back(lid: int, note: str = Form(""), file: UploadFile | None = File(None),
                    user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    l = db.get(Loan, lid)
    if l is None:
        raise HTTPException(404, "Pinjaman tak jumpa")
    if l.returned_at is not None:
        raise HTTPException(400, "Sudah dipulangkan")
    l.return_photo = await save_upload(file, "inv_", images_only=True) if file is not None and file.filename else None
    l.return_note = note.strip()[:300]
    l.returned_at = datetime.utcnow()
    db.commit()
    return _loan_out(db, l)


@router.get("/inventory/photo/{name}")
def loan_photo(name: str, user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    if not name.startswith("inv_"):
        raise HTTPException(404, "Tak jumpa")
    return storage.serve(name, "Gambar tiada")


# ---------------------------------------------------------------- muka depan: profil, direktori, struktur

class SessionIn(BaseModel):
    code: str


@router.get("/session", dependencies=[Depends(require_persatuan_admin)])
def get_session(db: Session = Depends(get_db)):
    code = pp.session_now(db, svc.today_my())
    return {"code": code, "label": pp.session_label(code), "auto": pp.current_session(svc.today_my())}


@router.put("/session", dependencies=[Depends(require_persatuan_admin)])
def set_session(data: SessionIn, db: Session = Depends(get_db)):
    """Admin tetapkan sesi semasa (cth 2728). Sesi layak tempah transport turut beralih jika ia ikut sesi lama."""
    code = data.code.strip()
    if not pp.valid_session(code):
        raise HTTPException(400, "Sesi tak sah. Guna 4 digit, cth 2728 (tahun akhir = tahun mula + 1)")
    old = pp.session_now(db, svc.today_my())
    db.merge(models.Setting(key="current_session", value=code))
    ey = db.get(models.Setting, "eligible_years")
    if ey is not None and ey.value.strip() == old:
        ey.value = code
    db.query(Post).filter(Post.session != code).update({Post.current: False})
    db.query(Post).filter(Post.session == code).update({Post.current: True})
    db.commit()
    return {"code": code, "label": pp.session_label(code), "auto": pp.current_session(svc.today_my())}


@router.get("/me/attendance")
def my_attendance(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rekod kehadiran saya bagi sesi semasa (bermula 1 Ogos) dan senarai setiap kehadiran."""
    p = person_of(db, user)
    code = pp.session_now(db, svc.today_my())
    start = pp.session_start(code)
    rows = db.query(Attendance).filter(Attendance.on_date >= start).order_by(Attendance.on_date.desc()).all()
    mine = {r.attendance_id for r in db.query(AttendRecord).filter_by(person_id=p.id)} if p else set()
    items = [{"id": a.id, "title": a.title, "date": a.on_date.isoformat(), "present": a.id in mine} for a in rows]
    return {"session": code, "label": pp.session_label(code), "total": len(items),
            "present": sum(1 for i in items if i["present"]), "items": items, "linked": p is not None}


def _dir_item(db, p: Person, with_posts: bool = True) -> dict:
    d = {"id": p.id, "name": p.name, "intake": p.intake,
         "intake_label": pp.session_label(p.intake) if pp.valid_session(p.intake) else "", "kind": p.kind,
         "college": p.college if p.kind == "SG" else "", "is_coach": p.is_coach}
    if with_posts:
        d["posts"] = [x["title"] + (f" ({x['seki'] or x['biro']})" if (x["seki"] or x["biro"]) else "")
                      for x in _posts_out(db, p.id) if x["current"]]
    return d


@router.get("/directory")
def directory(q: str = "", kind: str = "SG", session: str = "", limit: int = 200,
              user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Direktori ahli/alumni untuk semua ahli: nama, sesi, kolej, jawatan sahaja (tiada telefon/emel)."""
    qs = db.query(Person).filter(Person.active.is_(True), Person.kind == ("SSG" if kind == "SSG" else "SG"))
    if q.strip():
        qs = qs.filter(func.lower(Person.name).like(f"%{q.strip().lower()}%"))
    if session:
        qs = qs.filter(Person.intake == session)
    total = qs.count()
    rows = qs.order_by(func.lower(Person.name)).limit(min(max(limit, 1), 500)).all()
    sessions = [s for (s,) in db.query(Person.intake).filter(Person.active.is_(True), Person.kind == ("SSG" if kind == "SSG" else "SG"))
                .distinct().all() if s and is_valid_sg_intake(s)]
    sessions.sort(key=lambda s: pp.session_year(s) if pp.valid_session(s) else 0, reverse=True)
    return {"total": total, "sessions": sessions, "items": [_dir_item(db, p, kind != "SSG") for p in rows]}


@router.get("/structure")
def structure(session: str = "", user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """MT dan biro bagi sesi tertentu (lalai: sesi terkini yang ada jawatan)."""
    all_sessions = sorted({s for (s,) in db.query(Post.session).distinct()}, key=pp.session_year, reverse=True)
    cur = session.strip() if (session and session.strip()) else (all_sessions[0] if all_sessions else "")
    mt: dict[str, list[str]] = {}
    biros: dict[str, dict[str, list[str]]] = {}
    for x in db.query(Post).filter_by(session=cur).order_by(Post.id):
        p = db.get(Person, x.person_id)
        if p is None:
            continue
        b = db.get(Biro, x.biro_id) if x.biro_id else None
        parent = db.get(Biro, b.parent_id) if b and b.parent_id else None
        if x.level == "MT":
            mt.setdefault(x.title, []).append(p.name)
        else:
            name = (parent.name if parent else (b.name if b else "Lain-lain"))
            title = x.title if not parent else f"{x.title} (seki {b.name})"
            biros.setdefault(name, {}).setdefault(title, []).append(p.name)
    return {"sessions": all_sessions, "session": cur, "label": pp.session_label(cur) if cur else "",
            "mt": [{"title": t, "names": n} for t, n in mt.items()],
            "biros": [{"name": b, "posts": [{"title": t, "names": n} for t, n in ps.items()]}
                      for b, ps in biros.items()]}


@router.get("/inventory/list")
def inventory_list(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Senarai barang untuk semua ahli (nama, kategori, baki). Pinjaman diurus oleh pengurus inventori."""
    rows = db.query(Item).filter(Item.active.is_(True)).order_by(func.lower(Item.name)).all()
    return [{"id": i.id, "name": i.name, "category": i.category, "note": i.note, "image": i.image or "",
             "available": i.total - _out_qty(db, i.id), "total": i.total} for i in rows]


# ---------------------------------------------------------------- carta organisasi MT & Biro

@router.get("/org-chart")
def get_org_chart(db: Session = Depends(get_db)):
    """Papar gambar carta organisasi jawatankuasa (jika ada)."""
    val = db.get(models.Setting, "org_chart_file")
    return {"image": val.value if val and val.value else ""}


@router.post("/org-chart", dependencies=[Depends(require_persatuan_admin)])
async def upload_org_chart(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Muat naik gambar carta hierarki organisasi jawatankuasa."""
    old = db.get(models.Setting, "org_chart_file")
    if old and old.value:
        try:
            storage.delete(old.value)
        except Exception:
            pass
    name = await save_upload(file, prefix="orgchart_", images_only=True)
    db.merge(models.Setting(key="org_chart_file", value=name))
    db.commit()
    return {"image": name}


@router.delete("/org-chart", dependencies=[Depends(require_persatuan_admin)])
def delete_org_chart(db: Session = Depends(get_db)):
    """Padam gambar carta organisasi."""
    old = db.get(models.Setting, "org_chart_file")
    if old and old.value:
        try:
            storage.delete(old.value)
        except Exception:
            pass
        db.delete(old)
        db.commit()
    return {"ok": True}
