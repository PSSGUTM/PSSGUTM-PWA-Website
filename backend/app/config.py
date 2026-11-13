import os

# Yuran seorang per latihan (pergi + balik, tiada potongan untuk sehala):
# ikut jenis kenderaan dan kategori kolej. Motosikal bawa seorang sahaja.
FEES = {
    "car": {"dekat": float(os.getenv("FEE_DEKAT", "3")), "jauh": float(os.getenv("FEE_JAUH", "4"))},
    "motorcycle": {"dekat": float(os.getenv("FEE_MOTOR_DEKAT", "1")), "jauh": float(os.getenv("FEE_MOTOR_JAUH", "2"))},
}


# Bayaran TETAP kepada prebet bagi SATU hari latihan (bukan per penumpang), ikut kategori kolej prebet.
# Hanya admin boleh ubah dalam app (Admin > Lagi > Harga).
PAYOUTS = {
    "car": {"dekat": float(os.getenv("PAYOUT_CAR_DEKAT", "10")), "jauh": float(os.getenv("PAYOUT_CAR_JAUH", "14"))},
    "motorcycle": {"dekat": float(os.getenv("PAYOUT_MOTOR_DEKAT", "1")), "jauh": float(os.getenv("PAYOUT_MOTOR_JAUH", "2"))},
}


def payout_default(vehicle_type: str, category: str) -> float:
    return PAYOUTS.get(vehicle_type, PAYOUTS["car"]).get(category, 0.0)


def fee_amount(vehicle_type: str, category: str) -> float:
    """Kadar lalai (env). Kadar sebenar boleh diubah admin dalam app: lihat services.booking.fee_amount(db, ...)."""
    return FEES.get(vehicle_type, FEES["car"])[category]


# Hanya no. ahli dalam senarai ahli sah boleh daftar (matikan untuk ujian: REQUIRE_ROSTER=false)
REQUIRE_ROSTER = os.getenv("REQUIRE_ROSTER", "true").lower() != "false"
SAFETY_REMINDER_DAYS = int(os.getenv("SAFETY_REMINDER_DAYS", "3"))
# Sesi ahli yang layak guna prebet (nilai awal sahaja). Admin tukar dalam app: Admin > Lagi > Kelayakan.
# Format = 4 digit selepas "SG" pada no. ahli, cth 2627. Boleh lebih satu: "2627,2728".
DEFAULT_ELIGIBLE_YEARS = os.getenv("ELIGIBLE_YEARS", "*")  # * = semua sesi/tahun

GENERATE_DAYS_AHEAD = int(os.getenv("GENERATE_DAYS_AHEAD", "8"))    # jana booking berapa hari ke depan
REMINDER_DAYS_BEFORE = int(os.getenv("REMINDER_DAYS_BEFORE", "2"))
CAR_SEATS_DEFAULT = int(os.getenv("CAR_SEATS_DEFAULT", "4"))        # anggaran kereta tambahan diperlukan

# Kenderaan yang bawa <= N penumpang digabungkan ke kenderaan lain (jika semua muat & ikut adab seat). 0 = matikan.
# Tempahan hanya ikut tarikh yang dipilih ahli (bukan jadual berulang). Set true untuk hidupkan semula jadual berulang.
AUTO_FROM_PREFERENCES = os.getenv("AUTO_FROM_PREFERENCES", "false").lower() == "true"
COMBINE_BELOW_PASSENGERS = int(os.getenv("COMBINE_BELOW_PASSENGERS", "2"))
BOOK_DAYS_AHEAD = int(os.getenv("BOOK_DAYS_AHEAD", "21"))           # berapa hari ke depan ahli boleh pilih tarikh

# Format no. ahli yang sah (regex). Digunakan semasa import/tambah senarai ahli. Tukar jika format persatuan berubah.
MEMBER_NO_PATTERN = os.getenv("MEMBER_NO_PATTERN", r"^SG\d{7}$")

