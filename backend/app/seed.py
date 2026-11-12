"""Isi data asas ikut pekeliling BKK PSSGUTM (sesi 2026/2027).

Jalankan (boleh diulang, tak duplicate):  python -m app.seed
Admin pertama:  ADMIN_EMAIL=... ADMIN_PASSWORD=... python -m app.seed
"""
import os
from datetime import time

from sqlalchemy.exc import IntegrityError

from .database import Base, SessionLocal, engine
from . import models
from .migrate import run_migrations
from .models import College, Gender, PickupPoint, Role, TrainingSession, User, Venue
from .security import hash_password

# (kod, nama, kategori, ada perkhidmatan?)
# Semua kolej dibuka. KP belum ada checkpoint (tiada nama bus stop) jadi ahli KP tak boleh tempah sehingga admin tambah.
COLLEGES = [
    ("KTDI", "Kolej Tun Dr. Ismail", "dekat", True),
    ("KTF", "Kolej Tun Fatimah", "dekat", True),
    ("KRP", "Kolej Rahman Putra", "dekat", True),
    ("KTR", "Kolej Tun Razak", "dekat", True),
    ("KTHO", "Kolej Tun Hussein Onn", "dekat", True),
    ("K9", "Kolej 9", "jauh", True),
    ("K10", "Kolej 10", "jauh", True),
    ("KP", "Kolej Perdana", "jauh", True),
    ("KTC", "Kolej Tuanku Canselor", "jauh", True),
    ("KDSE", "Kolej Datin Seri Endon", "jauh", True),
    ("KTGB", "Kolej Tun Ghafar Baba", "jauh", True),
    ("KLG", "KLG Residence", "jauh", True),
    ("KDOJ", "Kolej Dato' Onn Jaafar", "jauh", True),
]

# (kolej, jantina, tempat berkumpul). '-' dalam jadual = tiada perkhidmatan untuk jantina itu.
CHECKPOINTS = [
    ("K9", Gender.female, "Bus Stop K9"),
    ("K10", Gender.male, "Bus Stop K10"),
    ("KTC", Gender.male, "Bus Stop Sebelah S38"),
    ("KTC", Gender.female, "Bus Stop S01"),
    ("KTHO", Gender.female, "Bus Stop L12"),
    ("KTR", Gender.male, "Bus Stop K11"),
    ("KTR", Gender.female, "Bus Stop K04"),
    ("KTF", Gender.female, "Arked Meranti"),
    ("KRP", Gender.any, "G01"),
    ("KLG", Gender.any, "Bus Stop KLG"),
    ("KTGB", Gender.any, "Bus Stop KLG"),
    ("KDSE", Gender.any, "Bus Stop KDSE"),
    ("KDOJ", Gender.any, "Bus Stop KDOJ (berhampiran pintu pagar)"),
    ("KTDI", Gender.any, "Bus Stop sebelah MA1"),
]

# (tempat latihan, kolej terkecuali, kod kolej jika tempat itu ialah kolej)
VENUES = [
    ("Dewan Merdeka, KRP", "KTF,KRP", "KRP"),
    ("L50", "", ""),
    ("Dewan Serbaguna, KTHO", "KTHO", "KTHO"),
    ("Dewan Serbaguna, KTR", "KTR", "KTR"),
]


def upgrade_v7(db, by_code):
    """Naik taraf data sedia ada (sekali sahaja): buka semua kolej, tambah bus stop, tandakan tempat latihan yang ialah kolej,
    L50 tak kecualikan sesiapa, dan buka kepada semua sesi/tahun."""
    from .models import Setting
    if db.get(Setting, "seed_v7") is not None:
        return
    for code in ("KTDI", "KDSE", "KDOJ", "KTGB", "KLG", "KP"):
        if code in by_code:
            by_code[code].transport_available = True
    have = {(p.college_id, p.name) for p in db.query(PickupPoint)}
    for code, gender, name in CHECKPOINTS:
        col = by_code.get(code)
        if col is not None and (col.id, name) not in have:
            db.add(PickupPoint(name=name, college_id=col.id, gender=gender))
    for name, excl, code in VENUES:
        v = db.query(Venue).filter_by(name=name).first()
        if v is not None:
            v.college_code = code
            if name == "L50" and v.excluded_codes.strip().upper() == "KTF":
                v.excluded_codes = ""
    # merge = tambah ATAU kemas kini (kunci mungkin sudah ada dari versi lama / seed serentak semasa deploy)
    db.merge(Setting(key="eligible_years", value="*"))
    db.merge(Setting(key="seed_v7", value="1"))


