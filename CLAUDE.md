# CLAUDE.md / ANTIGRAVITY.md — konteks projek untuk Google Antigravity, Claude Code & AI lain

> **Nota Peralihan:** Projek ini pada mulanya dibangunkan dengan Claude Code dan kini telah berpindah kepada **Google Antigravity** untuk pengaturcaraan dan penyelenggaraan AI (*coding AI*). Fail ini berfungsi sebagai panduan konteks utama.

Baca fail ini dahulu, kemudian `docs/01-gambaran-sistem.md` dan `docs/02-peraturan-bisnes.md` sebelum ubah apa-apa.

## Apa projek ini
PWA pengangkutan latihan Prebet Silat PSSGUTM BKK (UTM). Ahli tempah pergi/balik, prebet (pemandu sukarela) bawa, admin BKK susun & sahkan, bendahari bayar prebet. Latihan Rabu & Sabtu 9–11 PM. Bahasa UI: Bahasa Melayu. Zon waktu: Asia/Kuala_Lumpur.

## Stack & deploy
- Backend: FastAPI + SQLAlchemy 2 + Pydantic 2 + APScheduler (`backend/app/`). Hos: Render (percuma). DB: Supabase PostgreSQL. Fail (resit/QR/logo): Supabase Storage.
- Frontend: React 18 + Vite + react-router 6, PWA (`frontend/src/`). Hos: Vercel.
- Keepalive: GitHub Actions ping `/health` setiap 10 minit (`.github/workflows/keepalive.yml`) — scheduler hanya jalan bila server hidup.
- Push ke `main` = auto-deploy (Render + Vercel).

## Arahan
```bash
cd backend && python -m venv venv && venv\Scripts\activate   # Linux/Mac: source venv/bin/activate
pip install -r requirements-dev.txt
python -m app.seed                 # data asas + admin (ADMIN_EMAIL/ADMIN_PASSWORD)
uvicorn app.main:app --reload      # http://localhost:8000/docs
python -m pytest -q                # WAJIB lulus sebelum commit
cd frontend && npm install && npm run dev   # http://localhost:5173
npm run build                      # mesti berjaya sebelum commit
```

## Peta kod
- `backend/app/models.py` jadual · `migrate.py` ALTER TABLE ADD COLUMN ringan (tiada Alembic) · `seed.py` data asas + `upgrade_v7` (sekali) · `config.py` semua env/lalai.
- `services/assign.py` algoritma susunan kenderaan (fungsi tulen, mudah diuji) · `services/booking.py` logik bisnes utama (masa, bayaran, bayaran prebet, tick, penyata).
- `routes/` auth, member, bookings, driver, admin (peranan: member / driver=prebet / admin; bendahari = `is_treasurer`).
- `frontend/src/pages/` Admin.jsx + AdminExtra.jsx, Prebet.jsx, Home.jsx, Bayaran.jsx, Driver.jsx, Auth.jsx, Setup.jsx (profil), Landing.jsx.
- `backend/tests/` test_assign.py (algoritma), test_flow.py (aliran penuh API).

