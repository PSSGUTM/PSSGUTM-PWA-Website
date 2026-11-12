# 08 · Setup PSSGUTM baharu di bawah akaun persatuan (pssgutm@)

Semua akaun di bawah **satu emel: pssgutm@gmail.com**. Hidupkan pengesahan 2 langkah pada emel itu dan simpan kod pemulihan dengan sekurang-kurangnya dua pegawai. Item 🔎 mungkin berbeza sedikit dalam dashboard semasa.

## Urutan (jangan langkau)
1. **GitHub**: log masuk sebagai pssgutm@ › repo **PRIVATE** `pssgutm`. Sebelum push, jalankan pemeriksaan rahsia (di bawah). Push kandungan folder ini.
2. **Supabase**: projek baharu (region Singapore) › simpan kata laluan DB › cipta bucket **`uploads`** (private) › salin `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (lihat 04 Langkah 1).
3. **Render**: Web Service dari repo (Root `backend`). Build: `pip install -r requirements.txt -r requirements-postgres.txt`. Start: `python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`. Env seperti dalam 04. `SECRET_KEY` baharu.
4. **Vercel**: Root `frontend`, env `VITE_API_URL` = URL Render. Deploy.
5. Kembali ke Render: `CORS_ORIGINS` dan `FRONTEND_URL` = URL Vercel. Redeploy.
6. **GitHub Secret** `BACKEND_URL` untuk keepalive (04 Langkah 2).
7. Log masuk admin (`ADMIN_EMAIL`/`ADMIN_PASSWORD`). Semak `/health` dan log Render tiada ralat.
8. **Google OAuth** (04 Langkah 6) dan **emel Brevo** (04 Langkah 5), kemudian isi `GOOGLE_CLIENT_ID`, `BREVO_API_KEY`, `MAIL_FROM`.

## Bawa data lama (pilihan, jika mahu sejarah transport)
Buat **selepas** langkah 7 (jadual sudah wujud). Perlukan PostgreSQL client (`pg_dump`, `psql`) pada komputer.
1. Render baharu: **Suspend** perkhidmatan supaya tiada tulis semasa pindah.
2. `pg_dump --data-only --no-owner --disable-triggers "<DATABASE_URL LAMA>" > data-lama.sql`
3. Kosongkan data awal dalam DB baharu: `psql "<DATABASE_URL BARU>" -c "TRUNCATE <semua jadual> RESTART IDENTITY CASCADE;"` (senarai jadual: `\dt` dalam psql).
4. `psql "<DATABASE_URL BARU>" -f data-lama.sql`
5. **Resume** Render. Seed idempotent akan tambah biro asas jika tiada.
6. Fail resit/gambar dalam bucket lama tidak ikut: salin melalui dashboard Supabase jika perlu (resit disimpan 6 bulan sahaja).
Simpan `data-lama.sql` di tempat selamat (mengandungi data peribadi) dan padam selepas sahih.

## Pemeriksaan rahsia sebelum push
Dalam folder projek: `git grep -nI -E "(SECRET|KEY|PASSWORD|TOKEN)\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}"` dan semak `.env` tidak dalam `git status`. `.env.example` mesti hanya nilai contoh.

## Selepas hidup: isi data
1. Admin › **Persatuan › Bengkung**: isi atau import senarai bengkung (bawah ke atas).
2. **Persatuan › Import**: muat naik `format-import-PSSGUTM.xlsx` yang sudah diisi (Semak dahulu, kemudian Import).
3. **Persatuan › Biro**: semak biro, tetapkan kebenaran Kehadiran (BLG) dan Inventori, tambah seki.
4. Ahli log masuk dengan **Google** guna emel yang ada dalam senarai: akaun dicipta sendiri.
