# 01 · Gambaran sistem (System overview)

## Tujuan
Gantikan Google Form + hebahan WhatsApp untuk pengangkutan latihan silat. Ahli pilih tarikh & pergi/balik, sistem susun kenderaan prebet secara automatik ikut peraturan adab dan kolej, ahli bayar kepada persatuan, bendahari bayar prebet.

## Peranan (Roles)
| Peranan | Siapa | Boleh buat |
|---|---|---|
| **member** (ahli) | Ahli silat tanpa kenderaan | Tempah tarikh, hantar resit bayaran, lihat kenderaan & rakan sekereta |
| **driver** (prebet) | Pemandu sukarela (kereta/motor) | Daftar kenderaan, sahkan "boleh bawa" tiap tarikh, tanda sampai/hantar, lihat pendapatan |
| **admin** | BKK | Semua: sahkan senarai, urus ahli/kenderaan/harga, penyata, reset |
| **is_treasurer** | Bendahari (bendera tambahan) | Sahkan bayaran ahli, bayar prebet + muat naik resit. Tidak nampak penyata untung/rugi atau tukar harga |

## Seni bina (Architecture)
```
Pengguna (telefon, PWA)
   │  HTTPS
   ▼
Vercel ── frontend React/Vite (fail statik, rewrite semua laluan ke index.html)
   │  fetch API (VITE_API_URL)
   ▼
Render ── backend FastAPI (1 worker + APScheduler)
   │              ▲
   │              └── GitHub Actions: ping /health tiap 10 min (elak Render tidur)
   ├──► Supabase PostgreSQL  (DATABASE_URL)
   ├──► Supabase Storage     (resit, QR, logo; SUPABASE_URL + SUPABASE_SERVICE_KEY)
   ├──► Brevo HTTP API       (emel lupa kata laluan; pilihan)
   └──► Google Sign-In       (GOOGLE_CLIENT_ID; pilihan)
```
Tanpa `SUPABASE_*`, fail disimpan di cakera setempat (`UPLOAD_DIR`) — **hilang bila Render restart**, jadi produksi mesti guna Supabase Storage.

## Struktur repo
```
backend/app/        main.py (app+scheduler) · config.py · models.py · migrate.py · seed.py
                    security.py · storage.py · mailer.py · google_auth.py
                    routes/{auth,member,bookings,driver,admin}.py
                    services/assign.py (algoritma susunan) · services/booking.py (logik bisnes)
backend/tests/      test_assign.py · test_flow.py
frontend/src/       App.jsx · api.js · pages/ · components/ · styles.css
.github/workflows/  keepalive.yml
docs/               dokumentasi ini
```

## Jadual data utama
users, member_roster (senarai ahli sah), colleges, pickup_points (checkpoint; banyak per kolej), venues (tempat latihan), training_sessions (Rabu/Sabtu), training_events (satu latihan satu tarikh: open/finalised/cancelled), bookings, payments, vehicles (+vehicle_kinds, vehicle_unavailable), prebet_availability (sahkan boleh bawa + kenderaan dipilih), duty_ticks (tanda sampai/hantar), driver_payouts (bayaran prebet), admin_duty (admin bertugas), holidays, notifications, feedback, settings (nilai boleh ubah: harga, kadar, masa, kaedah bayar), password_resets.

## Kerja latar (Scheduler)
| Jadual | Buat apa |
|---|---|
| Setiap hari 00:05 | Jana tempahan, peringatan latihan, peringatan keselamatan rider, peringatan bayar prebet, peringatan lesen, peringatan tunggakan |
| Setiap 10 minit | Notis kepada prebet, amaran tanda sampai/hantar, **auto-sah senarai pada 7:30 PM** hari latihan |

Scheduler hidup dalam proses backend. Jika Render tidur, kerja ini tidak jalan — sebab itu ada keepalive.

## Keselamatan ringkas
JWT (`SECRET_KEY` wajib ditukar dalam produksi, app enggan mula jika tidak), kata laluan bcrypt, had kadar (rate limit) pada login/lupa/daftar, hanya no. ahli dalam roster boleh daftar, maklumat bank/QR prebet hanya admin & bendahari nampak, fail diakses melalui API berautentikasi.

## Had yang perlu tahu
- Render percuma: cold start 30–60 saat jika keepalive gagal; SMTP disekat (guna Brevo HTTP API).
- Tiada Alembic: perubahan skema = tambah lajur dalam `migrate.py`.
- Tiada notifikasi WhatsApp; notifikasi dalam app sahaja (loceng).
