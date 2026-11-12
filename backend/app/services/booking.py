"""Enjin booking PSSGUTM: jana booking recurring, kolej terkecuali, susun kereta,
sahkan senarai, bayaran/kredit, notifikasi."""
import math
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import config, models
from ..models import BookingStatus, Direction, EventStatus, Gender, PaymentStatus, VehicleType
from .assign import (auto_seat, check_layout, complete_layout, college_group, lone_female_cases, parse_rows,
                     plan_assignment, seat_list, zone_of)

DAY_NAMES = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"]
MY_TZ = timezone(timedelta(hours=8))  # Malaysia, tiada DST


def now_my() -> datetime:
    return datetime.now(MY_TZ).replace(tzinfo=None)


def today_my() -> date:
    return now_my().date()


def fmt12(t) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def fmt_date(d: date) -> str:
    return f"{DAY_NAMES[d.weekday()]} {d.strftime('%d/%m')}"


def _hm(txt: str) -> time:
    h, m = str(txt).split(":")
    return time(int(h), int(m))


def cutoff_dt(d: date) -> datetime:
    """Waktu tutup (lalai 5 petang) pada hari latihan: prebet sahkan & ahli pilih Pergi/Balik."""
    return datetime.combine(d, _hm(config.CUTOFF_TIME))


def member_closed(d: date) -> bool:
    return config.ENFORCE_CUTOFF and now_my() >= cutoff_dt(d)


def notify_gender_change(db: Session, user: models.User, old, new, actor=None, how: str = "") -> None:
    """Maklumkan admin: jantina ahli berubah (supaya fail CSV sumber dikemas kini). Senarai ahli sah (roster) sudah diselaraskan."""
    lbl = {"male": "Lelaki", "female": "Perempuan"}
    o = lbl.get(getattr(old, "value", old), "-"); n = lbl.get(getattr(new, "value", new), "-")
    for a in db.query(models.User).filter_by(role=models.Role.admin, active=True):
        if actor is not None and a.id == actor.id:
            continue
        _notify(db, a.id, "admin_alert", f"Jantina ahli berubah: {user.name}",
                f"{user.member_no}: {o} → {n}{(' ' + how) if how else ''}. Senarai ahli sah dalam sistem sudah dikemas kini; "
                "betulkan juga fail CSV sumber BKK.", severity="task", link="/admin?tab=more",
                ref=f"gender:{user.id}:{getattr(new, 'value', new)}")


def sync_driver_vehicles(db: Session, user: models.User, resort: bool = True) -> int:
    """Jantina pemandu disalin ke setiap kenderaan (menentukan susunan tempat duduk). Selaraskan bila jantina akaun berubah,
    kemudian susun semula latihan terbuka yang akan datang. Return bilangan kenderaan yang dikemas kini."""
    if user.gender not in (Gender.male, Gender.female):
        return 0
    n = 0
    for v in db.query(models.Vehicle).filter_by(driver_id=user.id):
        if v.driver_gender != user.gender:
            v.driver_gender = user.gender
            n += 1
    db.flush()
    if n and resort:
        for ev in db.query(models.TrainingEvent).filter(models.TrainingEvent.training_date >= today_my(),
                                                        models.TrainingEvent.status == EventStatus.open):
            assign_vehicles(db, ev)
    db.commit()
    return n


def change_gender(db: Session, user: models.User, new, actor=None, how: str = "") -> None:
    """Tukar jantina ahli (kelulusan admin / suntingan admin): selaras roster, susun semula, maklumkan admin."""
    old = user.gender
    if old == new:
        return
    user.gender = new
    user.gender_request = ""
    r = db.query(models.MemberRoster).filter_by(member_no=user.member_no).first()
    if r is not None:
        r.gender = new
    db.flush()
    if old is not None:
        notify_gender_change(db, user, old, new, actor=actor, how=how)
    db.commit()
    reconcile_user(db, user)
    sync_driver_vehicles(db, user)


def user_can_pay_any(db: Session, user: models.User) -> bool:
    """Ada bayaran yang sudah dibuka (senarai disahkan BKK / auto)? Maklumat bank & QR hanya dipaparkan selepas itu."""
    for p in db.query(models.Payment).filter_by(user_id=user.id):
        if can_pay(db, p):
            return True
    return False


def auto_finalise_dt(d: date) -> datetime:
    return datetime.combine(d, _hm(config.AUTO_FINALISE_TIME))


def pay_deadline(d: date) -> datetime:
    """Ahli bayar persatuan sebelum jam ini pada hari selepas latihan (lalai 12 tengah hari); selepas itu tunggakan."""
    return datetime.combine(d + timedelta(days=1), _hm(config.PAY_DEADLINE_TIME))


def arrive_by(s: models.TrainingSession) -> str:
    """Ahli sampai di checkpoint (lalai 5 minit sebelum waktu pickup mula)."""
    t = datetime.combine(date.today(), s.pickup_start) - timedelta(minutes=config.ARRIVE_EARLY_MINUTES)
    return fmt12(t.time())


def short(u) -> str:
    """Nama pendek (dipaparkan kepada ahli/prebet lain). Admin nampak nama penuh juga."""
    return (u.short_name or "").strip() or u.name


def vehicle_desc(v: models.Vehicle) -> str:
    """'Saga, silver & ABC123' (JENAMA, WARNA & NO.PLAT)."""
    head = ", ".join(x for x in ((v.brand or "").strip() or None, (v.colour or "").strip() or None) if x)
    if not head:
        head = v.name
    return f"{head} & {v.plate_no}" if v.plate_no else head


KIND_DEFAULTS = {  # jenis -> (tahap, pautan lalai). tahap: info | task | warning
    "admin_alert": ("task", "/admin"), "payout_due": ("task", "/bendahari"), "payment": ("info", "/bayaran"),
    "car": ("info", "/"), "venue": ("info", "/"), "finalised": ("info", "/"), "cancelled": ("info", "/"),
    "reminder": ("task", "/"), "driver": ("task", "/prebet"), "payout": ("info", "/pendapatan"), "announcement": ("info", ""),
}


def _notify(db, user_id, kind, title, body="", training_date=None, severity=None, link=None, ref=""):
    """Tambah notifikasi. Jika 'ref' diberi dan notifikasi tak dibaca dengan ref sama masih ada untuk pengguna ini, kemas kini sahaja."""
    dsev, dlink = KIND_DEFAULTS.get(kind, ("info", ""))
    severity = severity or dsev
    link = dlink if link is None else link
    if ref:
        old = db.query(models.Notification).filter_by(user_id=user_id, ref=ref).first()
        if old is not None:
            old.title, old.body, old.severity, old.link, old.kind = title[:150], body[:500], severity, link, kind
            old.training_date, old.read = training_date, False
            return old
    n = models.Notification(user_id=user_id, kind=kind, title=title[:150], body=body[:500], training_date=training_date,
                            severity=severity, link=link, ref=ref)
    db.add(n)
    return n


def resolve_warning(db, user_id, ref):
    """Amaran selesai: buang notifikasi amaran dengan ref ini."""
    for n in db.query(models.Notification).filter_by(user_id=user_id, ref=ref):
        db.delete(n)


# ---------------------------------------------------------------- jadual harga (boleh diubah admin)

RATE_KEYS = [(k, c) for k in ("car", "motorcycle") for c in ("dekat", "jauh")]


def fee_amount(db: Session, vehicle_type: str, category: str) -> float:
    """Yuran penumpang (RM) ikut jenis kenderaan & kategori kolej. Tetapan admin; kalau tiada guna nilai asal."""
    s = db.get(models.Setting, f"fee_{vehicle_type}_{category}")
    if s is not None and s.value.strip() != "":
        try:
            return float(s.value)
        except ValueError:
            pass
    return config.fee_amount(vehicle_type, category)


def payout_rate(db: Session, vehicle_type: str, category: str) -> float:
    """Bayaran TETAP kepada prebet bagi satu hari latihan (ikut jenis kenderaan & kategori kolej prebet). Hanya admin boleh ubah."""
    s = db.get(models.Setting, f"payout_{vehicle_type}_{category}")
    if s is not None and s.value.strip() != "":
        try:
            return float(s.value)
        except ValueError:
            pass
    return config.payout_default(vehicle_type, category)


def fee_tables(db: Session) -> dict:
    return {
        "fees": {k: {c: fee_amount(db, k, c) for c in ("dekat", "jauh")} for k in ("car", "motorcycle")},
        "payouts": {k: {c: payout_rate(db, k, c) for c in ("dekat", "jauh")} for k in ("car", "motorcycle")},
    }


def get_setting(db: Session, key: str, default: str = "") -> str:
    s = db.get(models.Setting, key)
    return s.value if s is not None and s.value != "" else default


def set_setting(db: Session, key: str, value: str):
    s = db.get(models.Setting, key)
    if s is None:
        db.add(models.Setting(key=key, value=value))
    else:
        s.value = value


# ---------------------------------------------------------------- cuti

def is_holiday(db: Session, d: date) -> bool:
    return db.query(models.Holiday).filter_by(training_date=d).first() is not None


def holiday_note(db: Session, d: date) -> str:
    h = db.query(models.Holiday).filter_by(training_date=d).first()
    return (h.note or "Cuti") if h else ""


# ---------------------------------------------------------------- lookups

def upcoming_dates(db: Session, today: date | None = None, days: int | None = None):
    today = today or today_my()
    sessions = db.query(models.TrainingSession).filter_by(active=True).all()
    out = []
    for offset in range((config.GENERATE_DAYS_AHEAD if days is None else days) + 1):
        d = today + timedelta(days=offset)
        for s in sessions:
            if s.one_off_date is not None:
                if s.one_off_date == d:
                    out.append((d, s))
            elif s.day_of_week == d.weekday():
                out.append((d, s))
    return sorted(out, key=lambda x: x[0])


def warning_unlock_date(db: Session, n) -> date:
    """Amaran baru boleh dipadam pada tarikh latihan SETERUSNYA selepas tarikh rujukannya
    (training_date amaran, atau tarikh dicipta jika tiada). Cth amaran Rabu -> boleh padam Sabtu."""
    ref = n.training_date or (n.created_at + timedelta(hours=8)).date()
    found = upcoming_dates(db, ref + timedelta(days=1), 21)
    return found[0][0] if found else ref + timedelta(days=3)


def warning_deletable(db: Session, n, today: date | None = None) -> bool:
    if (n.severity or "info") != "warning":
        return True
    return (today or today_my()) >= warning_unlock_date(db, n)


# ---------------------------------------------------------------- kelayakan ikut sesi (tahun) ahli

def eligible_years(db: Session) -> list[str]:
    s = db.get(models.Setting, "eligible_years")
    raw = s.value if s is not None else config.DEFAULT_ELIGIBLE_YEARS
    return [y.strip() for y in raw.split(",") if y.strip()]


def member_year(member_no: str) -> str | None:
    """'SG2627001' -> '2627'. Selain format itu -> None."""
    m = re.match(r"^SG(\d{4})\d{3}$", (member_no or "").strip().upper())
    return m.group(1) if m else None


def year_label(y: str) -> str:
    return "Semua sesi" if y == "*" else f"{y[:2]}/{y[2:]}"


def year_ok(db: Session, member_no: str) -> bool:
    y = member_year(member_no)
    yrs = eligible_years(db)
    return "*" in yrs or (y is not None and y in yrs)


def get_or_create_event(db: Session, session: models.TrainingSession, d: date) -> models.TrainingEvent:
    ev = db.query(models.TrainingEvent).filter_by(session_id=session.id, training_date=d).first()
    if ev is None:
        ev = models.TrainingEvent(session_id=session.id, training_date=d)
        db.add(ev)
        db.flush()
    return ev


def event_on(db: Session, d: date) -> models.TrainingEvent | None:
    return db.query(models.TrainingEvent).filter_by(training_date=d).first()


def excluded_codes(db: Session, ev: models.TrainingEvent) -> set[str]:
    if not ev.venue_id:
        return set()
    v = db.get(models.Venue, ev.venue_id)
    return {c.strip().upper() for c in (v.excluded_codes or "").split(",") if c.strip()} if v else set()


def points_for(db: Session, user: models.User) -> list[models.PickupPoint]:
    """Checkpoint yang boleh dipilih ahli: aktif, kolej sama, jantina sama atau 'any'."""
    if not user.college_id or user.gender not in (Gender.male, Gender.female):
        return []
    pts = db.query(models.PickupPoint).filter_by(college_id=user.college_id, active=True).order_by(models.PickupPoint.id).all()
    return [p for p in pts if p.gender in (user.gender, Gender.any)]


def resolve_point(db: Session, user: models.User) -> models.PickupPoint | None:
    """Checkpoint ahli: pilihan sendiri jika masih sah, jika tidak yang pertama sepadan (jantina khusus dahulu)."""
    pts = points_for(db, user)
    if user.pickup_point_id:
        for p in pts:
            if p.id == user.pickup_point_id:
                return p
    for p in pts:
        if p.gender == user.gender:
            return p
    return pts[0] if pts else None


def eligibility(db: Session, user: models.User, activity: bool = False) -> dict:
    """Layak guna kemudahan? Return {eligible, reason, pickup_point, category, fee_car, fee_motorcycle}."""
    col = db.get(models.College, user.college_id) if user.college_id else None
    blank = {"pickup_point": None, "category": None, "fee_car": None, "fee_motorcycle": None}
    if user.role == models.Role.driver and not user.passenger_ok:
        return {"eligible": False, "reason": "Akaun prebet tidak menempah sebagai penumpang. "
                                             "Tekan 'Mohon jadi penumpang' di Profil jika perlu (perlu kelulusan BKK).", **blank}
    if not activity and not year_ok(db, user.member_no):
        yrs = ", ".join(year_label(y) for y in eligible_years(db)) or "-"
        return {"eligible": False, "reason": f"Tempahan prebet dibuka untuk ahli sesi {yrs} sahaja. "
                                             "Akaun anda boleh digunakan tetapi tidak boleh menempah.", **blank}
    if activity and (col is None or not col.transport_available or resolve_point(db, user) is None):
        # Aktiviti luar terbuka untuk semua ahli (termasuk tinggal luar / alumni): tempat ambil dipilih sendiri
        return {"eligible": True, "reason": "", "pickup_point": None, "category": col.category if col else None,
                "fee_car": None, "fee_motorcycle": None}
    if col is None:
        reason = (f"Kolej '{user.college_other}' tiada dalam senarai perkhidmatan. BKK akan semak."
                  if user.college_other else "Akaun ini bukan akaun penumpang.")
        return {"eligible": False, "reason": reason, **blank}
    if not col.transport_available:
        return {"eligible": False, "reason": f"Pengangkutan tidak disediakan untuk {col.code}.",
                **{**blank, "category": col.category}}
    pt = resolve_point(db, user)
    if pt is None:
        who = "lelaki" if user.gender == Gender.male else "perempuan"
        return {"eligible": False, "reason": f"Belum ada checkpoint (bus stop) untuk {col.code} ({who}). "
                                              "BKK akan tambah; tempahan dibuka selepas itu.",
                **{**blank, "category": col.category}}
    return {"eligible": True, "reason": "", "pickup_point": pt.name, "category": col.category,
            "fee_car": fee_amount(db, "car", col.category),
            "fee_motorcycle": fee_amount(db, "motorcycle", col.category)}


PICKUP_MODES = {"kumpul": "Tempat tetap (lama)", "rumah": "Ahli ambil dari rumah / tempat sendiri",
                "kolej": "Ambil dari kolej sahaja", "kedua": "Ahli pilih kolej atau tempat lain"}
CHOOSE_MODES = ("rumah", "kolej", "kedua")   # cara ahli memilih bila tempat tidak ditetapkan tetap


