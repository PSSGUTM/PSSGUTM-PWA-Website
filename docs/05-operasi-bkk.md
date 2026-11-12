# 05 · Operasi BKK (Operations & handover)

## Rutin setiap latihan (Rabu & Sabtu)
| Bila | Siapa | Buat |
|---|---|---|
| 1–2 hari sebelum | Admin | Tetapkan **tempat latihan**. Semak ada prebet sahkan "boleh bawa"; hubungi prebet yang belum |
| Hari latihan, sebelum 5 PTG | Ahli/Prebet | Tempah / sahkan. Admin pantau Ringkasan (kereta cukup? ada e-hailing?) |
| Selepas 5 PTG | Admin | Hanya admin tambah/buang ahli. Semak amaran |
| 7:30 PM | Sistem/Admin | Senarai disahkan (auto jika admin belum). Semak e-hailing dan tempah manual |
| Selepas latihan | Prebet | Tanda "dah hantar semua" |
| Esoknya sebelum 12 TGH | Ahli | Bayar + muat naik resit |
| Selepas 12 TGH | Bendahari | Sahkan resit; tunggakan (Bayaran › Tunggakan) |
| Mingguan/bulanan (ikut tetapan) | Bendahari | **Bayar prebet** per kad + resit |
| Bulanan | Admin | Set **admin bertugas** bulan depan; semak Untung/rugi; **muat turun sandaran** (Admin › Lagi) ke Drive BKK |

## Awal sesi baharu (setiap tahun) — checklist serah tugas
**Akaun & akses (buat dahulu, sebelum BKK lama keluar)**
- [ ] Senarai akaun milik persatuan (GitHub, Supabase, Render, Vercel, Brevo, Google Cloud) ada pada emel/pengurus kata laluan BKK. Tambah **BKK baharu sebagai owner/collaborator** pada setiap satu, kemudian buang BKK lama.
- [ ] Tukar `ADMIN_PASSWORD` / kata laluan admin dalam app; cipta akaun admin untuk setiap ahli BKK baharu (Admin › Penumpang › tukar peranan).
- [ ] Kemas kini hubungan pentadbir laman web (`SITE_CONTACT_PHONE`, `SITE_CONTACT_NAME` di Render) kepada orang yang menyelenggara sekarang.
- [ ] Tukar kunci jika ada yang tersebar: `SECRET_KEY` (semua log keluar), Supabase service key, Brevo key.

**Data**
- [ ] Muat turun **sandaran** (Admin › Lagi) dan sandaran DB/bucket penuh sesi lama sebelum mengosongkan apa-apa.
- [ ] Import **senarai ahli sah** baharu (CSV) di Admin › Lagi › Senarai ahli sah. Tukar `MEMBER_NO_PATTERN` jika format berubah.
- [ ] Padam akaun lama: Render `ALLOW_RESET=true` › Admin › Lagi › **Reset data ujian** › (pastikan tahu apa dipadam) › `ALLOW_RESET=false`.
- [ ] Semak kelayakan sesi (Admin › Lagi › Kelayakan), kolej, **checkpoint** (tambah KP jika belum), tempat latihan, jadual sesi (hari/masa), cuti kampus.
- [ ] Kemas kini QR/bank persatuan (Admin › Bayaran › maklumat bayaran) dan **bendahari baharu** dilantik.
- [ ] Semak yuran & **bayaran prebet** (Admin › Lagi › Harga) dan kaedah bayar prebet.
- [ ] Kemas kini nama/logo/warna (Branding) dan teks Syarat.

**Pengetahuan**
- [ ] BKK baharu baca `docs/01`–`03`. Pembangun baharu baca `CLAUDE.md` + `docs/06`.
- [ ] Mesyuarat BKK: semak semula peraturan dalam `docs/02`; catat perubahan di `docs/07`.

## Storan dan sandaran (setiap bulan)
- **Sandaran:** Admin › Lagi › Sandaran, muat turun zip dan simpan dalam fail BKK (di luar Supabase). Buat sekali sebulan; orang yang bertanggungjawab dicatat dalam senarai serah tugas.
- **Semak Supabase** setiap 2–3 bulan (Dashboard › Usage): Database (had 500 MB), Storage (had 1 GB), Egress (had 5 GB sebulan). Storan ialah yang paling cepat penuh.
- **Pembersihan automatik** (setiap hari, 12:05 pagi): gambar resit yang sudah disahkan atau dibatalkan dan lebih 6 bulan dipadam; notifikasi lebih 6 bulan dipadam (amaran aktif dikecualikan). **Rekod bayaran kekal**; hanya gambar resit hilang. Ubah tempoh dengan `RETENTION_MONTHS` di Render (0 = matikan).
- Semua gambar (resit, lesen) dikecilkan semasa muat naik (maks 1600 px, kualiti JPEG 80). QR dan logo kekal PNG.
- Import data batch lama (34 sesi): hanya maklumat orang (nama, sesi masuk, kursus dan tahap, status aktif/alumni, jawatan, jurulatih). Jangan import kehadiran harian batch lama.

