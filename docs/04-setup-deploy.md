# 04 · Setup & deploy (dari kosong)

> Gunakan akaun **persatuan** (emel BKK), bukan peribadi, supaya boleh diserah. Simpan semua kata laluan/kunci dalam pengurus kata laluan BKK. Item bertanda 🔎 mungkin berbeza dalam dashboard semasa; ikut yang tertera di skrin.

## Ringkasan perkhidmatan
| Perkhidmatan | Guna untuk | Kos |
|---|---|---|
| GitHub (repo PRIVATE) | Simpan kod, Actions keepalive | Percuma |
| Supabase | PostgreSQL + Storage (bucket `uploads`) | Percuma |
| Render | Hos backend FastAPI | Percuma (tidur jika tiada trafik; keepalive) |
| Vercel | Hos frontend | Percuma |
| Brevo (pilihan) | Emel lupa kata laluan | Percuma (had harian) |
| Google Cloud (pilihan) | Log masuk Google | Percuma |

## Langkah 1 — Supabase
1. Cipta projek. Simpan **kata laluan database**.
2. *Project Settings › Database*: salin **connection string** (pilih mod yang serasi dengan Render; 🔎 pooler/direct). Tukar prefix kepada `postgresql+psycopg2://…` → ini `DATABASE_URL`.
3. *Storage*: cipta bucket **`uploads`** (private). *Project Settings › API*: salin **Project URL** (`SUPABASE_URL`) dan **service_role key** (`SUPABASE_SERVICE_KEY`; **rahsia — backend sahaja**, jangan letak di frontend/repo).

## Langkah 2 — GitHub
Repo **PRIVATE**. Tambah Secret `BACKEND_URL` (Settings › Secrets and variables › Actions) = URL Render **tanpa `/health` dan tanpa `/` di hujung**, cth `https://nama.onrender.com`. Workflow `keepalive.yml` ping `/health` setiap 10 minit. Jika repo/akaun tidak aktif lama, GitHub boleh hentikan jadual: semak tab Actions sekali sebulan.

## Langkah 3 — Render (backend)
New › Web Service › sambung repo. 🔎 Root Directory `backend`. Runtime: **Python** (yang digunakan sekarang; log Render menunjukkan persekitaran `.venv` Python 3.12). Build Command 🔎 `pip install -r requirements.txt -r requirements-postgres.txt`. Start Command: lihat bawah. (`backend/Dockerfile` ialah pilihan alternatif untuk VPS.) Health check path `/health`. **Mesti 1 worker.**
Environment variables (minimum):
| Nama | Nilai |
|---|---|
| `ENV` | `production` |
| `SECRET_KEY` | rentetan rawak panjang (`openssl rand -hex 32`). **Jangan tukar sembarangan**: semua pengguna akan log keluar |
| `DATABASE_URL` | dari Supabase |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (`SUPABASE_BUCKET`=`uploads`) | dari Supabase |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | admin pertama (dibuat sekali semasa seed) |
| `CORS_ORIGINS` | URL Vercel, cth `https://nama.vercel.app` (koma untuk banyak) |
| `FRONTEND_URL` | URL Vercel (untuk pautan dalam emel) |
| `REQUIRE_ROSTER` | `true` |
| `ALLOW_RESET` | `false` (hidupkan hanya semasa reset, kemudian matikan) |
| `BREVO_API_KEY`, `MAIL_FROM` | emel lupa kata laluan (lihat bawah) |
| `GOOGLE_CLIENT_ID` | log masuk Google (lihat bawah) |
Senarai penuh + lalai: `.env.example` dan `backend/app/config.py`.
**Start Command yang digunakan: `python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`.** Jadi seed (data asas kolej, checkpoint, tempat, sesi, admin pertama) jalan **automatik setiap deploy/restart**, dan mesti selamat diulang (idempotent). Seed gagal = server tak mula (lihat [05 Operasi](05-operasi-bkk.md), "Port scan timeout"). Pada permulaan app juga jalankan `create_all` + `run_migrations()`. Selepas deploy pertama, import senarai ahli di Admin › Lagi › Senarai ahli sah.

## Langkah 4 — Vercel (frontend)
Import repo › Root Directory `frontend` › Framework Vite (build `npm run build`, output `dist`). Env: `VITE_API_URL` = URL Render. `vercel.json` sudah ada (rewrite SPA). Selepas tukar env, **Redeploy**.

## Langkah 5 — Emel lupa kata laluan (Brevo)
Render percuma **menyekat SMTP**, jadi guna Brevo HTTP API. Daftar Brevo › **sahkan emel penghantar** (Senders) › cipta **API key** › isi `BREVO_API_KEY`, `MAIL_FROM` (mesti emel yang disahkan), `FRONTEND_URL`. Ujian: Lupa kata laluan di app. Jika gagal, lihat log Render: carian "Brevo" menunjukkan sebab (sender belum disahkan, kunci salah, dsb.). Tanpa konfigurasi ini permintaan pergi kepada admin (bukan emel).

## Langkah 6 — Log masuk Google (pilihan)
Google Cloud Console › APIs & Services › Credentials › OAuth client ID jenis **Web** › Authorized JavaScript origins = URL Vercel (dan `http://localhost:5173` untuk dev) › salin Client ID ke `GOOGLE_CLIENT_ID` (Render). Kosong = butang Google disembunyikan. Pengguna Google tetap mesti ada no. ahli sah.

## Aliran kerja kod → produksi
```
branch baru → ubah kod → pytest + npm run build lulus → push → Pull Request → merge ke main
→ Render & Vercel auto-deploy → semak /health dan app
```
Skema DB berubah? Tambah lajur dalam `models.py` **dan** `migrate.py`. Elakkan deploy waktu latihan (Rabu/Sabtu 5–11 PM).

## Sandaran (Backup)
Supabase percuma tidak menjamin sandaran yang boleh dipulihkan 🔎. Dua lapis:
1. **Dalam app:** Admin › Lagi › **Muat turun sandaran** (zip CSV, admin sahaja). Sebulan sekali dan sebelum reset tahunan; simpan dalam folder Drive BKK peribadi (2–3 orang).
2. **Pentadbir laman web:** sesekali eksport pangkalan data penuh (Supabase › Database › Backups atau `pg_dump`) dan muat turun bucket `uploads` (lesen, resit, QR; tidak ada dalam zip CSV).
Fail sandaran mengandungi data peribadi: jangan kongsi di WhatsApp.

## Tempatan (local)
Lihat `CLAUDE.md` / `README.md`: SQLite automatik jika `DATABASE_URL` tiada. Dalam PowerShell guna `$env:NAMA="nilai"`.
