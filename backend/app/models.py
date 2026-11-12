import enum
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Role(str, enum.Enum):
    member = "member"
    driver = "driver"
    admin = "admin"


class Gender(str, enum.Enum):
    male = "male"
    female = "female"
    any = "any"  # untuk checkpoint/kenderaan yang terbuka kepada kedua-dua jantina


class Direction(str, enum.Enum):
    going = "going"          # pergi
    returning = "returning"  # balik


class BookingStatus(str, enum.Enum):
    confirmed = "confirmed"
    skipped = "skipped"        # ahli tekan "Tak naik"
    cancelled = "cancelled"    # dibatalkan admin / latihan dibatalkan
    ineligible = "ineligible"  # kolej terkecuali untuk tempat latihan ini


class PaymentStatus(str, enum.Enum):
    unpaid = "unpaid"
    pending = "pending"    # resit dah upload, tunggu admin verify
    paid = "paid"
    rejected = "rejected"  # resit ditolak
    void = "void"          # tak perlu bayar / dibatalkan


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class VehicleType(str, enum.Enum):
    car = "car"
    motorcycle = "motorcycle"


class EventStatus(str, enum.Enum):
    open = "open"            # ahli masih boleh skip, kereta belum dikunci
    finalised = "finalised"  # senarai disahkan: kereta dikunci, bayaran dibuka
    cancelled = "cancelled"


class College(Base):
    __tablename__ = "colleges"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)  # cth: KTF
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(10))  # "dekat" | "jauh"
    transport_available: Mapped[bool] = mapped_column(Boolean, default=True)