def clean_place(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()[:120]


def fixed_place(s: models.TrainingSession, direction: str) -> str:
    """Tempat tetap yang admin tetapkan untuk arah itu ('' = ahli pilih). Balik boleh 'sama dengan pergi'."""
    go = s.gather_place or ""
    if direction != "returning":
        return go
    if s.return_place:
        return s.return_place
    return go if (s.return_same or s.pickup_mode == "kumpul") else ""


def resolve_activity_pickup(s: models.TrainingSession, pt, pickup: str | None, place_text: str | None,
                            direction: str = "going") -> tuple[str, str]:
    """Tempat ambil (pergi) atau hantar (balik) untuk aktiviti luar. Return ('kolej', '') atau ('tempat', nama tempat)."""
    fixed = fixed_place(s, direction)
    if fixed:
        return "tempat", fixed
    mode = s.pickup_mode if s.pickup_mode in CHOOSE_MODES else "kedua"
    can_kolej = pt is not None and mode in ("kolej", "kedua")
    can_tempat = mode in ("rumah", "kedua") or pt is None
    choice = pickup or ("kolej" if can_kolej else "tempat")
    if choice == "kolej":
        if not can_kolej:
            raise ValueError("Aktiviti ini tak ambil dari kolej." if mode == "rumah"
                             else "Belum ada checkpoint untuk kolej anda. Hubungi BKK.")
        return "kolej", ""
    if choice == "tempat":
        if not can_tempat:
            raise ValueError("Aktiviti ini ambil dari kolej sahaja.")
        place = clean_place(place_text)
        if not place:
            raise ValueError("Isi nama tempat ambil.")
        return "tempat", place
    raise ValueError("Pilihan tempat ambil tak sah")


def pickup_label(b: models.Booking, pts: dict) -> str | None:
    """Nama checkpoint kolej, atau tempat lain (aktiviti luar)."""
    if b.pickup_place:
        return b.pickup_place
    p = pts.get(b.pickup_point_id)
    return getattr(p, "name", p) if p is not None else None


def activity_session_on(db: Session, user_id: int, d: date):
    b = db.query(models.Booking).filter_by(user_id=user_id, training_date=d).first()
    s = db.get(models.TrainingSession, b.session_id) if b else None
    return s if (s is not None and s.one_off_date is not None) else None


def activity_is_free(s: models.TrainingSession) -> bool:
    return not (s.activity_fee or 0) and not (s.car_price or 0) and not (s.motor_price or 0)


def activity_price(s: models.TrainingSession, vehicle_type: str = "car", vehicle: models.Vehicle | None = None) -> float:
    """Yuran seorang bagi aktiviti luar. Harga sekenderaan dibahagi kapasiti (persatuan tanggung kekurangan jika kereta tak penuh).
    Motosikal: harga motosikal (lalai RM3)."""
    if s.car_price is None and s.motor_price is None:
        return float(s.activity_fee or 0.0)  # kaedah lama: yuran tetap seorang
    if vehicle_type == "motorcycle":
        return float(math.ceil(round(float(s.motor_price if s.motor_price is not None
                                           else config.MOTOR_ACTIVITY_PRICE_DEFAULT), 2)))
    cap = vehicle.capacity if vehicle is not None and vehicle.capacity else config.CAR_SEATS_DEFAULT
    return float(math.ceil(round(float(s.car_price or 0.0) / cap, 2)))  # dibundar ke atas ke ringgit penuh (cth 10.22 -> 11)


def motor_allowed(s: models.TrainingSession) -> bool:
    """Aktiviti luar: motosikal hanya jika jarak tak melebihi had (lalai 10 km)."""
    if s.one_off_date is None or s.km is None:
        return True
    return s.km <= (s.motor_max_km if s.motor_max_km is not None else config.MOTOR_MAX_KM_DEFAULT)


def activity_fee_on(db: Session, user_id: int, d: date) -> float | None:
    """Anggaran yuran (kereta) jika tarikh ini aktiviti luar; latihan biasa = None. 0 = percuma."""
    s = activity_session_on(db, user_id, d)
    if s is None:
        return None
    return 0.0 if (activity_is_free(s) or s.fee_by_assoc) else activity_price(s, "car")


def free_activity_on(db: Session, d: date) -> bool:
    """Semua tempahan pada tarikh ini ialah aktiviti luar percuma."""
    sids = {r[0] for r in db.query(models.Booking.session_id).filter_by(training_date=d).distinct()}
    sess = [db.get(models.TrainingSession, i) for i in sids]
    return bool(sess) and all(s.one_off_date is not None and activity_is_free(s) for s in sess)


def fee_for(db: Session, user: models.User, vehicle_type: str = "car", d: date | None = None,
            vehicle: models.Vehicle | None = None) -> float:
    """Yuran ikut kategori kolej dan jenis kenderaan (jadual harga admin). Sebelum kenderaan ditetapkan = kadar kereta (anggaran).
    Aktiviti luar: harga sekenderaan / kapasiti (atau yuran tetap kaedah lama)."""
    if d is not None:
        s = activity_session_on(db, user.id, d)
        if s is not None:
            return 0.0 if (activity_is_free(s) or s.fee_by_assoc) else activity_price(s, vehicle_type, vehicle)
    col = db.get(models.College, user.college_id) if user.college_id else None
    return fee_amount(db, vehicle_type, col.category) if col else 0.0


def pickup_window(s: models.TrainingSession) -> str:
    return f"{fmt12(s.pickup_start)} – {fmt12(s.pickup_end)}"


# ---------------------------------------------------------------- generate

def _session_over(d: date, s: models.TrainingSession, now: datetime) -> bool:
    end = datetime.combine(d, s.end_time)
    if s.end_time <= s.start_time:
        end += timedelta(days=1)
    return now >= end


def generate_bookings(db: Session, today: date | None = None) -> int:
    """Jana booking daripada preferences. Idempotent. Booking yang ahli dah skip TIDAK dihidupkan semula.
    Latihan yang sudah DISAHKAN pun dijana untuk ahli yang baru masuk (cth baru daftar): mereka ditambah dan
    diisi ke seat kosong (kenderaan sedia ada tak diubah), dan dimaklumkan."""
    created = 0
    now = now_my() if today is None else datetime.combine(today, time.min)
    users = {u.id: u for u in db.query(models.User).filter_by(active=True)}
    colleges = {c.id: c for c in db.query(models.College)}
    for d, s in upcoming_dates(db, today):
        ev = get_or_create_event(db, s, d)
        if ev.status == EventStatus.cancelled:
            continue
        late = ev.status == EventStatus.finalised
        if late and _session_over(d, s, now):
            continue
        if not late and ev.status != EventStatus.open:
            continue
        excluded = excluded_codes(db, ev)
        touched = set()
        for p in (db.query(models.Preference).filter_by(session_id=s.id, active=True) if config.AUTO_FROM_PREFERENCES else []):
            u = users.get(p.user_id)
            col = colleges.get(u.college_id) if u else None
            if not u or not col or not col.transport_available:
                continue
            if s.one_off_date is None and not year_ok(db, u.member_no):
                continue  # aktiviti luar dibuka untuk semua ahli; latihan biasa ikut sesi dibenarkan
            pt = resolve_point(db, u)
            if pt is None:
                continue
            status = BookingStatus.ineligible if col.code.upper() in excluded else BookingStatus.confirmed
            for direction, wanted in ((Direction.going, p.going), (Direction.returning, p.returning)):
                if not wanted or (s.trip_only and s.trip_only != direction.value):
                    continue
                if db.query(models.Booking).filter_by(user_id=u.id, training_date=d, direction=direction).first():
                    continue
                db.add(models.Booking(user_id=u.id, session_id=s.id, training_date=d, direction=direction,
                                      pickup_point_id=pt.id, status=status))
                created += 1
                touched.add(u.id)
        db.flush()
        for uid in touched:
            _sync_payment(db, users[uid], d)
        assign_vehicles(db, ev)
        if late and touched:
            _late_join_notice(db, ev, touched)
    db.commit()
    return created


def ensure_events(db: Session):
    """Dipanggil semasa membaca data: hanya pastikan rekod latihan wujud (ringan). Penjanaan penuh & susunan
    dibuat oleh jadual harian / tindakan admin, bukan setiap kali halaman dibuka."""
    if config.AUTO_FROM_PREFERENCES:
        generate_bookings(db)
        return
    made = False
    for d, s in upcoming_dates(db):
        if db.query(models.TrainingEvent.id).filter_by(session_id=s.id, training_date=d).first() is None:
            db.add(models.TrainingEvent(session_id=s.id, training_date=d))
            made = True
    if made:
        db.commit()


def _late_join_notice(db: Session, ev: models.TrainingEvent, user_ids):
    """Ahli yang masuk selepas senarai disahkan: maklumkan kenderaan (jika dapat) atau status menunggu BKK."""
    d = ev.training_date
    for uid in user_ids:
        rows = db.query(models.Booking).filter_by(user_id=uid, training_date=d, session_id=ev.session_id,
                                                  status=BookingStatus.confirmed).all()
        if not rows or rows[0].vehicle_id or rows[0].ehailing:
            continue  # kenderaan / e-hailing sudah dimaklumkan
        _notify(db, uid, "car", f"Dimasukkan ke senarai: {fmt_date(d)}",
                "Senarai latihan ini sudah disahkan. Belum ada tempat kosong untuk anda; "
                "BKK akan maklumkan jika ada kenderaan atau uruskan e-hailing.", d)


def reconcile_user(db: Session, user: models.User):
    """Selepas ahli tukar preferences/kolej: selaraskan booking pada latihan 'open' akan datang."""
    prefs = {p.session_id: p for p in db.query(models.Preference).filter_by(user_id=user.id)}
    pt_all = resolve_point(db, user)
    regular_ok = year_ok(db, user.member_no)
    sess = {s.id: s for s in db.query(models.TrainingSession)}
    events = (db.query(models.TrainingEvent)
              .filter(models.TrainingEvent.training_date >= today_my(),
                      models.TrainingEvent.status == EventStatus.open).all())
    for ev in events:
        p = prefs.get(ev.session_id)
        pt = pt_all if (regular_ok or sess[ev.session_id].one_off_date is not None) else None
        rows = db.query(models.Booking).filter_by(user_id=user.id, training_date=ev.training_date).all()
        for b in rows:
            if b.pickup_place:
                continue  # aktiviti luar dengan tempat ambil pilihan sendiri: tak bergantung pada kolej
            wanted = bool(p and p.active and (p.going if b.direction == Direction.going else p.returning))
            wanted = wanted or b.manual or not config.AUTO_FROM_PREFERENCES  # dipilih ikut tarikh: kekal walaupun jadual berulang tak termasuk
            if pt is None or not wanted:
                if b.status in (BookingStatus.confirmed, BookingStatus.ineligible):
                    b.status, b.vehicle_id = BookingStatus.skipped, None
            elif pt is not None:
                b.pickup_point_id = pt.id
        db.flush()
        apply_venue(db, ev)
    generate_bookings(db)


# ---------------------------------------------------------------- venue / exclusion

def apply_venue(db: Session, ev: models.TrainingEvent):
    """Semak kolej terkecuali ikut tempat latihan; selaras bayaran; susun kereta."""
    if ev.status == EventStatus.cancelled:
        return
    excluded = excluded_codes(db, ev)
    users = {u.id: u for u in db.query(models.User)}
    colleges = {c.id: c for c in db.query(models.College)}
    rows = db.query(models.Booking).filter_by(training_date=ev.training_date, session_id=ev.session_id).all()
    changed = {}
    for b in rows:
        u = users[b.user_id]
        col = colleges.get(u.college_id)
        is_ex = bool(col and col.code.upper() in excluded)
        if b.status == BookingStatus.confirmed and is_ex:
            b.status, b.vehicle_id = BookingStatus.ineligible, None
            changed[u.id] = True
        elif b.status == BookingStatus.ineligible and not is_ex:
            b.status = BookingStatus.confirmed
            changed[u.id] = False
    db.flush()
    venue = db.get(models.Venue, ev.venue_id) if ev.venue_id else None
    for uid, lost in changed.items():
        if lost:
            _notify(db, uid, "venue", f"Tiada transport: {fmt_date(ev.training_date)}",
                    f"Latihan di {venue.name if venue else 'tempat baru'}: kolej anda terkecuali daripada kemudahan pengangkutan.",
                    ev.training_date)
        else:
            _notify(db, uid, "venue", f"Transport kembali: {fmt_date(ev.training_date)}",
                    "Tempat latihan bertukar; anda layak semula menggunakan kemudahan pengangkutan.", ev.training_date)
    for uid in {b.user_id for b in rows}:
        _sync_payment(db, users[uid], ev.training_date)
    assign_vehicles(db, ev)


# ---------------------------------------------------------------- payments

def _confirmed_trips(db, user_id, d) -> int:
    """Trip yang dikenakan yuran persatuan. Trip e-hailing (tanpa kenderaan prebet) TIDAK dikira:
    ahli tempah & bayar e-hailing sendiri."""
    return db.query(models.Booking).filter(
        models.Booking.user_id == user_id, models.Booking.training_date == d,
        models.Booking.status == BookingStatus.confirmed,
        or_(models.Booking.vehicle_id.isnot(None), models.Booking.ehailing.is_(False))).count()


def _sync_payment(db: Session, user: models.User, d: date):
    """Pastikan bayaran selaras dengan booking: ada trip aktif = perlu bayar;
    tiada trip = batal (bayaran yang dah dibuat dibawa sebagai kredit, bukan dipulangkan)."""
    db.flush()
    trips = _confirmed_trips(db, user.id, d)
    af = activity_fee_on(db, user.id, d)
    if af is not None and af <= 0:
        trips = 0  # aktiviti percuma: tiada bayaran
    pay = db.query(models.Payment).filter_by(user_id=user.id, training_date=d).first()
    if trips > 0:
        if pay is None:
            db.add(models.Payment(user_id=user.id, training_date=d, amount=fee_for(db, user, d=d)))
        elif pay.status == PaymentStatus.void:
            pay.status = PaymentStatus.unpaid
        return
    if pay is None:
        return
    if pay.status in (PaymentStatus.unpaid, PaymentStatus.rejected):
        user.credit_balance += pay.credit_applied  # pulangkan kredit yang sempat digunakan
        pay.credit_applied = 0.0
        pay.status = PaymentStatus.void
    elif pay.status == PaymentStatus.paid:
        user.credit_balance += pay.amount          # tiada pemulangan tunai: dibawa ke latihan seterusnya
        pay.credit_applied = 0.0
        pay.status = PaymentStatus.void
        _notify(db, user.id, "payment", "Bayaran dibawa ke latihan seterusnya",
                f"RM{pay.amount:.2f} disimpan sebagai kredit untuk latihan akan datang.", d)
    # 'pending' dibiarkan; admin verify -> _sync_payment dipanggil semula


def payment_due(pay: models.Payment) -> float:
    return max(0.0, round(pay.amount - pay.credit_applied, 2))


def has_car(db: Session, user_id: int, d: date) -> bool:
    return db.query(models.Booking).filter(
        models.Booking.user_id == user_id, models.Booking.training_date == d,
        models.Booking.status == BookingStatus.confirmed,
        or_(models.Booking.vehicle_id.isnot(None), models.Booking.ehailing.is_(True))).first() is not None


def can_pay(db: Session, pay: models.Payment) -> bool:
    ev = event_on(db, pay.training_date)
    return bool(ev and ev.status == EventStatus.finalised
                and pay.status in (PaymentStatus.unpaid, PaymentStatus.rejected)
                and payment_due(pay) > 0 and has_car(db, pay.user_id, pay.training_date))


# ---------------------------------------------------------------- kehadiran prebet (boleh / tak boleh bawa)

def _deadline(d: date, s: models.TrainingSession | None = None) -> datetime:
    return cutoff_dt(d)


def last_session_date(db: Session, today: date | None = None) -> date:
    """Tarikh latihan terkini yang sudah bermula atau hari ini (cth Ahad -> Sabtu; Rabu -> Rabu).
    Kotak tarikh lepas kekal dipaparkan sehingga tarikh ini bertukar ke latihan seterusnya."""
    today = today or today_my()
    sessions = db.query(models.TrainingSession).filter_by(active=True).all()
    for back in range(0, 15):
        d = today - timedelta(days=back)
        for sess in sessions:
            if (sess.one_off_date == d) if sess.one_off_date is not None else (sess.day_of_week == d.weekday()):
                return d
    return today


def prebet_dates(db: Session, today: date | None = None, days: int | None = None, keep_recent: bool = False):
    """Tarikh latihan/aktiviti akan datang yang prebet perlu sahkan (tanpa cuti & latihan dibatalkan).
    keep_recent: untuk paparan, kekalkan kotak latihan terkini yang sudah tamat sehingga latihan seterusnya."""
    today = today or today_my()
    start = last_session_date(db, today) if keep_recent else today
    out = []
    n_days = (config.BOOK_DAYS_AHEAD if days is None else days) + (today - start).days
    for d, s in upcoming_dates(db, start, days=n_days):
        if is_holiday(db, d):
            continue
        ev = db.query(models.TrainingEvent).filter_by(session_id=s.id, training_date=d).first()
        if ev is not None and ev.status == EventStatus.cancelled:
            continue
        if _session_over(d, s, now_my()) and not (keep_recent and d >= start):
            continue
        out.append((d, s, ev))
    return out


def prebet_options(db: Session, user: models.User) -> list[dict]:
    """Senarai tarikh untuk prebet: status sahkan, kenderaan dipilih, waktu tutup, tugasan (jika senarai sudah disusun),
    senarai penumpang untuk diambil, dan tanda dah sampai / dah hantar."""
    rows = {r.training_date: r for r in db.query(models.PrebetAvailability).filter_by(user_id=user.id)}
    mine = prebet_vehicles(db, user.id)
    my_veh = {v.id for v in db.query(models.Vehicle).filter_by(driver_id=user.id)}
    now = now_my()
    out = []
    for d, s, ev in prebet_dates(db, keep_recent=True):
        r = rows.get(d)
        dl = _deadline(d, s)
        pick = next((v for v in mine if r and r.vehicle_id == v.id), mine[0] if mine else None)
        item = {"training_date": d.isoformat(), "session_name": s.name, "is_activity": s.one_off_date is not None,
                "start_time": s.start_time.strftime("%H:%M"), "pickup_window": pickup_window(s),
                "arrive_by": arrive_by(s),
                "venue": None, "available": None if r is None else r.available,
                "by_admin": bool(r and r.by_admin), "deadline": dl.isoformat(),
                "deadline_passed": now >= dl, "event_status": ev.status.value if ev else "open",
                "vehicles": [vehicle_card(v) for v in mine], "vehicle_id": pick.id if pick else None,
                "stops": [], "passengers": 0, "pickups": [], "task": "", "ticks": None,
                "past": _session_over(d, s, now)}
        if ev is not None and ev.venue_id:
            v = db.get(models.Venue, ev.venue_id)
            item["venue"] = v.name if v else None
        if ev is not None:
            bks = db.query(models.Booking).filter(
                models.Booking.training_date == d, models.Booking.session_id == s.id,
                models.Booking.status == BookingStatus.confirmed, models.Booking.vehicle_id.in_(list(my_veh) or [0])).all()
            if bks:
                m = manifest(db, d, vehicle_ids=my_veh, for_driver=True)
                stops, pickups = [], []
                for c in m["cars"]:
                    stops += [{"college": st["college"], "checkpoint": st["checkpoint"], "count": st["count"],
                               "names": st["names"]} for st in c["stops"]]
                    pickups += [{"name": x["name"], "phone": x["phone"], "block": x["block"], "college": x["college"],
                                 "checkpoint": x["checkpoint"], "places": x.get("places"), "directions": x["directions"]} for x in c["passengers"]]
                item["stops"] = stops
                item["pickups"] = pickups if ev.status == EventStatus.finalised else []
                item["passengers"] = len({b.user_id for b in bks})
                item["ticks"] = ticks_for(db, user.id, d) if ev.status == EventStatus.finalised else None
                item["task"] = (f"Ambil penumpang di checkpoint di bawah (penumpang di checkpoint {arrive_by(s)}; "
                                f"anda ambil {pickup_window(s)}), kemudian ke tempat latihan. "
                                if ev.status == EventStatus.finalised else
                                "Senarai belum disahkan; butiran boleh berubah. ")
            elif r is not None and r.available and ev.status == EventStatus.finalised:
                item["task"] = "Tak diperlukan kali ini. Tiada bayaran untuk latihan ini."
        out.append(item)
    return out


def set_availability(db: Session, user: models.User, d: date, available: bool, by_admin: bool = False,
                     vehicle_id: int | None = None):
    """Prebet (atau admin bagi pihak prebet) sahkan boleh/tak boleh bawa pada satu tarikh, dan pilih kenderaan yang digunakan.
    Selepas waktu tutup (lalai 5 petang hari latihan) hanya admin boleh ubah."""
    row_dates = {x[0] for x in prebet_dates(db)}
    if d not in row_dates:
        if is_holiday(db, d):
            raise ValueError("Tarikh ini cuti, tiada pengangkutan")
        raise ValueError("Tiada latihan pada tarikh ini")
    if not by_admin and member_closed(d):
        raise ValueError(f"Pengesahan ditutup pada {fmt12(_hm(config.CUTOFF_TIME))} hari latihan. Sila hubungi BKK.")
    mine = prebet_vehicles(db, user.id)
    if vehicle_id is not None and vehicle_id not in {v.id for v in mine}:
        raise ValueError("Kenderaan itu bukan milik anda atau belum diluluskan")
    vids = [v.id for v in db.query(models.Vehicle).filter_by(driver_id=user.id)]
    if not available:
        ev = event_on(db, d)
        if ev is not None and ev.status == EventStatus.finalised and vids and db.query(models.Booking).filter(
                models.Booking.training_date == d, models.Booking.vehicle_id.in_(vids),
                models.Booking.status == BookingStatus.confirmed).first():
            raise ValueError("Senarai dah disahkan dan ada penumpang dalam kenderaan anda. Sila hubungi BKK.")
    row = db.query(models.PrebetAvailability).filter_by(user_id=user.id, training_date=d).first()
    if row is None:
        row = models.PrebetAvailability(user_id=user.id, training_date=d)
        db.add(row)
    row.available, row.by_admin = available, by_admin
    if vehicle_id is not None:
        row.vehicle_id = vehicle_id
    db.flush()
    resolve_warning(db, user.id, f"avail:{user.id}:{d.isoformat()}")
    if by_admin:
        _notify(db, user.id, "driver", f"BKK sahkan {fmt_date(d)} untuk anda: {'boleh bawa' if available else 'tak boleh bawa'}",
                "Jika salah, tukar sendiri di tab Utama.", d, severity="info", link="/prebet")
    for ev in db.query(models.TrainingEvent).filter_by(training_date=d):
        if ev.status != EventStatus.cancelled:
            assign_vehicles(db, ev)
    db.commit()


def send_prebet_notices(db: Session, now: datetime | None = None) -> int:
    """Maklumkan prebet tentang tarikh latihan yang belum disahkan. Menghampiri tarikh akhir jadi amaran.
    Peringatan ke admin bila tarikh akhir lepas dan ada prebet belum sahkan."""
    now = now or now_my()
    if not config.REQUIRE_PREBET_CONFIRM:
        return 0
    sent = 0
    prebets = prebet_users(db)
    for d, s, ev in prebet_dates(db):
        dl = _deadline(d, s)
        answered = {r.user_id for r in db.query(models.PrebetAvailability).filter_by(training_date=d)}
        soon = now >= dl - timedelta(hours=24)
        missing = []
        for u in prebets:
            if u.id in answered:
                continue
            missing.append(u)
            ref = f"avail:{u.id}:{d.isoformat()}"
            old = db.query(models.Notification).filter_by(user_id=u.id, ref=ref).first()
            sev = "warning" if soon else "task"
            if old is None:
                left = "Waktu sahkan telah tutup, hubungi BKK." if now >= dl else f"Sahkan sebelum {dl.strftime('%d/%m %I:%M %p')} (hari latihan)."
                _notify(db, u.id, "driver", f"Boleh bawa penumpang {fmt_date(d)}?",
                        f"Ada latihan {s.name} pada {fmt_date(d)}. {left}", d, severity=sev, link="/prebet", ref=ref)
                sent += 1
            elif old.severity != sev:
                old.severity, old.read = sev, False
                old.title = f"Peringatan: sahkan {fmt_date(d)}"
                old.body = f"Tarikh akhir sahkan {dl.strftime('%d/%m %I:%M %p')}. Belum sahkan boleh/tak boleh bawa."
                sent += 1
        if missing and now >= dl:
            for a in db.query(models.User).filter_by(role=models.Role.admin, active=True):
                _notify(db, a.id, "admin_alert", f"{len(missing)} prebet belum sahkan {fmt_date(d)}",
                        "Sahkan bagi pihak mereka di tab Penumpang/Prebet atau hubungi mereka.", d,
                        severity="warning", link="/admin?tab=summary", ref=f"unconf:{d.isoformat()}")
        else:
            for a in db.query(models.User).filter_by(role=models.Role.admin, active=True):
                resolve_warning(db, a.id, f"unconf:{d.isoformat()}")
    db.commit()
    return sent


def send_licence_reminders(db: Session, today: date | None = None) -> int:
    """Lesen hampir tamat / tamat / belum diisi: ingatkan prebet (amaran, hilang bila dikemas kini)."""
    today = today or today_my()
    sent = 0
    for u in prebet_users(db):
        ref = f"licence:{u.id}"
        if not u.licence_file or u.licence_expiry is None:
            _notify(db, u.id, "driver", "Lengkapkan gambar lesen",
                    "Gambar lesen dan tarikh tamat diperlukan di tab Profil.", severity="warning", link="/profil", ref=ref)
            sent += 1
            continue
        left = (u.licence_expiry - today).days
        if left < 0:
            _notify(db, u.id, "driver", "Lesen anda sudah tamat tempoh",
                    f"Tamat {u.licence_expiry.strftime('%d/%m/%Y')}. Kemas kini lesen di Profil.", severity="warning",
                    link="/profil", ref=ref)
            sent += 1
        elif left <= config.LICENCE_REMIND_DAYS:
            _notify(db, u.id, "driver", f"Lesen tamat dalam {left} hari",
                    f"Tamat {u.licence_expiry.strftime('%d/%m/%Y')}. Sila perbaharui dan kemas kini di Profil.",
                    severity="warning", link="/profil", ref=ref)
            sent += 1
        else:
            resolve_warning(db, u.id, ref)
    db.commit()
    return sent


def arrears(db: Session, user_id: int, today: date | None = None) -> dict:
    """Tunggakan (hutang) ahli: bayaran yang sudah melepasi tarikh akhir (12 tengah hari hari selepas latihan)
    tetapi belum dibayar. Ahli yang menunggak masih boleh naik; hanya disekat jika bayaran tertua melebihi ARREARS_BLOCK_DAYS."""
    now = now_my() if today is None else datetime.combine(today, time(23, 59))
    today = now.date()
    items = []
    for p in db.query(models.Payment).filter(models.Payment.user_id == user_id,
                                             models.Payment.status.in_((PaymentStatus.unpaid, PaymentStatus.rejected))
                                             ).order_by(models.Payment.training_date):
        if payment_due(p) > 0 and can_pay(db, p) and now >= pay_deadline(p.training_date):
            items.append(p)
    total = round(sum(payment_due(p) for p in items), 2)
    oldest = items[0].training_date if items else None
    days = (today - oldest).days if oldest else 0
    return {"total": total, "count": len(items), "oldest": oldest.isoformat() if oldest else None,
            "oldest_days": days, "blocked": bool(oldest and days > config.ARREARS_BLOCK_DAYS),
            "items": [{"id": p.id, "training_date": p.training_date.isoformat(), "due": payment_due(p),
                       "status": p.status.value} for p in items]}


# ---------------------------------------------------------------- vehicles

def prebet_confirmed_ids(db, d: date) -> set[int]:
    return {r.user_id for r in db.query(models.PrebetAvailability).filter_by(training_date=d, available=True)}


def _vehicles_for(db, d: date):
    """Kenderaan yang boleh disusun pada tarikh ini: diluluskan, aktif, hari tersedia, tak ditandakan tak boleh,
    dan (jika REQUIRE_PREBET_CONFIRM) pemandunya sudah sahkan 'boleh bawa'.
    Seorang prebet hanya satu kenderaan setiap tarikh: yang dipilihnya (atau yang pertama jika belum pilih)."""
    unavailable = {r.vehicle_id for r in db.query(models.VehicleUnavailable).filter_by(training_date=d)}
    confirmed = prebet_confirmed_ids(db, d) if config.REQUIRE_PREBET_CONFIRM else None
    chosen = {r.user_id: r.vehicle_id for r in db.query(models.PrebetAvailability).filter_by(training_date=d)}
    out, by_driver = [], {}
    for v in db.query(models.Vehicle).filter_by(active=True, approval=models.ApprovalStatus.approved).order_by(models.Vehicle.id):
        if str(d.weekday()) not in v.available_days.split(",") or v.id in unavailable:
            continue
        if confirmed is not None and v.driver_id and v.driver_id not in confirmed:
            continue
        if v.driver_id:
            by_driver.setdefault(v.driver_id, []).append(v)
        else:
            out.append(v)
    for uid, vs in by_driver.items():
        out.append(next((v for v in vs if chosen.get(uid) == v.id), vs[0]))
    return sorted(out, key=lambda v: v.id)


def prebet_vehicles(db: Session, user_id: int) -> list[models.Vehicle]:
    return db.query(models.Vehicle).filter_by(driver_id=user_id, active=True,
                                              approval=models.ApprovalStatus.approved).order_by(models.Vehicle.id).all()


def vehicle_card(v: models.Vehicle) -> dict:
    return {"id": v.id, "name": v.name, "brand": v.brand, "colour": v.colour, "plate_no": v.plate_no,
            "type": v.vehicle_type.value, "capacity": v.capacity, "desc": vehicle_desc(v)}


def chosen_vehicle(db: Session, user_id: int, d: date) -> models.Vehicle | None:
    vs = prebet_vehicles(db, user_id)
    if not vs:
        return None
    r = db.query(models.PrebetAvailability).filter_by(user_id=user_id, training_date=d).first()
    return next((v for v in vs if r and r.vehicle_id == v.id), vs[0])


# ---------------------------------------------------------------- tanda prebet: dah sampai / dah hantar

TICK_KINDS = {"arrived": "Dah sampai tempat latihan", "delivered": "Dah hantar semua (selepas latihan)"}


def _duty_driver_ids(db: Session, d: date) -> dict[int, list[int]]:
    """Prebet yang ada tugasan pada tarikh ini -> senarai kenderaan."""
    rows = db.query(models.Booking.vehicle_id).filter(
        models.Booking.training_date == d, models.Booking.status == BookingStatus.confirmed,
        models.Booking.vehicle_id.isnot(None)).distinct().all()
    out: dict[int, list[int]] = {}
    for (vid,) in rows:
        v = db.get(models.Vehicle, vid)
        if v and v.driver_id:
            out.setdefault(v.driver_id, []).append(vid)
    return out


def ticks_for(db: Session, user_id: int, d: date) -> dict:
    got = {t.kind: t.created_at.isoformat() for t in db.query(models.DutyTick).filter_by(user_id=user_id, training_date=d)}
    return {k: got.get(k) for k in TICK_KINDS}


def set_tick(db: Session, user: models.User, d: date, kind: str, on: bool = True):
    if kind not in TICK_KINDS:
        raise ValueError("Jenis tanda tak sah")
    ev = event_on(db, d)
    if ev is None or ev.status != EventStatus.finalised or user.id not in _duty_driver_ids(db, d):
        raise ValueError("Anda tiada tugasan pada tarikh ini")
    row = db.query(models.DutyTick).filter_by(user_id=user.id, training_date=d, kind=kind).first()
    if on and row is None:
        db.add(models.DutyTick(user_id=user.id, training_date=d, kind=kind, created_at=now_my()))
    elif not on and row is not None:
        db.delete(row)
    db.flush()
    if on:
        resolve_warning(db, user.id, f"tick:{kind}:{user.id}:{d.isoformat()}")
        for t in db.query(models.User).filter_by(is_treasurer=True, active=True):
            resolve_warning(db, t.id, f"tickmiss:{kind}:{user.id}:{d.isoformat()}")


def send_tick_warnings(db: Session, now: datetime | None = None) -> int:
    """Prebet bertugas tetapi belum tanda: amaran kepada prebet dan bendahari sahaja (prebet tetap dibayar)."""
    now = now or now_my()
    sent = 0
    treasurers = db.query(models.User).filter_by(is_treasurer=True, active=True).all()
    for ev in db.query(models.TrainingEvent).filter(
            models.TrainingEvent.status == EventStatus.finalised,
            models.TrainingEvent.training_date >= now.date() - timedelta(days=2),
            models.TrainingEvent.training_date <= now.date()).all():
        d = ev.training_date
        s = db.get(models.TrainingSession, ev.session_id)
        start = datetime.combine(d, s.start_time)
        end = datetime.combine(d, s.end_time) + (timedelta(days=1) if s.end_time <= s.start_time else timedelta())
        due = {"arrived": start + timedelta(minutes=30), "delivered": end + timedelta(minutes=60)}
        for uid in _duty_driver_ids(db, d):
            have = {t.kind for t in db.query(models.DutyTick).filter_by(user_id=uid, training_date=d)}
            u = db.get(models.User, uid)
            for kind, when in due.items():
                if kind in have or now < when:
                    continue
                label = TICK_KINDS[kind]
                _notify(db, uid, "driver", f"Belum tanda: {label.lower()} ({fmt_date(d)})",
                        "Sila tekan butang tanda di tab Utama. Anda tetap dibayar, ini untuk rekod BKK & bendahari.", d,
                        severity="warning", link="/prebet", ref=f"tick:{kind}:{uid}:{d.isoformat()}")
                for t in treasurers:
                    _notify(db, t.id, "payout_due", f"{short(u)} belum tanda '{label.lower()}' ({fmt_date(d)})",
                            "Amaran sahaja: prebet tetap dibayar.", d, severity="warning", link="/bendahari",
                            ref=f"tickmiss:{kind}:{uid}:{d.isoformat()}")
                sent += 1
    db.commit()
    return sent


def payout_category(uids, users: dict, colleges: dict) -> str:
    """Kategori bayaran prebet ikut PENUMPANG (bukan kolej prebet): jika ada seorang pun penumpang
    kolej jauh dalam kenderaan itu = kadar jauh, selain itu dekat. Sama untuk kereta & motosikal."""
    for uid in uids:
        u = users.get(uid)
        col = colleges.get(u.college_id) if u is not None and u.college_id else None
        if col is not None and col.category == "jauh":
            return "jauh"
    return "dekat"


def vehicle_category(db: Session, v: models.Vehicle, colleges: dict | None = None) -> str | None:
    """Kategori kolej kenderaan: ditetapkan admin, atau ikut kolej pemandu. None = neutral (ambil mana-mana)."""
    if v.category in ("dekat", "jauh"):
        return v.category
    drv = db.get(models.User, v.driver_id) if v.driver_id else None
    if drv is None or not drv.college_id:
        return None
    col = colleges.get(drv.college_id) if colleges is not None else db.get(models.College, drv.college_id)
    return col.category if col and col.category in ("dekat", "jauh") else None


def vehicle_zone(db: Session, v: models.Vehicle, colleges: dict | None = None) -> tuple[str | None, str | None]:
    """(zon, kod kolej pemandu). Zon: dekat | jauhA | jauhB | None (neutral). Admin boleh tetapkan 'dekat'/'jauh' pada kenderaan."""
    drv = db.get(models.User, v.driver_id) if v.driver_id else None
    col = None
    if drv is not None and drv.college_id:
        col = colleges.get(drv.college_id) if colleges is not None else db.get(models.College, drv.college_id)
    code = col.code if col else None
    if v.category == "dekat":
        return "dekat", code
    if v.category == "jauh":
        z = zone_of(code, col.category) if col and col.category == "jauh" else "jauhB"
        return z, code
    return (zone_of(code, col.category) if col else None), code


def assign_vehicles(db: Session, ev: models.TrainingEvent):
    """Susun kenderaan (kereta dahulu, kemudian motosikal; peraturan seat ikut jantina; zon kolej prebet).
    Latihan 'open': susun semula penuh. Selepas disahkan: kekalkan yang sedia ada,
    hanya isi ahli yang belum ada kenderaan ke seat kosong."""
    if ev.status == EventStatus.cancelled:
        return
    db.flush()
    d = ev.training_date
    sess = db.get(models.TrainingSession, ev.session_id)
    rows = db.query(models.Booking).filter_by(training_date=d, session_id=ev.session_id,
                                              status=BookingStatus.confirmed).all()
    by_user = defaultdict(list)
    for b in rows:
        by_user[b.user_id].append(b)
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(list(by_user) or [0]))}
    colleges = {c.id: c for c in db.query(models.College)}
    ordered = sorted(by_user, key=lambda uid: (by_user[uid][0].pickup_point_id or 0, uid))

    def member_info(u, first):
        if first.pickup_place:  # diambil dari tempat lain: neutral, dikumpul ikut nama tempat (prioriti kolej didahulukan)
            return None, None, "@" + first.pickup_place.lower()
        col = colleges.get(u.college_id) if u.college_id else None
        cat = col.category if col and col.category in ("dekat", "jauh") else None
        return cat, (zone_of(col.code, cat) if col else None), (col.code if col else None)

    members = []
    for uid in ordered:
        cat, zone, code = member_info(users[uid], next((b for b in by_user[uid] if b.direction == Direction.going), by_user[uid][0]))
        members.append({
            "user_id": uid,
            "gender": users[uid].gender.value if users[uid].gender in (Gender.male, Gender.female) else "male",
            "dirs": {b.direction.value for b in by_user[uid]},
            "current_vehicle_id": by_user[uid][0].vehicle_id,
            "category": cat, "zone": zone, "college": code, "college_group": college_group(code) if code else None})
    veh_rows = _vehicles_for(db, d)
    if not motor_allowed(sess):
        veh_rows = [v for v in veh_rows if v.vehicle_type != VehicleType.motorcycle]
    vehicles = []
    for v in veh_rows:
        zone, code = vehicle_zone(db, v, colleges)
        vehicles.append({"id": v.id, "type": v.vehicle_type.value, "driver_gender": v.driver_gender.value,
                         "rows": parse_rows(v.seat_rows), "category": vehicle_category(db, v, colleges),
                         "zone": zone, "college": code, "college_group": college_group(code) if code else None})
    finalised = ev.status == EventStatus.finalised
    lone_rule = config.LONE_FEMALE_RULE
    plan = plan_assignment(members, vehicles, keep_existing=finalised,
                           combine_below=config.COMBINE_BELOW_PASSENGERS, no_lone_female=lone_rule)
    for uid, vid in plan.items():
        prev = by_user[uid][0].vehicle_id
        for b in by_user[uid]:
            b.vehicle_id = vid
            if vid is not None:
                b.ehailing, b.ehailing_note = False, ""  # dapat prebet: e-hailing tak diperlukan
        if finalised and prev is None and vid is not None:
            _notify(db, uid, "car", f"Kenderaan ditetapkan: {fmt_date(d)}",
                    _car_text(db, db.get(models.Vehicle, vid)), d)
            v = db.get(models.Vehicle, vid)
            if v and v.driver_id:
                _notify(db, v.driver_id, "driver", f"Penumpang ditambah: {fmt_date(d)}",
                        f"{short(users[uid])} ({_college_label(db, users[uid])}) dimasukkan ke kenderaan anda. Lihat tab Utama.",
                        d, link="/prebet")
    db.flush()
    # Perempuan yang akan jadi seorang diri dengan prebet lelaki: terus ke e-hailing (tiada keputusan admin diperlukan)
    _sync_lone_warnings(db, ev, set(), users)
    refresh_fees(db, ev)