## Keadaan terkini (1 Nov 2026) — baca juga `docs/PEMBETULAN.md`
- **Aliran masa:** ahli tutup tempahan 5:00 PM; admin sahkan senarai, atau auto-sah 7:00 PM (`AUTO_FINALISE_TIME`). Bank/QR dan bayaran ahli hanya dibuka selepas disahkan; bendahari bayar prebet hanya untuk latihan disahkan. Admin boleh edit selepas sah dan "Batalkan pengesahan" (`auto_off`).
- **E-hailing:** trip e-hailing (tiada kenderaan) TIDAK dikenakan yuran; ahli bayar e-hailing sendiri. `_confirmed_trips` mengecualikannya; `refresh_fees`/`set_ehailing`/`auto_ehailing` memanggil `_sync_payment`. Bayaran `void` tidak dipaparkan kepada ahli. Kos e-hailing tidak direkod.
- **Bayaran:** `POST /admin/payments/{id}/verify` menerima `amount_paid`; kurang daripada due = 400; lebih = masuk `credit_balance` (digunakan automatik pada latihan seterusnya semasa pengesahan senarai). Admin dan bendahari sama-sama boleh sahkan resit.
- **Jantina:** pilihan ahli mengatasi senarai CSV; tukar selepas set perlu permohonan, diluluskan admin (Admin › Lagi). `vehicles.driver_gender` ialah salinan; panggil `svc.sync_driver_vehicles` bila jantina pemandu berubah.
- **Prebet:** ahli berkenderaan boleh mohon jadi prebet (`users.prebet_request`), admin lulus. Bayaran prebet: kadar tetap ikut kategori kenderaan (kereta dekat 10/jauh 14, motor 1/2), hanya admin ubah kadar.
- **Storan:** `services/retention.py` (harian 12:05 pagi) memadam gambar resit selesai dan notifikasi lebih `RETENTION_MONTHS` (6) bulan; rekod bayaran kekal. `imaging.compress` mengecilkan gambar semasa muat naik (pillow; QR/logo kekal PNG). Import batch lama (34 sesi) = maklumat orang sahaja (nama, sesi masuk, kursus/tahap, aktif/alumni, jawatan, jurulatih), bukan kehadiran harian. Istilah: sesi = tahun akademik 4 digit (2627), sama dengan batch; MT dan biro ikut sesi; aktif = pelajar UTM yang masih berlatih (3 atau 4 sesi serentak); alumni = bekas ahli silat gayung yang telah tamat; sekretariat (pembantu biro, tahun 1) masih dibincang.
- **Amaran (severity warning) tak boleh dipadam ahli:** mesti ada `ref` dan laluan `resolve_warning`, atau tamat tempoh dalam `retention.expire_stale_warnings`. Amaran baharu tanpa `ref` tak akan hilang: jangan buat.
- **Peranan manusia:** Admin/BKK pegang kutipan dan bayar prebet (QR milik admin); pembangun dan pentadbir sistem berasingan.
- **Keputusan 6 Nov 2026 (lihat docs/07-log-keputusan.md):** no. SG ke SSG, pengangkutan latihan rasmi hanya ahli di kolej UTM, aktiviti luar boleh mohon pickup tempat lain (dibina, PEMBETULAN 19), tema merah naga, akaun hosting di bawah emel persatuan.
- **Arah akan datang:** satu website PSSGUTM (transport = satu modul), rekod ahli tunggal (aktif/tidak aktif/alumni + batch), jawatan dan biro dalam pangkalan data (boleh diubah admin), kehadiran, simpanan barang. Sambung daripada kod sedia ada; jangan mula baru.
- **UI:** kad notifikasi di Utama hanya untuk amaran (loceng ada semua); tema ikut akaun (`users.theme`); motor dilabel "Motor".
- **Peringatan:** semua perubahan ini belum disahkan oleh `pytest` dalam sandbox AI; jalankan dan betulkan dahulu.

## Peraturan kerja (JANGAN langgar)
1. Satu perubahan = satu branch = `pytest` + `npm run build` lulus sebelum merge ke `main`.
2. Tambah lajur DB? Tambah di `models.py` DAN `migrate.py` (Render tidak jalankan Alembic). Jangan pernah DROP data produksi.
3. Peraturan bisnes di `docs/02-peraturan-bisnes.md` ialah keputusan BKK. Jangan "baiki" tanpa tanya. Jika ubah, kemas kini dokumen + `docs/07-log-keputusan.md`.
4. Nilai boleh ubah (yuran, bayaran prebet, masa) ada lalai dalam `config.py`, tetapi nilai sebenar disimpan dalam jadual `settings` dan diubah admin dalam app.
5. Satu worker sahaja (scheduler dalam proses). Jangan tambah `--workers`.
6. Jangan commit `.env`, senarai ahli, `uploads/`, kunci API. Repo mesti PRIVATE.
7. Teks UI dalam BM ringkas; kontras warna ≥ 4.5:1 cerah & gelap; guna pembolehubah CSS, bukan warna tetap.
8. Waktu guna `now_my()`/zon Malaysia, bukan `datetime.now()` mentah.
9. `ENFORCE_CUTOFF=false` hanya untuk ujian.
9a. **`seed.py` jalan setiap deploy** (Start Command Render: `python -m app.seed && uvicorn ...`). Ia MESTI idempotent: semak wujud atau guna `db.merge`, jangan `db.add` kunci tetap (pernah menyebabkan `settings_pkey` duplicate dan server tak mula).
9b. Sandaran admin (`GET /admin/export`) tidak boleh memasukkan kata laluan, fail gambar atau no. akaun bank penuh.
9c. Data peribadi: jangan log atau papar telefon/emel/akaun bank kepada peranan yang tidak perlu.
10. Selepas siap kerja: ringkaskan apa diubah, fail terlibat, dan cara uji.

## Pengesahan tidak dibuat dalam sandbox AI sebelum ini
`test_flow.py` pernah tidak dapat dijalankan dalam persekitaran tanpa pakej. Jalankan penuh dan betulkan jika ada kegagalan.

## Modul utama PSSGUTM (2026-11-08)
Kod: `backend/app/models_main.py`, `routes/persatuan.py`, `services/people.py`; frontend `pages/Persatuan.jsx`, `pages/Hadir.jsx`. Setup akaun persatuan: `docs/08-setup-baharu-akaun-persatuan.md`. Ujian logik: `tests/test_people.py`.
