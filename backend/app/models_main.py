"""Jadual modul utama PSSGUTM: rekod ahli/alumni, bengkung, jawatan, kehadiran, inventori."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class BeltLevel(Base):
    """Peringkat bengkung. rank kecil = peringkat bawah. Admin boleh ubah nama, tambah dan susun semula."""
    __tablename__ = "belt_levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)


class Person(Base):
    """Rekod tunggal ahli semasa (SG) atau alumni (SSG). Dipadankan dengan akaun log masuk melalui emel."""
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), default="")
    gender: Mapped[str | None] = mapped_column(String(10))            # male | female
    intake: Mapped[str] = mapped_column(String(4), default="")        # sesi masuk, cth 2425
    kind: Mapped[str] = mapped_column(String(3), default="SG")        # SG | SSG
    member_no: Mapped[str] = mapped_column(String(30), default="", index=True)  # SSG tidak unik
    study_end: Mapped[date | None] = mapped_column(Date)
    study_level: Mapped[str] = mapped_column(String(40), default="")
    college: Mapped[str] = mapped_column(String(20), default="")
    block: Mapped[str] = mapped_column(String(40), default="")
    is_coach: Mapped[bool] = mapped_column(Boolean, default=False)
    belt_id: Mapped[int | None] = mapped_column(ForeignKey("belt_levels.id"))
    belt_date: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str] = mapped_column(String(300), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BeltHistory(Base):
    __tablename__ = "belt_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    belt_id: Mapped[int | None] = mapped_column(ForeignKey("belt_levels.id"))
    on_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Biro(Base):
    """Biro atau sekretariat ('seki', bawah satu biro). Bendera kebenaran ditetapkan admin."""
    __tablename__ = "biros"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("biros.id"))   # ada nilai = seki
    can_attendance: Mapped[bool] = mapped_column(Boolean, default=False)
    can_inventory: Mapped[bool] = mapped_column(Boolean, default=False)


class Post(Base):
    """Jawatan seseorang pada sesi tertentu (sejarah kekal). level: MT | Biro | Sekretariat (jawatankuasa = MT + Biro)."""
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    session: Mapped[str] = mapped_column(String(4))
    level: Mapped[str] = mapped_column(String(15), default="Biro")
    biro_id: Mapped[int | None] = mapped_column(ForeignKey("biros.id"))
    title: Mapped[str] = mapped_column(String(80))
    current: Mapped[bool] = mapped_column(Boolean, default=True)   # jawatan semasa memberi kebenaran biro


class Attendance(Base):
    __tablename__ = "attendances"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    on_date: Mapped[date] = mapped_column(Date, index=True)
    token: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    open: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AttendRecord(Base):
    __tablename__ = "attend_records"
    __table_args__ = (UniqueConstraint("attendance_id", "person_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    attendance_id: Mapped[int] = mapped_column(ForeignKey("attendances.id"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Item(Base):
    """Barang inventori persatuan."""
    __tablename__ = "inv_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(60), default="")
    total: Mapped[int] = mapped_column(Integer, default=1)
    note: Mapped[str] = mapped_column(String(300), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Loan(Base):
    __tablename__ = "inv_loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inv_items.id"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    taken_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_date: Mapped[date | None] = mapped_column(Date)
    taken_note: Mapped[str] = mapped_column(String(300), default="")
    taken_photo: Mapped[str | None] = mapped_column(String(255))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime)
    return_note: Mapped[str] = mapped_column(String(300), default="")
    return_photo: Mapped[str | None] = mapped_column(String(255))
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Notice(Base):
    """Pengumuman (kind=pengumuman) dan banner/berita kebajikan (kind=kebajikan) yang diurus admin."""
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(12), default="pengumuman", index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    image: Mapped[str | None] = mapped_column(String(255))
    link: Mapped[str] = mapped_column(String(300), default="")
    on_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PageText(Base):
    """Teks halaman ringkas yang admin edit: panduan, hubungi, sokongan."""
    __tablename__ = "page_texts"

    key: Mapped[str] = mapped_column(String(30), primary_key=True)
    body: Mapped[str] = mapped_column(Text, default="")


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(String(1500))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