# Lupa kata laluan. Pilihan 1 (disyorkan untuk Render percuma, yang menyekat SMTP): Brevo melalui HTTP API.
#   BREVO_API_KEY + MAIL_FROM (emel penghantar yang disahkan dalam Brevo).
# Pilihan 2: SMTP (tidak berfungsi pada Render percuma). Kalau tiada satu pun diset, permintaan dihantar kepada admin.
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
MAIL_FROM = os.getenv("MAIL_FROM", "")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "PSSGUTM Transport")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or MAIL_FROM or os.getenv("SMTP_USER", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")            # cth https://pssgutm-app.onrender.com (untuk pautan dalam emel)
RESET_TOKEN_MINUTES = int(os.getenv("RESET_TOKEN_MINUTES", "60"))

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
MAX_RECEIPT_BYTES = 5 * 1024 * 1024
# Pembersihan automatik: padam gambar resit selesai & notifikasi lebih N bulan (0 = tutup). Rekod bayaran kekal.
RETENTION_MONTHS = float(os.getenv("RETENTION_MONTHS", "6"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]

# Log masuk dengan Google (Google Cloud > Credentials > OAuth client ID jenis Web). Kosong = butang Google disembunyikan.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()

# ---- Fasa 6 ----
# Prebet mesti sahkan "boleh bawa" bagi setiap tarikh sebelum disusun (matikan: REQUIRE_PREBET_CONFIRM=false)
REQUIRE_PREBET_CONFIRM = os.getenv("REQUIRE_PREBET_CONFIRM", "true").lower() != "false"
# Kereta pemandu lelaki: penumpang perempuan mesti 0 atau >= 2 (tidak boleh tepat seorang)
LONE_FEMALE_RULE = os.getenv("LONE_FEMALE_RULE", "true").lower() != "false"
# Tunggakan: ahli yang belum bayar masih boleh naik; sekat hanya jika bayaran tertua melebihi N hari
ARREARS_BLOCK_DAYS = int(os.getenv("ARREARS_BLOCK_DAYS", "183"))
# Butang "Reset semua data ujian" hanya aktif jika ALLOW_RESET=true (matikan selepas ujian)
ALLOW_RESET = os.getenv("ALLOW_RESET", "false").lower() == "true"
# Aktiviti luar: had jarak motosikal (km) dan harga motosikal lalai (RM)
MOTOR_MAX_KM_DEFAULT = float(os.getenv("MOTOR_MAX_KM_DEFAULT", "10"))
MOTOR_ACTIVITY_PRICE_DEFAULT = float(os.getenv("MOTOR_ACTIVITY_PRICE_DEFAULT", "3"))
LICENCE_REMIND_DAYS = int(os.getenv("LICENCE_REMIND_DAYS", "30"))
# Prebet mesti muat naik gambar lesen + tarikh tamat sebelum hantar kenderaan
REQUIRE_LICENCE = os.getenv("REQUIRE_LICENCE", "true").lower() != "false"

# ---- Fasa 7: aliran masa hari latihan (waktu Malaysia, HH:MM) ----
# Prebet sahkan & ahli pilih Pergi/Balik: tutup pada jam ini pada hari latihan. Selepas itu hanya admin boleh tambah/buang.
CUTOFF_TIME = os.getenv("CUTOFF_TIME", "17:00")
# BKK sahkan senarai (dari 5 petang). Jika BKK tak sahkan: disahkan automatik pada jam ini hari latihan
AUTO_FINALISE_TIME = os.getenv("AUTO_FINALISE_TIME", "19:00")
# Ahli mesti bayar persatuan sebelum jam ini pada hari selepas latihan; selepas itu jadi tunggakan (hutang)
PAY_DEADLINE_TIME = os.getenv("PAY_DEADLINE_TIME", "12:00")
# Ahli sampai di checkpoint ini sekian minit sebelum waktu mula pickup
ARRIVE_EARLY_MINUTES = int(os.getenv("ARRIVE_EARLY_MINUTES", "5"))
# Hubungan masalah laman web (bukan urusan prebet)
SITE_CONTACT_PHONE = os.getenv("SITE_CONTACT_PHONE", "0192278390")
SITE_CONTACT_NAME = os.getenv("SITE_CONTACT_NAME", "Pentadbir laman web (Mir)")
# Matikan sekatan masa (untuk ujian)
ENFORCE_CUTOFF = os.getenv("ENFORCE_CUTOFF", "true").lower() != "false"