## Pelan jika sistem rosak pada hari latihan
1. Semak `https://<backend>/health`. Jika lambat: Render sedang bangun (tunggu ≤ 1 minit).
2. Jika tetap down: lihat Render › Logs. Deploy terakhir bermasalah → *Rollback* ke deploy sebelumnya (Render dan Vercel simpan sejarah).
3. Sandaran manual: eksport senarai kenderaan dari Admin › Kerusi/Manifest (tangkap skrin) dan hebah di WhatsApp. Pengangkutan diteruskan; kemas kini app selepas pulih.

## Masalah biasa
| Gejala | Punca biasa | Penyelesaian |
|---|---|---|
| App lambat bila dibuka pertama | Render tidur | Semak GitHub Actions keepalive hijau; `BACKEND_URL` betul (tanpa `/health` dan `/` hujung) |
| Senarai tak disahkan auto 7:30 | Render tidur / scheduler tak jalan | Pastikan keepalive; sahkan manual |
| Resit/QR/logo hilang selepas deploy | `SUPABASE_*` tiada, fail di cakera Render | Isi `SUPABASE_URL`+`SUPABASE_SERVICE_KEY`, bucket `uploads` wujud |
| Semua pengguna tiba-tiba log keluar | `SECRET_KEY` bertukar | Normal; log masuk semula |
| "Lupa kata laluan" tiada emel | Brevo tak dikonfigurasi / sender belum disahkan | Semak `MAIL_FROM`, log Render "Brevo"; sementara itu admin beri kata laluan sementara |
| Butang Google tiada | `GOOGLE_CLIENT_ID` kosong / origin salah | Isi Client ID, tambah URL Vercel dalam Authorized origins |
| Ahli tak boleh daftar | No. ahli tiada dalam roster / format salah | Tambah di Senarai ahli sah |
| Ahli kolej KP tak boleh tempah | Belum ada checkpoint KP | Admin tambah checkpoint KP |
| Perempuan ditanda e-hailing | Peraturan perempuan-seorang dengan prebet lelaki | Tambah prebet perempuan/penumpang perempuan lain, atau tempah e-hailing |
| Bayaran prebet tidak muncul | Prebet tak beroperasi / tempoh belum tamat (mingguan/bulanan) / senarai belum disahkan | Semak kaedah bayar & tarikh |
| Deploy gagal, log: `IntegrityError ... duplicate key ... settings_pkey (eligible_years)` | Seed cuba INSERT tetapan yang sudah wujud (data lama / dua deploy bertindih) | Dibetulkan dalam `seed.py` (guna `merge` + tangkap `IntegrityError`). Jika berulang dengan jadual lain, pastikan seed idempotent: semak wujud dahulu sebelum tambah |
| Render: `Port scan timeout, no open ports detected` | Server tak sempat bind port kerana seed/migrasi ranap atau lambat (Start Command jalankan seed dahulu) | Baca log SEBELUM mesej ini; selalunya ada ralat seed. Betulkan, deploy semula |
| "Failed to fetch" pada satu skrin sahaja | Endpoint itu ranap (HTTP 500); pelayar papar sebagai "Failed to fetch" | Lihat Render › Logs pada masa yang sama untuk traceback (`NameError`, dsb.). Bukan masalah internet pengguna |
| Deploy gagal | Ralat build/test | Lihat log; `pytest` + `npm run build` setempat |
| Butang kelihatan kosong (warna sama dengan latar) | CSS: warna pautan menimpa warna butang | Semak kontras cerah & gelap (`styles.css`, bahagian "kontras"); guna `:not(.btn)` pada peraturan pautan |
| Perlu aktifkan semula latihan yang dibatalkan | Pengerusi putuskan diteruskan | Admin › Ringkasan › ♻️ Aktifkan semula (hanya selagi tarikh belum lepas) |
| Frontend tunjuk ralat rangkaian | `VITE_API_URL` salah / `CORS_ORIGINS` tak masuk URL Vercel | Betulkan, redeploy |

## Kontrak operasi dalaman
- Hanya 1–2 orang BKK dilantik **pentadbir laman web** (akses Render/Vercel/Supabase). Admin biasa hanya guna app.
- Jangan kongsi kata laluan di WhatsApp. Guna pengurus kata laluan.
- Setiap perubahan peraturan: catat di `docs/07` supaya BKK akan datang faham sebabnya.