def _college_label(db, u: models.User) -> str:
    col = db.get(models.College, u.college_id) if u.college_id else None
    return college_group(col.code) if col else (u.college_other or "-")


def _sync_lone_warnings(db, ev, flagged: set[int], users):
    """Amaran kepada admin: ahli perempuan tunggal yang tak boleh dimasukkan ikut peraturan. Hilang sendiri bila selesai."""
    prefix = f"lone:{ev.id}:"
    admins = db.query(models.User).filter_by(role=models.Role.admin, active=True).all()
    for a in admins:
        for n in db.query(models.Notification).filter(models.Notification.user_id == a.id,
                                                      models.Notification.ref.like(prefix + "%")):
            uid = n.ref.rsplit(":", 1)[1]
            if not uid.isdigit() or int(uid) not in flagged:
                db.delete(n)
    for uid in flagged:
        u = users.get(uid) or db.get(models.User, uid)
        for a in admins:
            _notify(db, a.id, "admin_alert", f"Perlu keputusan: {u.name} ({fmt_date(ev.training_date)})",
                    f"{u.name} ({_college_label(db, u)}) perempuan seorang diri dalam kereta pemandu lelaki. "
                    "Cadangan: tandakan e-hailing, atau tukar manual di Peta Kerusi.",
                    ev.training_date, severity="warning", link="/admin?tab=summary", ref=f"{prefix}{uid}")