class Venue(Base):
    """Tempat latihan. Kolej dalam excluded_codes tak dapat pengangkutan di sini."""

    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    excluded_codes: Mapped[str] = mapped_column(String(120), default="")  # cth: "KTF,KRP"
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Jika diisi (kod kolej), tempat ini ialah kolej itu: ahli kolej sama berjalan kaki (tak perlu prebet)
    college_code: Mapped[str] = mapped_column(String(10), default="")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    # Nama pendek (seperti username): dipaparkan kepada ahli/prebet lain. Admin nampak kedua-duanya.
    short_name: Mapped[str] = mapped_column(String(40), default="")
    # Blok/bilik (cth "B-12-3") dan checkpoint pilihan ahli (jika kolej ada lebih satu)
    block: Mapped[str] = mapped_column(String(40), default="")
    pickup_point_id: Mapped[int | None] = mapped_column(ForeignKey("pickup_points.id"))
    member_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)  # SG2627XXX
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.member)
    gender: Mapped[Gender | None] = mapped_column(Enum(Gender))  # male/female; kosong utk admin/driver
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id"))
    college_other: Mapped[str] = mapped_column(String(60), default="")  # kolej 'Lain-lain' (ditulis sendiri)
    credit_balance: Mapped[float] = mapped_column(Float, default=0.0)  # bayaran dibawa dari latihan dibatalkan
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bendahari: urus bayaran ahli & bayar driver sahaja (bukan akses admin penuh)
    is_treasurer: Mapped[bool] = mapped_column(Boolean, default=False)
    # Maklumat untuk persatuan bayar driver (hanya admin & pemilik boleh lihat)
    payout_bank: Mapped[str] = mapped_column(String(100), default="")
    payout_account_no: Mapped[str] = mapped_column(String(50), default="")
    payout_account_name: Mapped[str] = mapped_column(String(100), default="")
    payout_qr_file: Mapped[str | None] = mapped_column(String(255))   # QR bank
    payout_qr2_file: Mapped[str | None] = mapped_column(String(255))  # QR e-wallet (cth Touch 'n Go), pilihan
    # Dokumen prebet: gambar lesen (wajib) + tarikh tamat, insurans (pilihan)
    licence_file: Mapped[str | None] = mapped_column(String(255))
    licence_expiry: Mapped[date | None] = mapped_column(Date)
    insurance_file: Mapped[str | None] = mapped_column(String(255))
    # Prebet yang diluluskan admin untuk turut jadi penumpang; permohonan menunggu kelulusan
    passenger_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    passenger_request: Mapped[bool] = mapped_column(Boolean, default=False)
    # Paparan pilihan pengguna: auto (ikut telefon) | light | dark. Mengikut akaun, bukan peranti.
    theme: Mapped[str] = mapped_column(String(8), default="auto")
    # Permohonan tukar jantina (male/female) menunggu kelulusan BKK; kosong = tiada
    gender_request: Mapped[str] = mapped_column(String(10), default="")
    # Ahli (ada kenderaan) mohon jadi prebet: menunggu kelulusan BKK
    prebet_request: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MemberRoster(Base):
    """Senarai ahli sah PSSGUTM. Hanya no. ahli dalam senarai ini boleh daftar."""

    __tablename__ = "member_roster"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    gender: Mapped[Gender | None] = mapped_column(Enum(Gender))
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PickupPoint(Base):
    """Checkpoint berkumpul. Satu kolej boleh ada banyak checkpoint (ahli pilih sendiri)."""

    __tablename__ = "pickup_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"))
    gender: Mapped[Gender] = mapped_column(Enum(Gender), default=Gender.any)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TrainingSession(Base):
    """Jadual tetap mingguan (Rabu & Sabtu)."""

    __tablename__ = "training_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Isnin ... 2=Rabu ... 5=Sabtu
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)        # masa balik bermula
    pickup_start: Mapped[time] = mapped_column(Time)
    pickup_end: Mapped[time] = mapped_column(Time)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Diisi untuk aktiviti luar jadual (sekali sahaja pada tarikh ini). Kosong = jadual tetap mingguan.
    one_off_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Aktiviti berbilang hari: satu "kaki" sahaja ('going' atau 'returning'). Kosong = kedua-dua arah.
    trip_only: Mapped[str | None] = mapped_column(String(10), nullable=True)
    activity_group: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Yuran seorang bagi aktiviti luar (RM, sama untuk kereta/motosikal). Kosong atau 0 = percuma.
    activity_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Aktiviti luar: jarak (km), had jarak motosikal, harga SEKENDERAAN (kereta) dan harga motosikal.
    # Yuran penumpang kereta = car_price / kapasiti kereta. Kosong = guna activity_fee (kaedah lama).
    km: Mapped[float | None] = mapped_column(Float, nullable=True)
    motor_max_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    car_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    motor_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Aktiviti luar: cara ambil. kumpul = berkumpul satu tempat | rumah = ambil dari rumah/tempat ahli
    # | kolej = ambil dari kolej | kedua = ahli pilih kolej atau tempat lain. Kosong = kedua.
    pickup_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    gather_place: Mapped[str] = mapped_column(String(120), default="")   # tempat pergi tetap (kosong = ahli pilih)
    return_place: Mapped[str] = mapped_column(String(120), default="")   # tempat balik tetap (kosong = ahli pilih)
    return_same: Mapped[bool] = mapped_column(Boolean, default=False)    # balik ke tempat pergi tetap
    # Persatuan tanggung yuran pengangkutan (ahli tak bayar; persatuan serah kepada BKK, BKK bayar prebet)
    fee_by_assoc: Mapped[bool] = mapped_column(Boolean, default=False)
    assoc_settled: Mapped[bool] = mapped_column(Boolean, default=False)  # persatuan sudah serah kepada BKK


class TrainingEvent(Base):
    """Satu latihan sebenar pada satu tarikh: tempat, dan status senarai."""

    __tablename__ = "training_events"
    __table_args__ = (UniqueConstraint("session_id", "training_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"))
    training_date: Mapped[date] = mapped_column(Date, index=True)
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"))
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.open)
    finalised_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Admin batalkan pengesahan: jangan auto-sah semula (admin sahkan sendiri bila siap)
    auto_off: Mapped[bool] = mapped_column(Boolean, default=False)