def upgrade_v8(db):
    """Sekali sahaja: selaraskan jantina kenderaan dengan jantina akaun pemandu (data lama mungkin tak sepadan)."""
    from .models import Setting, Vehicle
    if db.get(Setting, "seed_v8") is not None:
        return
    drivers = {u.id: u for u in db.query(User) if u.gender is not None}
    for v in db.query(Vehicle):
        d = drivers.get(v.driver_id)
        if d is not None and v.driver_gender != d.gender:
            v.driver_gender = d.gender
    db.merge(Setting(key="seed_v8", value="1"))


def upgrade_v9(db):
    """Sekali sahaja: buang amaran lama 'senarai ditarik balik' (tiada penanda) yang tersangkut pada ahli,
    kecuali bagi tarikh yang senarainya masih benar-benar ditarik balik (belum disahkan semula)."""
    from .models import EventStatus, Notification, Setting, TrainingEvent
    if db.get(Setting, "seed_v9") is not None:
        return
    open_dates = {d for (d,) in db.query(TrainingEvent.training_date).filter(TrainingEvent.status == EventStatus.open)}
    q = db.query(Notification).filter(Notification.kind == "unfinalised", Notification.ref == "")
    for n in q.all():
        if n.training_date not in open_dates:
            db.delete(n)
    db.merge(Setting(key="seed_v9", value="1"))


def upgrade_v10(db):
    """Sekali sahaja: jika warna jenama tersimpan masih warna hijau/emas lama, buang supaya tema merah baharu terpakai.
    Warna yang admin pilih sendiri (bukan lalai lama) tidak disentuh."""
    from .models import Setting
    if db.get(Setting, "seed_v10") is not None:
        return
    for key, old in (("brand_primary", "#0b3d2e"), ("brand_accent", "#c8a24a")):
        row = db.get(Setting, key)
        if row is not None and (row.value or "").lower() == old:
            db.delete(row)
    db.merge(Setting(key="seed_v10", value="1"))


def run():
    Base.metadata.create_all(bind=engine)
    run_migrations()  # tambah lajur baharu SEBELUM sebarang query (elak ralat lajur tiada)
    db = SessionLocal()
    try:
        if db.query(College).count() == 0:
            db.add_all([College(code=c, name=n, category=k, transport_available=a) for c, n, k, a in COLLEGES])
            db.flush()

        by_code = {c.code: c for c in db.query(College)}
        if db.query(PickupPoint).count() == 0:
            for code, gender, name in CHECKPOINTS:
                db.add(PickupPoint(name=name, college_id=by_code[code].id, gender=gender))

        if db.query(models.VehicleKind).count() == 0:
            db.add_all([models.VehicleKind(name=n, base=b, seat_rows=r) for n, b, r in
                        (("Kereta 5 tempat duduk", "car", "1,3"), ("Kereta 7 tempat duduk", "car", "1,3,2"),
                         ("Motosikal", "motorcycle", "1"))])

        if db.query(Venue).count() == 0:
            db.add_all([Venue(name=n, excluded_codes=x, college_code=c) for n, x, c in VENUES])

        if db.query(TrainingSession).count() == 0:
            # Rabu & Sabtu, 9-11 PM. Pickup 8:30-8:50 PM, balik bermula 11:00 PM.
            for name, dow in (("Rabu", 2), ("Sabtu", 5)):
                db.add(TrainingSession(name=name, day_of_week=dow, start_time=time(21, 0), end_time=time(23, 0),
                                       pickup_start=time(20, 30), pickup_end=time(20, 50)))

        upgrade_v7(db, by_code)
        upgrade_v8(db)
        upgrade_v9(db)
        upgrade_v10(db)

        admin_email = os.getenv("ADMIN_EMAIL")
        admin_password = os.getenv("ADMIN_PASSWORD")
        if admin_email and admin_password and not db.query(User).filter_by(email=admin_email.lower()).first():
            db.add(User(name="Admin BKK", member_no="ADMIN", phone="0000000000", email=admin_email.lower(),
                        password_hash=hash_password(admin_password), role=Role.admin))
            print("Akaun admin dibuat.")

        try:
            db.commit()
        except IntegrityError:
            # Dua proses seed serentak (cth deploy bertindih di Render): yang satu lagi sudah siap. Selamat diabaikan.
            db.rollback()
            print("Seed: data sudah dimasukkan oleh proses lain, diteruskan.")
        print("Seed siap.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