def flagged_lone_ids(db, ev) -> set[int]:
    out = set()
    for n in db.query(models.Notification.ref).filter(models.Notification.ref.like(f"lone:{ev.id}:%")):
        tail = n[0].rsplit(":", 1)[1]
        if tail.isdigit():
            out.add(int(tail))
    return out


def refresh_fees(db: Session, ev: models.TrainingEvent):
    """Yuran ikut jenis kenderaan yang ditetapkan (kereta/motor). Hanya bayaran yang belum dibayar."""
    d = ev.training_date
    vehicles = {v.id: v for v in db.query(models.Vehicle)}
    seen = {}
    for b in db.query(models.Booking).filter_by(training_date=d, session_id=ev.session_id,
                                                status=BookingStatus.confirmed):
        seen.setdefault(b.user_id, b)
    for uid, b in seen.items():
        _sync_payment(db, db.get(models.User, uid), d)  # e-hailing = tiada yuran; dapat kenderaan = yuran semula
        pay = db.query(models.Payment).filter_by(user_id=uid, training_date=d).first()
        if pay is None or pay.status not in (PaymentStatus.unpaid, PaymentStatus.rejected) or pay.credit_applied:
            continue
        v = vehicles.get(b.vehicle_id) if b.vehicle_id else None
        pay.amount = fee_for(db, db.get(models.User, uid), v.vehicle_type.value if v else "car", d=d, vehicle=v)
    db.flush()


def _car_text(db, v: models.Vehicle | None) -> str:
    """cth: 'Kereta: Ali (Saga, silver & ABC123), tel 0123456789'. Penumpang tahu kenderaan mana untuk dinaiki."""
    if v is None:
        return ""
    drv = db.get(models.User, v.driver_id) if v.driver_id else None
    label = "Motosikal" if v.vehicle_type == VehicleType.motorcycle else "Kereta"
    who = short(drv) if drv else v.name
    txt = f"{label}: {who} ({vehicle_desc(v)})"
    if drv:
        txt += f", tel {drv.phone}"
    return txt


# ---------------------------------------------------------------- skip / finalise / cancel

def set_skip(db: Session, user: models.User, d: date, skip: bool) -> int:
    if d < today_my():
        raise ValueError("Tarikh dah lepas")
    ev = event_on(db, d)
    if ev is None:
        raise ValueError("Tiada latihan pada tarikh ini")
    if ev.status == EventStatus.cancelled:
        raise ValueError("Latihan ini dibatalkan")
    if member_closed(d):
        raise ValueError(f"Pilihan ditutup pada {fmt12(_hm(config.CUTOFF_TIME))} hari latihan. Sila hubungi BKK jika ada perubahan.")
    if ev.status == EventStatus.finalised:
        raise ValueError("Senarai dah disahkan dan kereta dikunci. Sila hubungi BKK jika tak dapat hadir.")
    frm, to = (BookingStatus.confirmed, BookingStatus.skipped) if skip else (BookingStatus.skipped, BookingStatus.confirmed)
    rows = db.query(models.Booking).filter_by(user_id=user.id, training_date=d, status=frm).all()
    for b in rows:
        b.status = to
        if skip:
            b.vehicle_id = None
    db.flush()
    apply_venue(db, ev)
    db.commit()
    return len(rows)


# ---------------------------------------------------------------- pilih ikut tarikh

def _walk_msg(db: Session, ev: models.TrainingEvent | None) -> str:
    v = db.get(models.Venue, ev.venue_id) if ev is not None and ev.venue_id else None
    return (f"Latihan di {v.name if v else 'tempat ini'}: kolej anda sama atau terlalu dekat dengan tempat latihan, "
            "jadi tiada pengangkutan. Sila berjalan kaki.")


def date_options(db: Session, user: models.User) -> list[dict]:
    """Senarai tarikh latihan/aktiviti akan datang beserta status tempahan ahli (untuk pilih ikut tarikh)."""
    today, now = today_my(), now_my()
    el, act = eligibility(db, user), eligibility(db, user, activity=True)
    prefs = {p.session_id: p for p in db.query(models.Preference).filter_by(user_id=user.id)}
    out = []
    for d, s in upcoming_dates(db, today, days=config.BOOK_DAYS_AHEAD):
        ev = db.query(models.TrainingEvent).filter_by(session_id=s.id, training_date=d).first()
        ev_status = ev.status.value if ev else "open"
        if ev_status == "cancelled" or _session_over(d, s, now):
            continue
        e = act if s.one_off_date else el
        hol = holiday_note(db, d)
        if hol:
            e = {**e, "eligible": False, "reason": f"🌴 {hol}: tiada pengangkutan pada tarikh ini."}
        rows = {b.direction.value: b for b in db.query(models.Booking).filter_by(
            user_id=user.id, training_date=d, session_id=s.id)}
        live = (BookingStatus.confirmed, BookingStatus.ineligible)

        def is_on(direction):
            b = rows.get(direction)
            return bool(b and b.status in live)

        first = next((b for b in rows.values() if b.status == BookingStatus.confirmed), None)
        veh = db.get(models.Vehicle, first.vehicle_id) if first and first.vehicle_id else None
        p = prefs.get(s.id)
        on = is_on("going") or is_on("returning")
        excluded_here = any(b.status == BookingStatus.ineligible for b in rows.values())
        ucol = db.get(models.College, user.college_id) if user.college_id else None
        walk = bool(ev and ucol and ucol.code.upper() in excluded_codes(db, ev))
        if hol:
            note = e["reason"]
        elif walk:
            note = "🚶 " + _walk_msg(db, ev)
        elif not e["eligible"]:
            note = e["reason"]
        elif not on:
            note = ""
        elif excluded_here:
            note = "Kolej anda terkecuali daripada kemudahan pengangkutan untuk tempat latihan ini."
        elif veh is not None:
            note = ""
        elif first is not None and first.ehailing:
            note = "BKK uruskan e-hailing untuk anda."
        elif ev_status == "finalised":
            note = "Anda dalam senarai, tetapi senarai sudah disahkan dan belum ada tempat kosong. BKK akan maklumkan atau uruskan e-hailing."
        else:
            note = "Anda dalam senarai. Kenderaan ditetapkan bila senarai disusun dan disahkan."
        out.append({
            "in_list": on, "note": note, "walk": walk, "holiday": hol,
            "km": s.km, "motor_allowed": motor_allowed(s),
            "training_date": d.isoformat(), "session_id": s.id, "session_name": s.name,
            "is_activity": s.one_off_date is not None, "trip_only": s.trip_only,
            "start_time": s.start_time.strftime("%H:%M"), "end_time": s.end_time.strftime("%H:%M"),
            "pickup_window": pickup_window(s), "event_status": ev_status,
            "eligible": e["eligible"], "reason": e["reason"],
            "going": is_on("going"), "returning": is_on("returning"),
            "excluded": any(b.status == BookingStatus.ineligible for b in rows.values()),
            "recurring": bool(p and p.active),
            "car": _car_text(db, veh) if veh else "",
            "ehailing": bool(first and first.ehailing and not first.vehicle_id),
            "can_remove": ev_status == "open",
            **_pickup_info(db, user, s, rows),
        })
    return out


def _pickup_info(db: Session, user: models.User, s: models.TrainingSession, rows: dict) -> dict:
    """Maklumat tempat ambil (pergi) dan hantar (balik) untuk aktiviti luar (kosong untuk latihan biasa)."""
    if s.one_off_date is None:
        return {}
    mode = s.pickup_mode if s.pickup_mode in CHOOSE_MODES else "kedua"
    pt = resolve_point(db, user)
    ucol = db.get(models.College, user.college_id) if user.college_id else None
    has_point = pt is not None and bool(ucol and ucol.transport_available)
    mine = {}
    for k in ("going", "returning"):
        b = rows.get(k)
        if b is not None and b.status in (BookingStatus.confirmed, BookingStatus.ineligible):
            mine[k] = {"kind": "tempat" if b.pickup_place else "kolej",
                       "place": b.pickup_place or (pt.name if pt else "")}
    return {"pickup_mode": mode, "pickup_mode_label": PICKUP_MODES[mode],
            "fixed_go": fixed_place(s, "going"), "fixed_return": fixed_place(s, "returning"),
            "can_kolej": has_point and mode in ("kolej", "kedua"), "college_point": pt.name if has_point else "",
            "can_tempat": mode in ("rumah", "kedua") or not has_point,
            "my_pickup": mine.get("going") or mine.get("returning"), "my_places": mine,
            "assoc_pays": bool(s.fee_by_assoc)}


def book_date(db: Session, user: models.User, d: date, session_id: int, going: bool, returning: bool,
              by_admin: bool = False, pickup: str | None = None, place: str | None = None,
              return_pickup: str | None = None, return_place: str | None = None) -> dict:
    """Ahli pilih (atau batal) trip untuk satu tarikh tertentu. Pada latihan 'open' ahli masuk dalam susunan;
    pada latihan yang sudah disahkan ahli ditambah ke seat kosong (kenderaan sedia ada tak diubah)."""
    s = db.get(models.TrainingSession, session_id)
    if s is None or not s.active or not any(
            x == d and y.id == s.id for x, y in upcoming_dates(db, today_my(), days=config.BOOK_DAYS_AHEAD)):
        raise ValueError("Tarikh latihan tak sah")
    if (going or returning) and is_holiday(db, d):
        raise ValueError(f"{fmt_date(d)} cuti ({holiday_note(db, d)}): tiada pengangkutan")
    if not by_admin and member_closed(d):
        raise ValueError(f"Pilihan ditutup pada {fmt12(_hm(config.CUTOFF_TIME))} hari latihan. Sila hubungi BKK jika ada perubahan.")
    if not by_admin and (going or returning) and arrears(db, user.id)["blocked"]:
        raise ValueError("Bayaran tertunggak lebih 6 bulan. Sila jelaskan dahulu di tab Bayaran sebelum menempah.")
    e = eligibility(db, user, activity=s.one_off_date is not None)
    wanted = {"going": going, "returning": returning}
    if s.trip_only and any(v for k, v in wanted.items() if k != s.trip_only):
        raise ValueError("Aktiviti ini hanya untuk satu arah")
    ev = get_or_create_event(db, s, d)
    if ev.status == EventStatus.cancelled:
        raise ValueError("Latihan ini dibatalkan")
    finalised = ev.status == EventStatus.finalised
    if _session_over(d, s, now_my()):
        raise ValueError("Latihan ini sudah tamat")
    rows = {b.direction.value: b for b in db.query(models.Booking).filter_by(
        user_id=user.id, training_date=d, session_id=s.id)}
    other = db.query(models.Booking).filter(
        models.Booking.user_id == user.id, models.Booking.training_date == d,
        models.Booking.session_id != s.id, models.Booking.status.in_((BookingStatus.confirmed, BookingStatus.ineligible))).first()
    if other is not None and (going or returning):
        raise ValueError("Anda sudah ada tempahan lain pada tarikh ini")

    if not (going or returning):  # batal
        if finalised and not by_admin:
            raise ValueError("Senarai dah disahkan dan kereta dikunci. Sila hubungi BKK jika tak dapat hadir.")
        for b in rows.values():
            if b.status in (BookingStatus.confirmed, BookingStatus.ineligible):
                b.status, b.vehicle_id = BookingStatus.skipped, None
        db.flush()
        apply_venue(db, ev)
        db.commit()
        return {"ok": True}

    if not e["eligible"]:
        raise ValueError(e["reason"])
    is_act = s.one_off_date is not None
    pt = resolve_point(db, user)
    live = (BookingStatus.confirmed, BookingStatus.ineligible)
    res: dict[str, tuple[str, str]] = {}   # arah -> (kolej|tempat, nama tempat)

    def choice(k: str):
        if k == "returning" and return_pickup is not None:
            return return_pickup, return_place
        if pickup is not None:   # balik ikut pilihan pergi jika ahli tak pilih berasingan
            return pickup, place
        cur = rows.get(k)        # kekalkan pilihan sedia ada bila ahli hanya tukar pergi/balik
        if cur is None or cur.status not in live:
            cur = next((b for b in rows.values() if b.status in live), None)
        if cur is not None and (cur.pickup_place or cur.pickup_point_id):
            return ("tempat", cur.pickup_place) if cur.pickup_place else ("kolej", None)
        return None, None

    for k, v in wanted.items():
        if not v:
            continue
        if is_act:
            pk, pl = choice(k)
            res[k] = resolve_activity_pickup(s, pt, pk, pl, k)
        elif pt is None:
            raise ValueError("Belum ada checkpoint untuk kolej anda. Hubungi BKK.")
        else:
            res[k] = ("kolej", "")
    pts_id = {k: (pt.id if kind == "kolej" and pt is not None else None) for k, (kind, _pl) in res.items()}
    if finalised and not by_admin:
        for k, v in wanted.items():
            b = rows.get(k)
            if not v and b is not None and b.status == BookingStatus.confirmed:
                raise ValueError("Senarai dah disahkan dan kereta dikunci. Sila hubungi BKK jika tak dapat hadir.")
    col = db.get(models.College, user.college_id) if user.college_id else None
    if any(kind == "kolej" for kind, _pl in res.values()) and col and col.code.upper() in excluded_codes(db, ev):
        raise ValueError(_walk_msg(db, ev))
    status = BookingStatus.confirmed
    added = False
    for k, v in wanted.items():
        b = rows.get(k)
        if v:
            if b is None:
                db.add(models.Booking(user_id=user.id, session_id=s.id, training_date=d, direction=Direction(k),
                                      pickup_point_id=pts_id[k], pickup_place=res[k][1], status=status, manual=True))
                added = True
            elif b.status in (BookingStatus.skipped, BookingStatus.cancelled):
                b.status, b.manual, b.pickup_point_id, b.pickup_place = status, True, pts_id[k], res[k][1]
                added = True
            else:
                b.manual = True
                if is_act:
                    b.pickup_point_id, b.pickup_place = pts_id[k], res[k][1]
        elif b is not None and b.status in (BookingStatus.confirmed, BookingStatus.ineligible):
            b.status, b.vehicle_id = BookingStatus.skipped, None
    db.flush()
    _sync_payment(db, user, d)
    apply_venue(db, ev)
    if finalised and added:
        auto_ehailing(db, ev)
        _late_join_notice(db, ev, {user.id})
    db.commit()
    return {"ok": True}