class Preference(Base):
    """Pilihan recurring ahli. Checkpoint diambil automatik daripada kolej + jantina."""

    __tablename__ = "preferences"
    __table_args__ = (UniqueConstraint("user_id", "session_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"))
    going: Mapped[bool] = mapped_column(Boolean, default=True)
    # Nama lajur di database "returning_trip" kerana RETURNING ialah kata kunci SQL (SQLite menolaknya)
    returning: Mapped[bool] = mapped_column("returning_trip", Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Vehicle(Base):
    """Kereta atau motosikal prebet. Diisi driver sendiri (perlu approve admin) atau admin."""

    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))  # cth: "Myvi Ali"
    brand: Mapped[str] = mapped_column(String(40), default="")    # JENAMA, cth Saga
    colour: Mapped[str] = mapped_column(String(30), default="")   # WARNA, cth Silver
    plate_no: Mapped[str] = mapped_column(String(20), default="")
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    vehicle_type: Mapped[VehicleType] = mapped_column(Enum(VehicleType), default=VehicleType.car)
    driver_gender: Mapped[Gender] = mapped_column(Enum(Gender), default=Gender.male)  # male | female
    # Susun atur tempat duduk PENUMPANG ikut baris, dari depan. Kereta 5 seat = "1,3", 7 seat = "1,3,2".
    # Baris pertama = sebelah driver. Motosikal = "1".
    seat_rows: Mapped[str] = mapped_column(String(20), default="1,3")
    capacity: Mapped[int] = mapped_column(Integer)  # jumlah tempat penumpang (jumlah seat_rows)
    available_days: Mapped[str] = mapped_column(String(20), default="2,5")
    approval: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), default=ApprovalStatus.approved)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Akuan keselamatan (lesen sah, insurans, helmet): pilihan, tapi driver diingatkan
    safety_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    safety_reminded_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Kategori kolej yang diutamakan: "" = ikut kolej pemandu, "dekat" | "jauh" = ditetapkan admin
    category: Mapped[str] = mapped_column(String(10), default="")
    kind_name: Mapped[str] = mapped_column(String(60), default="")  # jenis kenderaan (paparan sahaja)


