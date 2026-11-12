# PSSGUTM Transport

PWA pengangkutan latihan Prebet Silat PSSGUTM (Rabu & Sabtu 9-11 PM): ahli tempah, prebet bawa, admin BKK susun & sahkan, bendahari bayar prebet.
Stack: FastAPI + SQLAlchemy (Render + Supabase) · React + Vite PWA (Vercel) · GitHub Actions keepalive.

> **Repo ini mesti PRIVATE.** Jangan commit `.env`, senarai ahli, `uploads/` atau kunci API.

## Mula di sini
- Dokumentasi penuh: [`docs/README.md`](docs/README.md) (versi PDF: `PSSGUTM-Transport-Dokumentasi.pdf`)
- Untuk AI / pembangun: [`CLAUDE.md`](CLAUDE.md) / [`ANTIGRAVITY.md`](ANTIGRAVITY.md) & [`docs/06-membangun-dengan-ai.md`](docs/06-membangun-dengan-ai.md)
- Peraturan bisnes: [`docs/02-peraturan-bisnes.md`](docs/02-peraturan-bisnes.md)
- Deploy & env: [`docs/04-setup-deploy.md`](docs/04-setup-deploy.md), `.env.example`
- Serah tugas tahunan: [`docs/05-operasi-bkk.md`](docs/05-operasi-bkk.md)

## Jalankan setempat
```powershell
cd backend
python -m venv venv ; venv\Scripts\activate
pip install -r requirements-dev.txt
$env:ADMIN_EMAIL="bkk@contoh.com"; $env:ADMIN_PASSWORD="password-kuat"; $env:REQUIRE_ROSTER="false"
python -m app.seed
uvicorn app.main:app --reload        # http://localhost:8000/docs
python -m pytest -q                  # ujian
cd ..\frontend ; npm install ; npm run dev   # http://localhost:5173
```
Linux/Mac: `export NAMA=nilai` ganti `$env:NAMA="nilai"`.