def _clear_unfinalised(db: Session, ev: models.TrainingEvent) -> None:
    """Buang amaran 'senarai ditarik balik' daripada semua ahli (senarai sudah disahkan semula / latihan dibatalkan)."""
    db.query(models.Notification).filter(models.Notification.ref.like(f"unfin:{ev.id}:%")).delete(
        synchronize_session=False)


def finalise_event(db: Session, ev: models.TrainingEvent) -> int:
    """Sahkan senarai: kunci kereta, buka bayaran, maklumkan semua ahli. Return bil. ahli."""
    if ev.status != EventStatus.open:
        raise ValueError("Latihan ini sudah disahkan atau dibatalkan")
    apply_venue(db, ev)  # susun akhir
    _clear_unfinalised(db, ev)
    ev.status = EventStatus.finalised
    ev.auto_off = False
    ev.finalised_at = now_my()
    d = ev.training_date
    venue = db.get(models.Venue, ev.venue_id) if ev.venue_id else None
    rows = db.query(models.Booking).filter_by(training_date=d, session_id=ev.session_id,
                                              status=BookingStatus.confirmed).all()
    seen = {}
    for b in rows:
        seen.setdefault(b.user_id, b)
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(list(seen) or [0]))}
    s = db.get(models.TrainingSession, ev.session_id)
    flagged = flagged_lone_ids(db, ev)
    for uid, b in seen.items():
        u = users[uid]
        pay = db.query(models.Payment).filter_by(user_id=uid, training_date=d).first()
        if b.vehicle_id and pay and pay.status == PaymentStatus.unpaid and u.credit_balance > 0:
            use = min(u.credit_balance, payment_due(pay))
            pay.credit_applied += use
            u.credit_balance -= use
            if payment_due(pay) <= 0:
                pay.status = PaymentStatus.paid
        place = f" di {venue.name}" if venue else ""
        if b.vehicle_id:
            v = db.get(models.Vehicle, b.vehicle_id)
            due = payment_due(pay) if pay else 0
            if pay is None:
                pay_txt = "Percuma, tiada bayaran."
            elif pay.status == PaymentStatus.paid:
                pay_txt = "Bayaran telah dilangsaikan dengan kredit."
            else:
                pay_txt = f"Sila bayar RM{due:.2f} dan upload resit."
            body = (f"Latihan{place}. Sampai di checkpoint {pickup_point_name(db, b)} pada {arrive_by(s)} "
                    f"(prebet ambil {pickup_window(s)}). Naik: {_car_text(db, v)}. {pay_txt} "
                    f"Bayar sebelum {fmt12(_hm(config.PAY_DEADLINE_TIME))} {fmt_date(d + timedelta(days=1))}.")
            _notify(db, uid, "finalised", f"Senarai disahkan: {fmt_date(d)}", body, d)
        elif uid in flagged:
            _notify(db, uid, "finalised", f"Senarai disahkan: {fmt_date(d)}",
                    "Belum ada prebet untuk anda. BKK sedang menentukan pengangkutan dan akan maklumkan.", d)
        # selainnya: auto_ehailing() di bawah memaklumkan ahli
    auto_ehailing(db, ev)
    notify_prebets_after_finalise(db, ev)
    db.commit()
    return len(seen)


def pickup_point_name(db, b: models.Booking) -> str:
    if b.pickup_place:
        return b.pickup_place
    p = db.get(models.PickupPoint, b.pickup_point_id) if b.pickup_point_id else None
    return p.name if p else "-"


def wa_group_text(db: Session) -> str:
    link = get_setting(db, "wa_group_link")
    return "Sila pantau group WhatsApp BKK untuk butiran e-hailing" + (f": {link}" if link else ".")


def auto_ehailing(db: Session, ev: models.TrainingEvent) -> int:
    """Selepas senarai disahkan: penumpang tanpa kenderaan (kereta & motosikal dah penuh) terus ditandakan e-hailing.
    Kes perempuan tunggal ditinggalkan untuk keputusan admin. Ahli dimaklumkan; admin dapat senarai untuk diuruskan."""
    flagged = flagged_lone_ids(db, ev)
    q = db.query(models.Booking).filter(
        models.Booking.training_date == ev.training_date, models.Booking.session_id == ev.session_id,
        models.Booking.status == BookingStatus.confirmed, models.Booking.vehicle_id.is_(None),
        models.Booking.ehailing.is_(False))
    per_user: dict[int, list] = defaultdict(list)
    for b in q.all():
        if b.user_id not in flagged:
            per_user[b.user_id].append(b)
    if not per_user:
        return 0
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(list(per_user)))}
    names = {"going": "pergi", "returning": "balik"}
    lines = []
    for uid, bs in per_user.items():
        for b in bs:
            b.ehailing = True
        dirs = " & ".join(names[b.direction.value] for b in sorted(bs, key=lambda x: x.direction.value))
        _sync_payment(db, users[uid], ev.training_date)
        extra = " Tiada yuran persatuan untuk trip e-hailing; sila tempah & bayar e-hailing sendiri."
        adab = (" (Adab: perempuan tidak boleh seorang diri dalam kereta prebet lelaki.)"
                if users[uid].gender == Gender.female else "")
        _notify(db, uid, "car", f"E-hailing: {fmt_date(ev.training_date)}",
                f"Tiada prebet untuk trip {dirs}; BKK uruskan e-hailing.{adab} {wa_group_text(db)}{extra}",
                ev.training_date, severity="task", link="/")
        lines.append(f"{users[uid].name} ({_college_label(db, users[uid])}, {dirs})")
    for a in db.query(models.User).filter_by(role=models.Role.admin, active=True):
        _notify(db, a.id, "admin_alert", f"E-hailing diperlukan: {fmt_date(ev.training_date)} ({len(lines)} orang)",
                "; ".join(lines)[:480], ev.training_date, severity="task", link="/admin?tab=summary",
                ref=f"ehail:{ev.id}")
    db.flush()
    return len(per_user)


def prebet_users(db: Session):
    """Pemandu/prebet aktif yang ada sekurang-kurangnya satu kenderaan diluluskan."""
    ids = {r[0] for r in db.query(models.Vehicle.driver_id).filter(
        models.Vehicle.driver_id.isnot(None), models.Vehicle.active.is_(True),
        models.Vehicle.approval == models.ApprovalStatus.approved)}
    return db.query(models.User).filter(models.User.id.in_(list(ids) or [0]), models.User.active.is_(True)).all()


def notify_prebets_after_finalise(db: Session, ev: models.TrainingEvent):
    """Prebet terlibat: butiran tugasan. Prebet yang sah boleh tapi tak diperlukan: dimaklumkan."""
    d = ev.training_date
    s = db.get(models.TrainingSession, ev.session_id)
    venue = db.get(models.Venue, ev.venue_id) if ev.venue_id else None
    confirmed = prebet_confirmed_ids(db, d)
    m = manifest(db, d)
    cars_by_driver: dict[int, list] = defaultdict(list)
    for c in m["cars"]:
        v = db.get(models.Vehicle, c["vehicle_id"])
        if v and v.driver_id:
            cars_by_driver[v.driver_id].append(c)
    for u in prebet_users(db):
        if u.id in cars_by_driver:
            parts = []
            for c in cars_by_driver[u.id]:
                parts.append(", ".join(f"{st['college']} @ {st['checkpoint']} ({st['count']})" for st in c["stops"]))
            _notify(db, u.id, "driver", f"Tugasan {fmt_date(d)}: anda diperlukan",
                    f"Pickup {pickup_window(s)}. Ambil: {'; '.join(parts)}."
                    + (f" Latihan di {venue.name}." if venue else ""), d, severity="task", link="/prebet",
                    ref=f"duty:{u.id}:{d.isoformat()}")
        elif u.id in confirmed or not config.REQUIRE_PREBET_CONFIRM:
            _notify(db, u.id, "driver", f"{fmt_date(d)}: tak diperlukan kali ini",
                    "Terima kasih kerana sedia membantu. Anda tak perlu bawa penumpang pada tarikh ini.", d,
                    severity="info", link="/prebet", ref=f"duty:{u.id}:{d.isoformat()}")


def cancel_event(db: Session, ev: models.TrainingEvent) -> int:
    """Batal latihan: semua trip dibatalkan; bayaran yang dah dibuat dibawa sebagai kredit."""
    if ev.status == EventStatus.cancelled:
        raise ValueError("Latihan ini sudah dibatalkan")
    d = ev.training_date
    rows = db.query(models.Booking).filter_by(training_date=d, session_id=ev.session_id).all()
    user_ids = {b.user_id for b in rows}
    for b in rows:
        # tanda hanya tempahan yang masih aktif: ahli yang sudah batal sendiri tidak dipulihkan kemudian
        b.cancelled_by_event = b.status in (BookingStatus.confirmed, BookingStatus.ineligible)
        b.status, b.vehicle_id = BookingStatus.cancelled, None
    ev.status = EventStatus.cancelled
    _clear_unfinalised(db, ev)
    db.flush()
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(list(user_ids) or [0]))}
    for uid in user_ids:
        _sync_payment(db, users[uid], d)
        _notify(db, uid, "cancelled", f"Latihan {fmt_date(d)} dibatalkan",
                "Bayaran yang telah dibuat (jika ada) dibawa ke latihan seterusnya.", d)
    db.commit()
    return len(user_ids)


def reactivate_event(db: Session, ev: models.TrainingEvent, today: date | None = None) -> dict:
    """Aktifkan semula latihan yang dibatalkan (cth pengerusi putuskan latihan diteruskan).
    Tempahan yang dibatalkan KERANA latihan dibatalkan dipulihkan; yang dibatalkan sendiri oleh ahli kekal batal.
    Cuti pada tarikh itu dibuang. Bayaran yang jadi kredit digunakan semula pada latihan ini mengikut kategori
    kenderaan ahli semasa senarai disahkan."""
    today = today or today_my()
    if ev.status != EventStatus.cancelled:
        raise ValueError("Latihan ini tidak dibatalkan")
    d = ev.training_date
    if d < today:
        raise ValueError("Tarikh latihan sudah lepas")
    ev.status = EventStatus.open
    ev.finalised_at = None
    hol = db.query(models.Holiday).filter_by(training_date=d).first()
    if hol is not None:
        db.delete(hol)
    rows = db.query(models.Booking).filter_by(training_date=d, session_id=ev.session_id,
                                              cancelled_by_event=True).all()
    user_ids = {b.user_id for b in rows}
    for b in rows:
        b.status, b.cancelled_by_event = BookingStatus.confirmed, False
    db.flush()
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(list(user_ids) or [0]))}
    for uid in user_ids:
        _sync_payment(db, users[uid], d)
    db.flush()
    assign_vehicles(db, ev)
    for uid in user_ids:
        _notify(db, uid, "reactivated", f"Latihan {fmt_date(d)} diteruskan semula",
                "Tempahan anda dipulihkan. Kredit bayaran (jika ada) akan digunakan semasa senarai disahkan. "
                "Tekan 'Tak naik' jika anda tidak dapat hadir.", d)
    _notify(db, None, "announcement", f"Latihan {fmt_date(d)} diteruskan semula",
            "BKK mengaktifkan semula latihan ini.", d, severity="info", link="")
    db.commit()
    return {"restored": len(user_ids)}


def unfinalise_event(db: Session, ev: models.TrainingEvent) -> dict:
    """Admin batalkan pengesahan senarai (cth tersilap / perlu ubah). Bayaran belum dibayar dibuka semula selepas disahkan lagi;
    kredit yang sempat digunakan dipulangkan. Tidak dibenarkan jika bayaran prebet sudah dibuat untuk tarikh ini.
    Auto-sah dimatikan untuk latihan ini: admin sahkan sendiri bila siap."""
    if ev.status != EventStatus.finalised:
        raise ValueError("Senarai belum disahkan")
    d = ev.training_date
    paid = db.query(models.DriverPayout).filter_by(training_date=d).count()
    if paid:
        raise ValueError("Bayaran prebet sudah dibuat untuk tarikh ini; pengesahan tak boleh dibatalkan")
    kept = 0
    for p in db.query(models.Payment).filter_by(training_date=d):
        if p.status in (PaymentStatus.unpaid, PaymentStatus.rejected):
            if p.credit_applied:
                u = db.get(models.User, p.user_id)
                u.credit_balance += p.credit_applied
                p.credit_applied = 0.0
        elif p.status in (PaymentStatus.pending, PaymentStatus.paid):
            kept += 1
    ev.status = EventStatus.open
    ev.finalised_at = None
    ev.auto_off = True
    db.flush()
    uids = {b.user_id for b in db.query(models.Booking).filter_by(
        training_date=d, session_id=ev.session_id, status=BookingStatus.confirmed)}
    for uid in uids:
        _notify(db, uid, "unfinalised", f"Senarai {fmt_date(d)} ditarik balik BKK",
                "BKK sedang membuat pindaan. Jangan bayar dahulu; anda dimaklumkan semula bila senarai disahkan.",
                d, severity="warning", link="/", ref=f"unfin:{ev.id}:{uid}")
    db.commit()
    return {"notified": len(uids), "payments_kept": kept}


def cancel_user_trips(db: Session, user: models.User, d: date):
    """Admin batalkan semua trip seorang ahli pada satu tarikh."""
    rows = db.query(models.Booking).filter_by(user_id=user.id, training_date=d).all()
    for b in rows:
        if b.status in (BookingStatus.confirmed, BookingStatus.ineligible):
            b.status, b.vehicle_id = BookingStatus.cancelled, None
    db.flush()
    _sync_payment(db, user, d)
    _notify(db, user.id, "cancelled", f"Booking {fmt_date(d)} dibatalkan oleh BKK",
            "Hubungi BKK kalau ada pertanyaan.", d)
    ev = event_on(db, d)
    if ev:
        assign_vehicles(db, ev)
    db.commit()


# ---------------------------------------------------------------- jobs

def send_reminders(db: Session, today: date | None = None) -> int:
    today = today or today_my()
    target = today + timedelta(days=config.REMINDER_DAYS_BEFORE)
    ev = event_on(db, target)
    if ev is None or ev.status == EventStatus.cancelled:
        return 0
    s = db.get(models.TrainingSession, ev.session_id)
    sent = 0
    for uid in {b.user_id for b in db.query(models.Booking).filter_by(
            training_date=target, status=BookingStatus.confirmed)}:
        if db.query(models.Notification).filter_by(user_id=uid, kind="reminder", training_date=target).first():
            continue
        _notify(db, uid, "reminder", f"Peringatan: latihan {fmt_date(target)}",
                f"Latihan {fmt12(s.start_time)}. Pilih / batal Pergi & Balik sebelum {fmt12(_hm(config.CUTOFF_TIME))} hari latihan; selepas itu ditutup.", target)
        sent += 1
    db.commit()
    return sent


def send_payout_reminders(db: Session, today: date | None = None) -> int:
    """Ingatkan bendahari tentang baki bayaran prebet yang tempohnya sudah tamat (mengikut mod: per latihan / mingguan /
    bulanan). Satu notifikasi seorang prebet (digabung); jadi amaran bila lewat tarikh akhir. Sekali sehari."""
    today = today or today_my()
    treasurers = db.query(models.User).filter_by(is_treasurer=True, active=True).all()
    if not treasurers:
        return 0
    sent = 0
    recent = datetime.utcnow() - timedelta(hours=20)
    by: dict[int, list] = defaultdict(list)
    for it in payout_items(db, today):
        if it["complete"]:
            by[it["driver"]["id"]].append(it)
    for did, its in by.items():
        drv = db.get(models.User, did)
        total = round(sum(i["outstanding"] for i in its), 2)
        overdue = any(i["overdue"] for i in its)
        ref = f"payoutdue:{did}:{drv.id}"
        for t in treasurers:
            if db.query(models.Notification).filter(
                    models.Notification.user_id == t.id, models.Notification.kind == "payout_due",
                    models.Notification.ref == ref, models.Notification.created_at >= recent).first():
                continue
            _notify(db, t.id, "payout_due", f"Bayar prebet {drv.short_name or drv.name}: RM{total:.2f}",
                    _carry_note([{"training_date": i["date"].isoformat(), "amount": i["outstanding"]} for i in its])
                    + (". Sudah lewat tarikh akhir." if overdue else "."),
                    its[-1]["date"], severity="warning" if overdue else "task", link="/bendahari", ref=ref)
            sent += 1
    db.commit()
    return sent