class VehicleKind(Base):
    """Jenis kenderaan yang boleh dipilih driver. Admin boleh tambah (cth MPV, van) dengan susun atur seat sendiri."""

    __tablename__ = "vehicle_kinds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)         # cth "Kereta 5 tempat duduk"
    base: Mapped[str] = mapped_column(String(12), default="car")       # "car" | "motorcycle" (menentukan yuran & peraturan)
    seat_rows: Mapped[str] = mapped_column(String(20), default="1,3")  # baris penumpang dari hadapan
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class VehicleUnavailable(Base):
    __tablename__ = "vehicle_unavailable"
    __table_args__ = (UniqueConstraint("vehicle_id", "training_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    training_date: Mapped[date] = mapped_column(Date)


class Booking(Base):
    """Satu baris = satu ahli, satu tarikh, satu arah."""

    __tablename__ = "bookings"
    __table_args__ = (UniqueConstraint("user_id", "training_date", "direction"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"))
    training_date: Mapped[date] = mapped_column(Date, index=True)
    direction: Mapped[Direction] = mapped_column(Enum(Direction))
    pickup_point_id: Mapped[int | None] = mapped_column(ForeignKey("pickup_points.id"))
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    seat: Mapped[str | None] = mapped_column(String(8), default=None)  # "baris.lajur" (0-asas); pilihan admin
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), default=BookingStatus.confirmed)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Tiada prebet: BKK uruskan e-hailing (nota = butiran dari BKK, cth nama driver/plat/masa)
    ehailing: Mapped[bool] = mapped_column(Boolean, default=False)
    ehailing_note: Mapped[str] = mapped_column(String(300), default="")
    # Dipilih ahli ikut tarikh (bukan daripada jadual berulang): tak dibatalkan bila jadual berulang diubah
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    # Dibatalkan kerana LATIHAN dibatalkan (bukan ahli batal sendiri): dipulihkan jika latihan diaktifkan semula
    cancelled_by_event: Mapped[bool] = mapped_column(Boolean, default=False)
    # Aktiviti luar: tempat ambil selain checkpoint kolej (ahli taip nama, atau admin tetapkan). Kosong = ikut checkpoint kolej.
    pickup_place: Mapped[str] = mapped_column(String(120), default="")


class Payment(Base):
    """Satu bayaran = satu ahli untuk satu tarikh (pergi + balik, harga sama)."""

    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("user_id", "training_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    training_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float)              # yuran penuh
    credit_applied: Mapped[float] = mapped_column(Float, default=0.0)  # ditolak dari kredit
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.unpaid)
    receipt_path: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    """Cadangan / maklum balas ahli untuk penambahbaikan website."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="cadangan")   # cadangan | masalah | lain
    message: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default="baru")     # baru | dibaca | selesai
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Notification(Base):
    """Notifikasi dalam app. user_id kosong = broadcast kepada semua ahli."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(String(500), default="")
    training_date: Mapped[date | None] = mapped_column(Date)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    # info = maklumat (boleh dipadam) | task = tugasan (tekan terus ke kerja, boleh dipadam)
    # warning = amaran (tak boleh dipadam; hilang sendiri bila selesai, tekan ke tab berkaitan)
    severity: Mapped[str] = mapped_column(String(10), default="info")
    link: Mapped[str] = mapped_column(String(80), default="")   # laluan dalam app, cth "/driver" atau "/admin?tab=pay"
    ref: Mapped[str] = mapped_column(String(80), default="", index=True)  # kunci unik untuk elak pendua / selesaikan amaran
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NotificationDismissal(Base):
    """Pengguna memadam notifikasi siaran (user_id kosong) untuk dirinya sendiri."""

    __tablename__ = "notification_dismissals"
    __table_args__ = (UniqueConstraint("user_id", "notification_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), index=True)


class Setting(Base):
    """Tetapan ringkas key/value (maklumat bayaran, dll)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(1000), default="")


class DriverPayout(Base):
    """Rekod persatuan bayar driver (persatuan ialah orang tengah)."""

    __tablename__ = "driver_payouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    training_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float)
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    receipt_file: Mapped[str | None] = mapped_column(String(255))   # resit bayaran bendahari kepada prebet
    received: Mapped[bool] = mapped_column(Boolean, default=False)  # prebet tandakan diterima
    received_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Satu resit bagi satu prebet untuk satu tempoh (per latihan / mingguan / bulanan): baris dalam 'batch' sama berkongsi resit
    batch: Mapped[str] = mapped_column(String(40), default="", index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class PrebetAvailability(Base):
    """Prebet sahkan boleh/tak boleh bawa pada satu tarikh latihan. Hanya yang 'boleh' disusun."""

    __tablename__ = "prebet_availability"
    __table_args__ = (UniqueConstraint("user_id", "training_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    training_date: Mapped[date] = mapped_column(Date, index=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    by_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Kenderaan yang dipilih untuk tarikh ini (kosong = kenderaan pertama prebet)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DutyTick(Base):
    """Prebet tandakan: 'arrived' = dah sampai tempat latihan; 'delivered' = dah hantar semua selepas latihan."""

    __tablename__ = "duty_ticks"
    __table_args__ = (UniqueConstraint("user_id", "training_date", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    training_date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AdminDuty(Base):
    """Admin bertugas ikut bulan: hari bertugas (0=Isnin) dan nombor untuk dihubungi."""

    __tablename__ = "admin_duty"
    __table_args__ = (UniqueConstraint("user_id", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    month: Mapped[str] = mapped_column(String(7))      # "2026-11"
    weekdays: Mapped[str] = mapped_column(String(20), default="2,5")
    phone: Mapped[str] = mapped_column(String(20), default="")


class Holiday(Base):
    """Tarikh cuti: tiada pengangkutan (admin tandakan)."""

    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    training_date: Mapped[date] = mapped_column(Date, unique=True)
    note: Mapped[str] = mapped_column(String(120), default="Cuti")


class PasswordReset(Base):
    """Token lupa kata laluan (disimpan sebagai hash; sekali guna; tamat tempoh)."""

    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