def auto_finalise(db: Session, now: datetime | None = None) -> int:
    """Admin lupa sahkan: senarai disahkan automatik pada jam AUTO_FINALISE_TIME (lalai 7:00 malam) hari latihan (perlu tempat latihan)."""
    now = now or now_my()
    done = 0
    for ev in db.query(models.TrainingEvent).filter(
            models.TrainingEvent.status == EventStatus.open,
            models.TrainingEvent.training_date >= now.date()).all():
        if ev.auto_off:
            continue   # admin batalkan pengesahan: tunggu admin sahkan sendiri
        s = db.get(models.TrainingSession, ev.session_id)
        start = datetime.combine(ev.training_date, s.start_time)
        if not (auto_finalise_dt(ev.training_date) <= now < start):
            continue
        if ev.venue_id is None and s.one_off_date is None:
            for a in db.query(models.User).filter_by(role=models.Role.admin, active=True):
                if not db.query(models.Notification).filter_by(
                        user_id=a.id, kind="admin_alert", training_date=ev.training_date).first():
                    _notify(db, a.id, "admin_alert", f"Tetapkan tempat latihan {fmt_date(ev.training_date)}",
                            "Senarai tak boleh disahkan automatik selagi tempat latihan belum ditetapkan.",
                            ev.training_date)
            continue
        finalise_event(db, ev)
        done += 1
    db.commit()
    return done


# ---------------------------------------------------------------- reporting

def _points_by_id(db):
    return {p.id: p for p in db.query(models.PickupPoint)}


# ---------------------------------------------------------------- e-hailing (diuruskan BKK)

def event_needs_transport(db: Session, ev: models.TrainingEvent) -> list[dict]:
    """Penumpang disahkan yang belum ada kenderaan (calon e-hailing) atau sudah ditandakan e-hailing."""
    rows = (db.query(models.Booking, models.User)
            .join(models.User, models.User.id == models.Booking.user_id)
            .filter(models.Booking.training_date == ev.training_date, models.Booking.session_id == ev.session_id,
                    models.Booking.status == BookingStatus.confirmed, models.Booking.vehicle_id.is_(None))
            .order_by(models.Booking.direction, models.User.name).all())
    return [{"booking_id": b.id, "user_id": u.id, "name": u.name, "phone": u.phone,
             "college": _college_label(db, u),
             "direction": b.direction.value, "ehailing": b.ehailing, "note": b.ehailing_note} for b, u in rows]


def set_ehailing(db: Session, ev: models.TrainingEvent, on: bool, direction: str | None,
                 note: str, user_ids: list[int] | None) -> int:
    """Tandakan (atau batal) e-hailing untuk penumpang tanpa kenderaan. Ahli dimaklumkan dalam app."""
    if ev.status == EventStatus.cancelled:
        raise ValueError("Latihan ini dibatalkan")
    q = db.query(models.Booking).filter(
        models.Booking.training_date == ev.training_date, models.Booking.session_id == ev.session_id,
        models.Booking.status == BookingStatus.confirmed, models.Booking.vehicle_id.is_(None))
    if direction:
        q = q.filter(models.Booking.direction == Direction(direction))
    if user_ids:
        q = q.filter(models.Booking.user_id.in_(user_ids))
    per_user: dict[int, list[models.Booking]] = defaultdict(list)
    for b in q.all():
        if b.ehailing != on or (on and b.ehailing_note != note):
            per_user[b.user_id].append(b)
    names = {"going": "pergi", "returning": "balik"}
    for uid, bs in per_user.items():
        for b in bs:
            b.ehailing, b.ehailing_note = on, (note if on else "")
        dirs = " & ".join(names[b.direction.value] for b in sorted(bs, key=lambda x: x.direction.value))
        if on:
            _notify(db, uid, "car", f"E-hailing diuruskan BKK: {fmt_date(ev.training_date)}",
                    f"Tiada prebet untuk trip {dirs}. Sila tempah & bayar e-hailing sendiri (tiada yuran persatuan untuk trip ini)."
                    + (f" {note}" if note else ""), ev.training_date)
        else:
            _notify(db, uid, "car", f"Pengangkutan dikemas kini: {fmt_date(ev.training_date)}",
                    f"E-hailing untuk trip {dirs} dibatalkan. BKK akan maklumkan jika ada kemas kini.",
                    ev.training_date)
    db.flush()
    for uid in per_user:
        _sync_payment(db, db.get(models.User, uid), ev.training_date)
    db.flush()
    return len(per_user)


def event_overview(db: Session, ev: models.TrainingEvent) -> dict:
    d = ev.training_date
    s = db.get(models.TrainingSession, ev.session_id)
    venue = db.get(models.Venue, ev.venue_id) if ev.venue_id else None
    rows = db.query(models.Booking).filter_by(training_date=d, session_id=ev.session_id).all()
    out = {"event_id": ev.id, "training_date": d.isoformat(), "session_name": s.name,
           "start_time": s.start_time.strftime("%H:%M"), "status": ev.status.value,
           "venue": {"id": venue.id, "name": venue.name, "excluded": venue.excluded_codes} if venue else None,
           "warnings": []}
    out["is_activity"] = s.one_off_date is not None
    out["trip_only"] = s.trip_only
    if venue is None and s.one_off_date is None and ev.status == EventStatus.open:
        out["warnings"].append("Tempat latihan belum ditetapkan")
    for direction in Direction:
        conf = [b for b in rows if b.direction == direction and b.status == BookingStatus.confirmed]
        assigned = [b for b in conf if b.vehicle_id]
        eh = [b for b in conf if not b.vehicle_id and b.ehailing]
        out[direction.value] = {"passengers": len(conf), "assigned": len(assigned), "ehailing": len(eh),
                                "unassigned": len(conf) - len(assigned) - len(eh)}
    worst = max(out["going"]["unassigned"], out["returning"]["unassigned"])
    out["extra_cars_needed"] = math.ceil(worst / config.CAR_SEATS_DEFAULT) if worst else 0
    out["vehicles_used"] = len({b.vehicle_id for b in rows if b.vehicle_id and b.status == BookingStatus.confirmed})
    out["vehicles_available"] = len(_vehicles_for(db, d))
    if worst:
        out["warnings"].append(f"{worst} ahli belum ada kenderaan (tambah prebet atau tandakan e-hailing)")
    skipped = db.query(models.User.name).join(models.Booking, models.Booking.user_id == models.User.id).filter(
        models.Booking.training_date == d, models.Booking.session_id == ev.session_id,
        models.Booking.status == BookingStatus.skipped).distinct().all()
    out["skipped"] = sorted(r[0] for r in skipped)
    out["ineligible_members"] = len({b.user_id for b in rows if b.status == BookingStatus.ineligible})
    conf_users = {b.user_id for b in rows if b.status == BookingStatus.confirmed}
    ucol = {u.id: u.college_id for u in db.query(models.User).filter(models.User.id.in_(list(conf_users) or [0]))}
    codes = {c.id: c.code for c in db.query(models.College)}
    by_college: dict[str, int] = {}
    for uid in conf_users:
        code = codes.get(ucol.get(uid), "Lain-lain")
        by_college[code] = by_college.get(code, 0) + 1
    out["by_college"] = dict(sorted(by_college.items()))
    pays = [p for p in db.query(models.Payment).filter_by(training_date=d) if p.status != PaymentStatus.void]
    out["payments"] = {
        "expected": sum(p.amount for p in pays),
        "collected": sum(p.amount for p in pays if p.status == PaymentStatus.paid),
        "pending_verify": sum(1 for p in pays if p.status == PaymentStatus.pending),
        "unpaid": sum(1 for p in pays if p.status in (PaymentStatus.unpaid, PaymentStatus.rejected)),
    }
    out["auto_off"] = bool(ev.auto_off)
    out["payments"]["to_collect"] = round(sum(max(0.0, p.amount - p.credit_applied) for p in pays
                                              if p.status in (PaymentStatus.unpaid, PaymentStatus.rejected, PaymentStatus.pending)), 2)
    out["payments"]["members"] = len(pays)
    out["payout_due"] = round(sum(r["owed"] for r in payout_rows(db, d)), 2) if ev.status == EventStatus.finalised else 0.0
    out["flow"] = event_flow(db, ev, out)
    out["ehailing_people"] = [{"name": r["name"], "direction": r["direction"]}
                              for r in event_needs_transport(db, ev) if r["ehailing"]]
    out["needs_decision"] = sorted(flagged_lone_ids(db, ev))
    if out["needs_decision"]:
        out["warnings"].append(f"{len(out['needs_decision'])} ahli perempuan perlu keputusan anda (e-hailing atau tukar manual)")
    return out


def prebet_status_list(db: Session, d: date) -> list[dict]:
    """Semua prebet beserta telefon dan status sahkan pada tarikh itu (untuk admin)."""
    rows = {r.user_id: r for r in db.query(models.PrebetAvailability).filter_by(training_date=d)}
    colleges = {c.id: c for c in db.query(models.College)}
    out = []
    for u in prebet_users(db):
        r = rows.get(u.id)
        col = colleges.get(u.college_id)
        vs = db.query(models.Vehicle).filter_by(driver_id=u.id, active=True, approval=models.ApprovalStatus.approved).all()
        out.append({"user_id": u.id, "name": u.name, "phone": u.phone, "college": col.code if col else None,
                    "gender": u.gender.value if u.gender else None,
                    "available": None if r is None else r.available, "by_admin": bool(r and r.by_admin),
                    "short_name": short(u),
                    "vehicles": [{"id": v.id, "name": v.name, "desc": vehicle_desc(v), "type": v.vehicle_type.value,
                                  "capacity": v.capacity} for v in vs],
                    "ticks": ticks_for(db, u.id, d)})
    return sorted(out, key=lambda x: (x["available"] is not None, x["name"]))


def event_flow(db: Session, ev: models.TrainingEvent, ov: dict) -> dict:
    """Pemantauan hujung ke hujung bagi satu tarikh: prebet sahkan -> senarai disahkan -> resit ahli -> bayar prebet -> resit prebet."""
    d = ev.training_date
    pl = prebet_status_list(db, d)
    confirmed = [p for p in pl if p["available"] is True]
    declined = [p for p in pl if p["available"] is False]
    missing = [p for p in pl if p["available"] is None]
    s = db.get(models.TrainingSession, ev.session_id)
    steps = []
    steps.append({"key": "prebet", "label": "Prebet sahkan",
                  "done": not missing and bool(pl),
                  "detail": f"{len(confirmed)} boleh, {len(declined)} tak boleh, {len(missing)} belum sahkan"})
    steps.append({"key": "list", "label": "Senarai disahkan", "done": ev.status == EventStatus.finalised,
                  "detail": {"open": "Belum disahkan", "finalised": "Sudah disahkan", "cancelled": "Dibatalkan"}[ev.status.value]})
    duty = _duty_driver_ids(db, d) if ev.status == EventStatus.finalised else {}
    if duty:
        tk = {(t.user_id, t.kind) for t in db.query(models.DutyTick).filter_by(training_date=d)}
        for kind, label in (("arrived", "Prebet sampai latihan"), ("delivered", "Prebet dah hantar")):
            n = sum(1 for uid in duty if (uid, kind) in tk)
            steps.append({"key": kind, "label": label, "done": n == len(duty), "detail": f"{n} / {len(duty)} prebet tanda"})
    pay = ov["payments"]
    n_pay = pay["pending_verify"] + pay["unpaid"]
    paid_n = sum(1 for p in db.query(models.Payment).filter_by(training_date=d, status=PaymentStatus.paid))
    steps.append({"key": "receipts", "label": "Resit ahli", "done": ev.status == EventStatus.finalised and n_pay == 0 and paid_n > 0,
                  "detail": f"{paid_n} disahkan, {pay['pending_verify']} tunggu semak, {pay['unpaid']} belum bayar"})
    rows = payout_rows(db, d)
    owed = sum(r["owed"] for r in rows)
    outstanding = sum(r["outstanding"] for r in rows)
    with_receipt = sum(1 for r in rows for x in r["payouts"] if x["has_receipt"])
    steps.append({"key": "payout", "label": "Bayar prebet", "done": bool(rows) and outstanding <= 0 and owed > 0,
                  "detail": f"RM{owed - outstanding:.2f} / RM{owed:.2f} dibayar"})
    steps.append({"key": "payout_receipt", "label": "Resit prebet", "done": bool(rows) and with_receipt >= sum(len(r["payouts"]) for r in rows) and with_receipt > 0,
                  "detail": f"{with_receipt} resit dimuat naik"})
    warns = []
    deadline = _deadline(d, s)
    if missing and now_my() >= deadline and ev.status == EventStatus.open:
        warns.append(f"{len(missing)} prebet belum sahkan dan tarikh akhir telah lepas")
    if ev.status == EventStatus.finalised and pay["unpaid"]:
        warns.append(f"{pay['unpaid']} ahli belum bayar")
    if outstanding > 0 and ev.status == EventStatus.finalised:
        warns.append(f"Baki bayar prebet RM{outstanding:.2f}")
    return {"steps": steps, "prebet": pl, "warnings": warns}


def manifest(db: Session, d: date, vehicle_ids: set[int] | None = None, for_driver: bool = False) -> dict:
    """Senarai penumpang ikut kereta (untuk admin & driver). for_driver: nama pendek sahaja (tanpa no. ahli)."""
    ev = event_on(db, d)
    rows = db.query(models.Booking).filter_by(training_date=d, status=BookingStatus.confirmed).all()
    by_user = defaultdict(list)
    for b in rows:
        by_user[b.user_id].append(b)
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(list(by_user) or [0]))}
    colleges = {c.id: c for c in db.query(models.College)}
    pts = _points_by_id(db)
    vehicles = {v.id: v for v in db.query(models.Vehicle)}
    cars = defaultdict(list)
    unassigned = []
    for uid, bs in by_user.items():
        u, first = users[uid], bs[0]
        col = colleges.get(u.college_id)
        item = {"user_id": uid, "name": short(u) if for_driver else u.name, "short_name": short(u),
                "full_name": u.name, "block": u.block or "", "phone": u.phone,
                "member_no": "" if for_driver else u.member_no,
                "gender": u.gender.value if u.gender else None,
                "college": "Tempat lain" if first.pickup_place else (college_group(col.code) if col else None),
                "category": None if first.pickup_place else (col.category if col else None),
                "checkpoint": pickup_label(first, pts),
                "places": {b.direction.value: pickup_label(b, pts) for b in bs},
                "directions": sorted(b.direction.value for b in bs)}
        if first.vehicle_id:
            cars[first.vehicle_id].append(item)
        else:
            unassigned.append(item)
    out_cars = []
    for vid, pax in cars.items():
        if vehicle_ids is not None and vid not in vehicle_ids:
            continue
        v = vehicles[vid]
        drv = db.get(models.User, v.driver_id) if v.driver_id else None
        stops: dict[tuple, dict] = {}
        for x in pax:
            key = (x["college"] or "-", x["checkpoint"] or "-")
            st = stops.setdefault(key, {"college": key[0], "checkpoint": key[1], "category": x["category"], "count": 0, "names": []})
            st["count"] += 1
            st["names"].append(x["name"])
        cats = {x["category"] for x in pax if x["category"]}
        out_cars.append({
            "category": vehicle_category(db, v, colleges), "mixed": len(cats) > 1,
            "stops": sorted(stops.values(), key=lambda t: (0 if t["category"] == "jauh" else 1, t["college"], t["checkpoint"])),
            "vehicle_id": vid, "name": v.name, "plate_no": v.plate_no, "capacity": v.capacity,
            "desc": vehicle_desc(v), "brand": v.brand, "colour": v.colour,
            "driver_college": (college_group(vehicle_zone(db, v, colleges)[1]) if vehicle_zone(db, v, colleges)[1] else None),
            "vehicle_type": v.vehicle_type.value, "seat_rows": v.seat_rows,
            "male": sum(1 for x in pax if x["gender"] == "male"),
            "female": sum(1 for x in pax if x["gender"] == "female"),
            "driver": {"name": short(drv) if for_driver else drv.name, "short_name": short(drv), "phone": drv.phone, "gender": drv.gender.value if drv.gender else None} if drv else None,
            "passengers": sorted(pax, key=lambda x: (x["checkpoint"] or "", x["name"]))})
    return {"training_date": d.isoformat(), "event_status": ev.status.value if ev else None,
            "cars": out_cars, "unassigned": [] if vehicle_ids is not None else unassigned}


def send_safety_reminders(db: Session, now: datetime | None = None) -> int:
    """Ingatkan driver/rider yang belum buat akuan keselamatan (lesen sah, insurans, helmet). Pilihan tapi diingatkan."""
    now = now or now_my()
    sent = 0
    for v in db.query(models.Vehicle).filter_by(approval=models.ApprovalStatus.approved, active=True,
                                                safety_confirmed=False):
        if not v.driver_id:
            continue
        if v.safety_reminded_at and now - v.safety_reminded_at < timedelta(days=config.SAFETY_REMINDER_DAYS):
            continue
        what = "lesen memandu/menunggang sah, insurans dan helmet penumpang" \
            if v.vehicle_type == VehicleType.motorcycle else "lesen memandu sah dan insurans"
        _notify(db, v.driver_id, "driver", f"Lengkapkan akuan keselamatan: {v.name}",
                f"Sila sahkan {what} di tab Driver.")
        v.safety_reminded_at = now
        sent += 1
    db.commit()
    return sent


def payout_rows(db: Session, d: date) -> list[dict]:
    """Ringkasan bayaran kepada prebet untuk satu tarikh: persatuan ialah orang tengah.
    Jumlah patut dibayar = bayaran TETAP satu hari latihan (ikut jenis kenderaan & kategori kolej prebet; hanya admin ubah)
    bagi kenderaan yang beroperasi (ada penumpang) pada senarai yang telah disahkan; tak beroperasi = tiada bayaran.
    Aktiviti luar bersistem harga sekenderaan: prebet dibayar harga penuh kenderaan (persatuan tanggung kekurangan)."""
    if free_activity_on(db, d):
        return []  # aktiviti percuma: persatuan tak kutip, tak bayar driver
    bookings = db.query(models.Booking).filter_by(training_date=d, status=BookingStatus.confirmed).all()
    per_vehicle = defaultdict(set)
    sess_of = {}
    for b in bookings:
        if b.vehicle_id:
            per_vehicle[b.vehicle_id].add(b.user_id)
            sess_of[b.vehicle_id] = b.session_id
    pays = {p.user_id: p for p in db.query(models.Payment).filter_by(training_date=d)}
    vehicles = {v.id: v for v in db.query(models.Vehicle).filter(models.Vehicle.id.in_(list(per_vehicle) or [0]))}
    users = {u.id: u for u in db.query(models.User).filter(
        models.User.id.in_(list({u for us in per_vehicle.values() for u in us}) or [0]))}
    colleges_all = {c.id: c for c in db.query(models.College)}
    ticks = {(t.user_id, t.kind) for t in db.query(models.DutyTick).filter_by(training_date=d)}
    out = []
    for vid, uids in per_vehicle.items():
        v = vehicles[vid]
        drv = db.get(models.User, v.driver_id) if v.driver_id else None
        sess = db.get(models.TrainingSession, sess_of[vid])
        collected = sum(pays[u].amount for u in uids if u in pays and pays[u].status == PaymentStatus.paid)
        expected = sum(pays[u].amount for u in uids if u in pays and pays[u].status != PaymentStatus.void)
        owed = 0.0
        ev = db.query(models.TrainingEvent).filter_by(session_id=sess_of[vid], training_date=d).first() if sess else None
        if ev is None or ev.status != EventStatus.finalised:
            owed = 0.0   # senarai belum disahkan: belum pasti prebet beroperasi
        elif sess is not None and sess.one_off_date is not None and (sess.car_price is not None or sess.motor_price is not None):
            full = (sess.motor_price if sess.motor_price is not None else config.MOTOR_ACTIVITY_PRICE_DEFAULT) \
                if v.vehicle_type == VehicleType.motorcycle else (sess.car_price or 0.0)
            owed = float(full)
        else:
            # Bayaran TETAP satu hari latihan bagi kenderaan yang beroperasi (ada penumpang); tak beroperasi = tiada bayaran
            cat = payout_category(uids, users, colleges_all)
            owed = payout_rate(db, v.vehicle_type.value, cat)
        paid_rows = db.query(models.DriverPayout).filter_by(vehicle_id=vid, training_date=d).all()
        paid_out = sum(x.amount for x in paid_rows)
        out.append({
            "vehicle_id": vid, "vehicle": v.name, "plate_no": v.plate_no,
            "vehicle_type": v.vehicle_type.value, "passengers": len(uids),
            "category": payout_category(uids, users, colleges_all), "training_date": d.isoformat(),
            "arrived": bool(drv and (drv.id, "arrived") in ticks), "delivered": bool(drv and (drv.id, "delivered") in ticks),
            "driver": None if drv is None else {
                "id": drv.id, "name": drv.name, "phone": drv.phone,
                "bank": drv.payout_bank, "account_no": drv.payout_account_no,
                "account_name": drv.payout_account_name, "has_qr": bool(drv.payout_qr_file),
                "has_qr2": bool(drv.payout_qr2_file)},
            "expected": round(expected, 2), "collected": round(collected, 2), "owed": round(owed, 2),
            "paid_out": round(paid_out, 2), "outstanding": round(max(0.0, owed - paid_out), 2),
            "payouts": [{"id": x.id, "amount": x.amount, "has_receipt": bool(x.receipt_file),
                         "received": x.received} for x in paid_rows],
        })
    return sorted(out, key=lambda r: r["vehicle"])


# ---------------------------------------------------------------- tempoh bayaran prebet (per latihan / mingguan / bulanan)

PAYOUT_MODES = {"latihan": "Per latihan", "mingguan": "Mingguan", "bulanan": "Bulanan"}


def payout_mode(db: Session) -> str:
    m = get_setting(db, "payout_mode", "latihan")
    return m if m in PAYOUT_MODES else "latihan"


def payout_period(d: date, mode: str) -> dict:
    """Tempoh bayaran bagi latihan pada tarikh d. period_end = hari terakhir tempoh; deadline = sebelum tengah malam."""
    if mode == "mingguan":
        start = d - timedelta(days=d.weekday())
        end = start + timedelta(days=6)           # Ahad
        label = f"Minggu {start.strftime('%d/%m')}–{end.strftime('%d/%m')}"
        dl_day = end
    elif mode == "bulanan":
        nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        end = nxt - timedelta(days=1)
        label = f"{d.strftime('%m/%Y')}"
        dl_day = end
    else:
        end = d
        label = fmt_date(d)
        dl_day = d + timedelta(days=1)            # sebelum tengah malam hari selepas latihan
    return {"key": f"{mode}:{end.isoformat()}", "label": label, "end": end,
            "deadline": datetime.combine(dl_day, time(23, 59))}


def _driver_card(drv: models.User) -> dict:
    return {"id": drv.id, "name": drv.name, "short_name": drv.short_name or drv.name, "phone": drv.phone,
            "bank": drv.payout_bank, "account_no": drv.payout_account_no, "account_name": drv.payout_account_name,
            "has_qr": bool(drv.payout_qr_file), "has_qr2": bool(drv.payout_qr2_file)}


def payout_items(db: Session, today: date | None = None, driver_id: int | None = None, days_back: int = 120) -> list[dict]:
    """Semua latihan (kenderaan, tarikh) yang prebet patut dibayar tetapi belum dilunaskan, dari yang terlama.
    Baki tertunggak daripada latihan terdahulu sentiasa ikut sekali (digabung) dengan yang seterusnya."""
    today = today or today_my()
    mode, now = payout_mode(db), now_my()
    dates = sorted({e.training_date for e in db.query(models.TrainingEvent).filter(
        models.TrainingEvent.status == EventStatus.finalised,
        models.TrainingEvent.training_date <= today,
        models.TrainingEvent.training_date >= today - timedelta(days=days_back))})
    out = []
    for d in dates:
        per = payout_period(d, mode)
        for r in payout_rows(db, d):
            if r["outstanding"] <= 0 or r["driver"] is None:
                continue
            if driver_id is not None and r["driver"]["id"] != driver_id:
                continue
            out.append({**r, "date": d, "period": per["label"], "period_key": per["key"], "period_end": per["end"],
                        "deadline": per["deadline"], "overdue": now > per["deadline"],
                        "complete": today >= per["end"]})
    return out


def payout_overview(db: Session, today: date | None = None) -> dict:
    """Untuk bendahari: baki bayaran ikut prebet (satu kad seorang prebet, ada butiran tiap tarikh)."""
    today = today or today_my()
    mode = payout_mode(db)
    items = payout_items(db, today)
    by: dict[int, dict] = {}
    for it in items:
        drv = db.get(models.User, it["driver"]["id"])
        g = by.setdefault(drv.id, {"driver": _driver_card(drv), "items": [], "total": 0.0, "due_total": 0.0,
                                  "overdue": False, "missing_ticks": 0})
        g["items"].append({"training_date": it["date"].isoformat(), "vehicle": it["vehicle"], "plate_no": it["plate_no"],
                           "vehicle_id": it["vehicle_id"], "amount": it["outstanding"], "period": it["period"],
                           "overdue": it["overdue"], "complete": it["complete"],
                           "arrived": it["arrived"], "delivered": it["delivered"]})
        g["total"] = round(g["total"] + it["outstanding"], 2)
        if it["complete"]:
            g["due_total"] = round(g["due_total"] + it["outstanding"], 2)
        g["overdue"] = g["overdue"] or it["overdue"]
        g["missing_ticks"] += (0 if it["arrived"] else 1) + (0 if it["delivered"] else 1)
    for g in by.values():
        g["note"] = _carry_note(g["items"])
    cards = sorted(by.values(), key=lambda g: (not g["overdue"], g["driver"]["name"]))
    return {"mode": mode, "mode_label": PAYOUT_MODES[mode], "drivers": cards,
            "total": round(sum(g["total"] for g in cards), 2)}


def _carry_note(items: list[dict]) -> str:
    """cth: 'RM20.00 = RM10.00 (Rab 21/10) + RM10.00 (Sab 24/10)'."""
    if not items:
        return ""
    parts = [f"RM{i['amount']:.2f} ({fmt_date(date.fromisoformat(i['training_date']))})" for i in items]
    return f"RM{sum(i['amount'] for i in items):.2f} = " + " + ".join(parts)


def pay_driver(db: Session, driver_id: int, receipt_file: str, today: date | None = None) -> dict:
    """Bendahari bayar SEORANG prebet sekali gus (semua baki tertunggak, digabung) dengan satu resit."""
    items = payout_items(db, today, driver_id=driver_id)
    if not items:
        raise ValueError("Tiada baki tertunggak untuk prebet ini")
    batch = secrets_token()
    rows = []
    for it in items:
        row = models.DriverPayout(vehicle_id=it["vehicle_id"], training_date=it["date"], amount=it["outstanding"],
                                  receipt_file=receipt_file, batch=batch, driver_id=driver_id)
        db.add(row)
        rows.append(row)
    db.flush()
    summary = [{"training_date": it["date"].isoformat(), "amount": it["outstanding"]} for it in items]
    total = round(sum(i["amount"] for i in summary), 2)
    note = _carry_note(summary)
    extra = ""
    if len(summary) > 1:
        extra = " Termasuk baki tertunggak latihan: " + ", ".join(fmt_date(it["date"]) for it in items[:-1]) + "."
    _notify(db, driver_id, "payout", f"Bayaran persatuan: RM{total:.2f}",
            f"{note}.{extra} Lihat resit dan tekan 'Diterima'.", items[-1]["date"], severity="warning",
            link="/pendapatan", ref=f"payout:{rows[0].id}")
    resolve_payout_reminders(db, driver_id)
    return {"amount": total, "id": rows[0].id, "batch": batch, "items": summary, "note": note}


def secrets_token() -> str:
    import secrets
    return secrets.token_hex(8)


def resolve_payout_reminders(db: Session, driver_id: int):
    for n in db.query(models.Notification).filter(models.Notification.ref.like(f"payoutdue:{driver_id}:%")):
        db.delete(n)


def payout_history(db: Session, driver_id: int | None = None, limit: int = 40) -> list[dict]:
    """Bayaran yang telah dibuat, dikumpul ikut resit (satu resit = satu prebet = satu bayaran)."""
    q = db.query(models.DriverPayout).order_by(models.DriverPayout.paid_at.desc(), models.DriverPayout.id.desc())
    if driver_id is not None:
        vids = [v.id for v in db.query(models.Vehicle).filter_by(driver_id=driver_id)]
        q = q.filter(or_(models.DriverPayout.driver_id == driver_id, models.DriverPayout.vehicle_id.in_(vids or [0])))
    groups: dict[str, dict] = {}
    for r in q.limit(400).all():
        key = r.batch or f"row{r.id}"
        g = groups.get(key)
        if g is None:
            v = db.get(models.Vehicle, r.vehicle_id)
            drv_id = r.driver_id or (v.driver_id if v else None)
            drv = db.get(models.User, drv_id) if drv_id else None
            g = groups[key] = {"id": r.id, "driver": drv.name if drv else "-", "driver_id": drv_id, "amount": 0.0,
                               "paid_at": r.paid_at.isoformat(), "has_receipt": bool(r.receipt_file),
                               "received": r.received, "items": []}
        g["amount"] = round(g["amount"] + r.amount, 2)
        g["items"].append({"training_date": r.training_date.isoformat(), "amount": r.amount})
    out = list(groups.values())[:limit]
    for g in out:
        g["items"].sort(key=lambda x: x["training_date"])
        g["note"] = _carry_note(g["items"])
    return out


def send_arrears_reminders(db: Session, today: date | None = None) -> int:
    """Ingatkan ahli yang ada tunggakan (amaran: hilang bila dijelaskan), dan bendahari ringkasan.
    Satu notifikasi setiap ahli (kemas kini sahaja)."""
    today = today or today_my()
    treasurers = db.query(models.User).filter_by(is_treasurer=True, active=True).all()
    total_all, who = 0.0, 0
    sent = 0
    uids = {r[0] for r in db.query(models.Payment.user_id).filter(
        models.Payment.status.in_((PaymentStatus.unpaid, PaymentStatus.rejected))).distinct()}
    for uid in uids:
        a = arrears(db, uid, today)
        ref = f"arrears:{uid}"
        if a["total"] <= 0:
            resolve_warning(db, uid, ref)
            continue
        who += 1
        total_all += a["total"]
        sev = "warning"
        extra = " Bayaran anda melebihi 6 bulan: tempahan baru disekat." if a["blocked"] else ""
        _notify(db, uid, "payment", f"Tunggakan RM{a['total']:.2f}",
                f"{a['count']} bayaran belum dibayar (tertua {a['oldest']}). Bayar di tab Bayaran.{extra}",
                severity=sev, link="/bayaran", ref=ref)
        sent += 1
    # ahli yang sudah selesai: buang amaran lama
    for n in db.query(models.Notification).filter(models.Notification.ref.like("arrears:%")):
        tail = n.ref.split(":")[1]
        if tail.isdigit() and int(tail) not in uids:
            db.delete(n)
    for t in treasurers:
        if who:
            _notify(db, t.id, "payout_due", f"Tunggakan ahli: {who} orang, RM{total_all:.2f}",
                    "Lihat tab Bendahari > Tunggakan.", severity="warning", link="/bendahari", ref="arrears:summary")
        else:
            resolve_warning(db, t.id, "arrears:summary")
    for a_ in db.query(models.User).filter_by(role=models.Role.admin, active=True):
        if who:
            _notify(db, a_.id, "admin_alert", f"Tunggakan ahli: {who} orang, RM{total_all:.2f}",
                    "Lihat tab Bayaran.", severity="warning", link="/admin?tab=pay", ref="arrears:summary")
        else:
            resolve_warning(db, a_.id, "arrears:summary")
    db.commit()
    return sent


# ---------------------------------------------------------------- peta kerusi (admin)

def _parse_seat(text):
    try:
        r, c = str(text).split(".")
        return int(r), int(c)
    except Exception:
        return None


def _veh_spec(v: models.Vehicle) -> tuple[str, str, list[int]]:
    return v.vehicle_type.value, v.driver_gender.value, parse_rows(v.seat_rows)


def _gender_of(u: models.User) -> str:
    return u.gender.value if u.gender in (Gender.male, Gender.female) else "male"


def vehicle_layout(db: Session, ev: models.TrainingEvent, v: models.Vehicle, direction: Direction):
    """Susun kerusi satu kenderaan, satu arah: ikut pilihan admin yang sah, selebihnya automatik.
    Return (bookings, {user_id: (r, c)} atau None jika tak muat)."""
    rows_b = db.query(models.Booking).filter_by(training_date=ev.training_date, session_id=ev.session_id,
                                                vehicle_id=v.id, direction=direction,
                                                status=BookingStatus.confirmed).all()
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_([b.user_id for b in rows_b] or [0]))}
    members = [{"user_id": b.user_id, "gender": _gender_of(users[b.user_id])} for b in rows_b]
    stored = {b.user_id: _parse_seat(b.seat) for b in rows_b if _parse_seat(b.seat)}
    vt, dg, rows = _veh_spec(v)
    return rows_b, complete_layout(vt, dg, rows, members, stored)


def seat_map(db: Session, ev: models.TrainingEvent) -> dict:
    d = ev.training_date
    bks = db.query(models.Booking).filter_by(training_date=d, session_id=ev.session_id,
                                             status=BookingStatus.confirmed).all()
    uids = {b.user_id for b in bks}
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(list(uids) or [0]))}
    colleges = {c.id: c for c in db.query(models.College)}

    def person(uid):
        u = users[uid]
        col = colleges.get(u.college_id)
        return {"user_id": uid, "name": u.name, "gender": _gender_of(u), "college": col.code if col else None,
                "college_group": college_group(col.code) if col else None}

    used = {b.vehicle_id for b in bks if b.vehicle_id}
    avail = {v.id: v for v in _vehicles_for(db, d)}
    for vid in used:
        avail.setdefault(vid, db.get(models.Vehicle, vid))
    cars = []
    for v in sorted(avail.values(), key=lambda x: x.id):
        vt, dg, rows = _veh_spec(v)
        drv = db.get(models.User, v.driver_id) if v.driver_id else None
        dirs = {}
        for direction in Direction:
            rb, lay = vehicle_layout(db, ev, v, direction)
            seated, loose = [], []
            for b in rb:
                p = person(b.user_id)
                if lay and b.user_id in lay:
                    p["row"], p["col"] = lay[b.user_id]
                    seated.append(p)
                else:
                    loose.append(p)
            dirs[direction.value] = {"seated": seated, "loose": loose}
        cars.append({"vehicle_id": v.id, "name": v.name, "plate_no": v.plate_no, "type": vt, "driver_gender": dg,
                     "driver_name": drv.name if drv else None, "driver_short": short(drv) if drv else None,
                     "desc": vehicle_desc(v), "rows": rows,
                     "category": vehicle_category(db, v), "zone": vehicle_zone(db, v, colleges)[0],
                     "driver_college": (college_group(vehicle_zone(db, v, colleges)[1]) if vehicle_zone(db, v, colleges)[1] else None),
                     "directions": dirs})
    by_user = defaultdict(list)
    for b in bks:
        if not b.vehicle_id:
            by_user[b.user_id].append(b.direction.value)
    flagged = flagged_lone_ids(db, ev)
    ehail = {b.user_id for b in bks if b.ehailing and not b.vehicle_id}
    unassigned = [{**person(uid), "dirs": sorted(ds), "needs_decision": uid in flagged, "ehailing": uid in ehail}
                  for uid, ds in by_user.items()]
    return {"event_id": ev.id, "training_date": d.isoformat(), "status": ev.status.value,
            "cars": cars, "unassigned": unassigned}


def move_seat(db: Session, ev: models.TrainingEvent, user: models.User, vehicle_id, direction: Direction | None,
              row: int | None, col: int | None):
    """Pindahkan ahli ke kerusi (atau kenderaan lain / keluarkan). Peraturan adab tetap dikuatkuasakan.
    Pada kenderaan yang sama dan kerusi berisi, kedua-duanya bertukar tempat. Raise ValueError jika melanggar."""
    d = ev.training_date
    mine = db.query(models.Booking).filter_by(user_id=user.id, training_date=d, session_id=ev.session_id,
                                              status=BookingStatus.confirmed).all()
    if not mine:
        raise ValueError("Ahli tiada booking aktif pada tarikh ini")
    prev_vid = mine[0].vehicle_id
    if vehicle_id is None:
        for b in mine:
            b.vehicle_id, b.seat = None, None
        db.flush()
        refresh_fees(db, ev)
        return
    v = db.get(models.Vehicle, vehicle_id)
    if v is None or v.approval != models.ApprovalStatus.approved or not v.active:
        raise ValueError("Kenderaan belum aktif/diluluskan")
    vt, dg, rows = _veh_spec(v)
    me = {"user_id": user.id, "gender": _gender_of(user)}
    plan = {}   # direction -> {user_id: (r, c)} untuk kenderaan sasaran
    dirs = [b.direction for b in mine]
    for dr in dirs:
        rb, lay = vehicle_layout(db, ev, v, dr)
        lay = dict(lay or {})
        others = [{"user_id": b.user_id, "gender": _gender_of(db.get(models.User, b.user_id))}
                  for b in rb if b.user_id != user.id]
        g = {m["user_id"]: m["gender"] for m in others + [me]}
        was_here = prev_vid == v.id and user.id in lay
        old = lay.pop(user.id, None) if was_here else None
        lay = {u: s for u, s in lay.items() if u != user.id}
        if dr == direction and row is not None:
            target = (row, col)
            taken = next((u for u, s in lay.items() if s == target), None)
            if taken is not None:
                if old is None:
                    raise ValueError("Kerusi itu sudah diduduki")
                lay[taken] = old          # tukar tempat
            lay[user.id] = target
        else:
            if old is not None:
                lay[user.id] = old        # arah lain kekal di kerusi sedia ada
            else:
                free = [s for s in seat_list(rows) if s not in set(lay.values())]
                for s in free:
                    occ = [{"row": r, "col": c, "gender": g[u]} for u, (r, c) in lay.items()]
                    if not check_layout(vt, dg, rows, occ + [{"row": s[0], "col": s[1], "gender": me["gender"]}]):
                        lay[user.id] = s
                        break
                else:
                    raise ValueError(f"Tiada kerusi sesuai untuk arah {'balik' if dr == Direction.returning else 'pergi'} dalam {v.name}")
        err = check_layout(vt, dg, rows, [{"row": r, "col": c, "gender": g[u]} for u, (r, c) in lay.items()])
        if err:
            raise ValueError(err)
        plan[dr] = (rb, lay)
    for dr, (rb, lay) in plan.items():
        mybk = next(b for b in mine if b.direction == dr)
        for b in rb + [mybk]:
            if b.user_id in lay:
                b.seat = f"{lay[b.user_id][0]}.{lay[b.user_id][1]}"
        mybk.vehicle_id = v.id
    for b in mine:
        b.vehicle_id = v.id
        b.ehailing, b.ehailing_note = False, ""
        if b.direction not in plan:
            b.seat = None
    db.flush()
    refresh_fees(db, ev)
    if ev.status == EventStatus.finalised and prev_vid != v.id:
        _notify(db, user.id, "car", f"Kenderaan ditetapkan: {fmt_date(d)}", _car_text(db, v), d)


# ---------------------------------------------------------------- penyata untung rugi (admin sahaja)

def profit_statement(db: Session, month: str | None = None, today: date | None = None) -> dict:
    """Kutipan ahli tolak bayaran prebet, ikut tarikh latihan dan ikut bulan. Boleh negatif (kebajikan ahli).
    collected = ahli yang sudah bayar; owed = bayaran tetap prebet yang patut dibayar; paid_out = sudah dibayar bendahari.
    net = collected - owed (anggaran penuh); realised = collected - paid_out (tunai sebenar setakat ini)."""
    today = today or today_my()
    q = db.query(models.TrainingEvent).filter(models.TrainingEvent.status == EventStatus.finalised,
                                              models.TrainingEvent.training_date <= today)
    if month:
        y, m = int(month[:4]), int(month[5:7])
        q = q.filter(models.TrainingEvent.training_date >= date(y, m, 1),
                     models.TrainingEvent.training_date < date(y + (m == 12), m % 12 + 1, 1))
    dates = sorted({e.training_date for e in q})
    days, months = [], {}
    for d in dates:
        pays = [p for p in db.query(models.Payment).filter_by(training_date=d) if p.status != PaymentStatus.void]
        collected = sum(p.amount for p in pays if p.status == PaymentStatus.paid)
        expected = sum(p.amount for p in pays)
        rows = payout_rows(db, d)
        owed = sum(r["owed"] for r in rows)
        paid_out = sum(r["paid_out"] for r in rows)
        row = {"training_date": d.isoformat(), "label": fmt_date(d), "expected": round(expected, 2),
               "collected": round(collected, 2), "owed": round(owed, 2), "paid_out": round(paid_out, 2),
               "net": round(collected - owed, 2), "realised": round(collected - paid_out, 2),
               "prebets": len(rows)}
        days.append(row)
        mk = d.strftime("%Y-%m")
        mt = months.setdefault(mk, {"month": mk, "expected": 0.0, "collected": 0.0, "owed": 0.0, "paid_out": 0.0,
                                    "net": 0.0, "realised": 0.0, "trainings": 0})
        for k in ("expected", "collected", "owed", "paid_out", "net", "realised"):
            mt[k] = round(mt[k] + row[k], 2)
        mt["trainings"] += 1
    total = {k: round(sum(m[k] for m in months.values()), 2)
             for k in ("expected", "collected", "owed", "paid_out", "net", "realised")}
    return {"days": days, "months": [months[k] for k in sorted(months)], "total": total}


# ---------------------------------------------------------------- admin bertugas

def duty_contacts(db: Session, d: date | None = None) -> dict:
    """Admin yang bertugas pada hari itu (ikut bulan & hari yang dipilih admin). Tiada = pentadbir laman web."""
    d = d or today_my()
    out = []
    for r in db.query(models.AdminDuty).filter_by(month=d.strftime("%Y-%m")):
        if str(d.weekday()) not in [x for x in r.weekdays.split(",") if x]:
            continue
        u = db.get(models.User, r.user_id)
        if u is not None and u.active and u.role == models.Role.admin:
            out.append({"name": short(u), "phone": (r.phone or u.phone or "").strip()})
    return {"date": d.isoformat(), "duty": out,
            "fallback": {"name": config.SITE_CONTACT_NAME, "phone": config.SITE_CONTACT_PHONE},
            "site": {"name": config.SITE_CONTACT_NAME, "phone": config.SITE_CONTACT_PHONE}}


def next_training_date(db: Session) -> date:
    ups = upcoming_dates(db, today_my(), days=8)
    return ups[0][0] if ups else today_my()


# ---------------------------------------------------------------- teks syarat lalai (dikemas kini ikut tetapan semasa)

def default_rules(db: Session) -> list[str]:
    t = fee_tables(db)
    f, p = t["fees"], t["payouts"]
    cut, auto = fmt12(_hm(config.CUTOFF_TIME)), fmt12(_hm(config.AUTO_FINALISE_TIME))
    pay = fmt12(_hm(config.PAY_DEADLINE_TIME))
    mode = payout_mode(db)
    mode_txt = {"latihan": "selepas setiap latihan (sebelum tengah malam hari selepas latihan)",
                "mingguan": "setiap minggu (Isnin–Ahad), dibayar sebelum tengah malam hari Ahad",
                "bulanan": "setiap bulan, dibayar sebelum tengah malam hari terakhir bulan"}[mode]
    return [
        "Kemudahan prebet terbuka kepada semua kolej dan semua sesi/tahun ahli PSSGUTM. Kolej yang belum ada checkpoint (bus stop) "
        "dibuka selepas BKK menambahnya.",
        f"Hari latihan: pilih Pergi / Balik SEBELUM {cut} pada hari latihan. Selepas {cut} pilihan ditutup; hubungi BKK jika perlu "
        "tambah atau batal (hanya admin boleh).",
        f"Prebet juga mesti sahkan 'boleh bawa' sebelum {cut} pada hari latihan. BKK sahkan senarai; jika terlupa, senarai disahkan "
        f"automatik pada {auto}.",
        f"Ahli berada di checkpoint (bus stop) pilihan anda pada 5 minit sebelum waktu ambil; prebet mengambil pada waktu pickup. "
        "Naik KENDERAAN YANG DIMAKLUMKAN sahaja (nama prebet, jenama, warna dan no. plat).",
        "Latihan 9:00–11:00 malam. Prebet menghantar balik selepas latihan.",
        f"Yuran seorang (pergi + balik): kereta dekat RM{f['car']['dekat']:.2f}, kereta jauh RM{f['car']['jauh']:.2f}, "
        f"motosikal dekat RM{f['motorcycle']['dekat']:.2f}, motosikal jauh RM{f['motorcycle']['jauh']:.2f}.",
        f"Bayar kepada persatuan sebelum {pay} hari selepas latihan (latihan Sabtu: sebelum {pay} hari Ahad). "
        "Lewat dari itu menjadi tunggakan (hutang). Tunggakan lebih 6 bulan menyebabkan tempahan disekat.",
        "Ahli yang kolejnya sama dengan tempat latihan (cth latihan di KTR, ahli KTR) berjalan kaki; tiada prebet.",
        "Adab tempat duduk: lelaki dan perempuan tidak sebaris; perempuan tidak duduk di sebelah prebet lelaki; "
        "perempuan tidak boleh seorang diri dalam kereta prebet lelaki (mesti dua orang atau lebih, jika tidak BKK uruskan e-hailing); "
        "motosikal hanya penumpang sama jantina.",
        "Susunan kenderaan: sama jantina & kategori kolej dahulu, kolej sama dahulu, kemudian isi tempat kosong ikut kolej dekat/jauh. "
        "Jika penuh atau melanggar adab, BKK uruskan e-hailing.",
        f"Prebet dibayar TETAP setiap hari latihan yang beroperasi: kereta dekat RM{p['car']['dekat']:.2f}, kereta jauh RM{p['car']['jauh']:.2f}, "
        f"motosikal dekat RM{p['motorcycle']['dekat']:.2f}, motosikal jauh RM{p['motorcycle']['jauh']:.2f} (hanya admin boleh ubah). "
        "Tidak beroperasi pada satu latihan = tiada bayaran untuk latihan itu.",
        f"Bayaran prebet dibuat bendahari {mode_txt}. Baki yang belum dibayar digabung dalam bayaran seterusnya.",
        "Prebet tanda 'dah sampai tempat latihan' dan 'dah hantar semua'. Jika terlupa, hanya amaran kepada prebet & bendahari.",
        "Prebet wajib muat naik lesen sah. Satu prebet boleh daftar lebih satu kenderaan dan pilih yang digunakan pada setiap tarikh.",
        f"Urusan prebet/pengangkutan: hubungi admin bertugas pada hari itu. Masalah laman web: {config.SITE_CONTACT_PHONE}.",
    ]


# ---------------------------------------------------------------- tempat ambil aktiviti luar (admin)

def _activity_bookings(db: Session, d: date, user_id: int | None = None, session_ids: list[int] | None = None):
    q = db.query(models.Booking).filter(
        models.Booking.training_date == d,
        models.Booking.status.in_((BookingStatus.confirmed, BookingStatus.ineligible)))
    if user_id is not None:
        q = q.filter(models.Booking.user_id == user_id)
    if session_ids is not None:
        q = q.filter(models.Booking.session_id.in_(session_ids))
    return q.all()


def admin_set_member_pickup(db: Session, user: models.User, d: date, place: str | None,
                            direction: str | None = None) -> int:
    """Admin tukar tempat ambil (pergi) / hantar (balik) seorang ahli pada aktiviti luar.
    place kosong = kembali ke checkpoint kolej ahli. direction kosong = kedua-dua arah."""
    rows = _activity_bookings(db, d, user_id=user.id)
    if direction in ("going", "returning"):
        rows = [b for b in rows if b.direction.value == direction]
    if not rows:
        raise ValueError("Ahli ini tiada tempahan pada tarikh/arah itu")
    s = db.get(models.TrainingSession, rows[0].session_id)
    if s is None or s.one_off_date is None:
        raise ValueError("Tempat ambil hanya boleh ditukar untuk aktiviti luar")
    label = clean_place(place)
    if label:
        pt_id, place_name = None, label
    else:
        pt = resolve_point(db, user)
        if pt is None:
            raise ValueError("Ahli ini tiada checkpoint kolej. Isi nama tempat.")
        pt_id, place_name = pt.id, ""
    for b in rows:
        b.pickup_point_id, b.pickup_place = pt_id, place_name
    db.flush()
    ev = event_on(db, d)
    if ev is not None:
        apply_venue(db, ev)
    arah = {"going": "pergi", "returning": "balik"}.get(direction or "", "pergi dan balik")
    _notify(db, user.id, "pickup", f"Tempat {arah} dikemas kini: {fmt_date(d)}",
            f"BKK tetapkan tempat {arah} anda di {place_name or pickup_point_name(db, rows[0])}.", d)
    return len(rows)


def admin_set_activity_pickup(db: Session, legs: list[models.TrainingSession], mode: str,
                              gather_place: str, return_place: str = "", return_same: bool = False) -> int:
    """Admin tetapkan tempat aktiviti. Tempat pergi tetap dan/atau tempat balik tetap (atau balik = pergi) wajib diikut
    semua ahli; arah yang dikosongkan dipilih ahli sendiri (ikut 'mode': rumah, kolej atau kedua)."""
    if mode not in PICKUP_MODES:
        raise ValueError("Mod ambil tak sah")
    go, back = clean_place(gather_place), clean_place(return_place)
    if return_same and not go:
        raise ValueError("Isi tempat pergi dahulu jika balik sama dengan pergi")
    for s in legs:
        s.pickup_mode = mode
        s.gather_place, s.return_place, s.return_same = go, ("" if return_same else back), bool(return_same)
    db.flush()
    changed, told = 0, {}
    for s in legs:
        for b in _activity_bookings(db, s.one_off_date, session_ids=[s.id]):
            fixed = fixed_place(s, b.direction.value)
            if fixed:
                b.pickup_point_id, b.pickup_place = None, fixed
                told[b.user_id] = s.one_off_date
                changed += 1
    db.flush()
    for s in legs:
        ev = event_on(db, s.one_off_date)
        if ev is not None:
            apply_venue(db, ev)
    for uid, d in told.items():
        _notify(db, uid, "pickup", f"Tempat ditetapkan BKK: {fmt_date(d)}",
                f"Pergi: {go or 'pilihan anda'}. Balik: {go if return_same else (back or 'pilihan anda')}.", d)
    return changed


# ---------------------------------------------------------------- penanggung yuran aktiviti luar

def assoc_owed(db: Session, legs: list[models.TrainingSession]) -> float:
    """Jumlah yang persatuan perlu serah kepada BKK untuk aktiviti ini = bayaran penuh kenderaan yang beroperasi
    (hanya selepas senarai disahkan; sebelum itu 0)."""
    ids = [s.id for s in legs]
    total = 0.0
    for d in sorted({s.one_off_date for s in legs}):
        for r in payout_rows(db, d):
            hit = db.query(models.Booking.id).filter(
                models.Booking.vehicle_id == r["vehicle_id"], models.Booking.training_date == d,
                models.Booking.session_id.in_(ids)).first()
            if hit:
                total += r["owed"]
    return round(total, 2)


def admin_set_activity_funding(db: Session, legs: list[models.TrainingSession], by_assoc: bool | None,
                               settled: bool | None) -> None:
    """Tukar penanggung yuran (ahli bayar = lalai, atau persatuan tanggung) dan tanda persatuan sudah serah kepada BKK.
    Ahli yang sudah bayar tidak rugi: bayaran dibawa sebagai kredit (_sync_payment). Bayaran 'pending' (resit belum
    disahkan) menjadi kredit bila admin sahkan. Bila ditukar kembali ke ahli bayar, kredit digunakan semula
    untuk bayaran baharu jika senarai sudah disahkan."""
    if by_assoc is not None and by_assoc != bool(legs[0].fee_by_assoc):
        for s in legs:
            s.fee_by_assoc = by_assoc
            if not by_assoc:
                s.assoc_settled = False
        db.flush()
        for s in legs:
            for uid in {b.user_id for b in _activity_bookings(db, s.one_off_date, session_ids=[s.id])}:
                _sync_payment(db, db.get(models.User, uid), s.one_off_date)
            ev = event_on(db, s.one_off_date)
            if ev is not None:
                refresh_fees(db, ev)
                if ev.status == EventStatus.finalised and not by_assoc:
                    for b in _activity_bookings(db, s.one_off_date, session_ids=[s.id]):
                        u = db.get(models.User, b.user_id)
                        pay = db.query(models.Payment).filter_by(user_id=u.id, training_date=s.one_off_date).first()
                        if b.vehicle_id and pay and pay.status == PaymentStatus.unpaid and u.credit_balance > 0:
                            use = min(u.credit_balance, payment_due(pay))
                            pay.credit_applied += use
                            u.credit_balance -= use
    if settled is not None:
        if settled and not legs[0].fee_by_assoc:
            raise ValueError("Aktiviti ini tidak ditanggung persatuan")
        for s in legs:
            s.assoc_settled = bool(settled)
