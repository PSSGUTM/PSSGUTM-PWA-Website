# 06 · Membangun & menyelenggara dengan AI

## Sejarah & Peralihan Alat AI
Pada peringkat awal permulaan projek ini, pembangun menggunakan **Claude Code** (dan Claude chat) untuk menjana struktur awal kod, peraturan bisnes dan ujian. 

Walau bagaimanapun, untuk mengelakkan beban kewangan persatuan (mengelak kos langganan berbayar) dan memaksimumkan integrasi, **selepas menggunakan Claude kami telah berpindah sepenuhnya kepada Google Antigravity untuk pengaturcaraan dan pembangunan AI (*coding AI*)**. Antigravity kini bertindak sebagai ejen utama untuk memahami repo, mengubah kod, menyemak ralat dan mengesahkan ujian automatik.

---

## Peranan Pembantu AI
| Pembantu | Status | Terbaik untuk | Elak |
|---|---|---|---|
| **Google Antigravity** | **Ejen Utama (Aktif)** | Ubah **kod**, tambah ciri, analisa dan baiki ralat, jalankan ujian automasi (`pytest`, `npm run build`), pengurusan fail projek secara terus | Membiarkan perubahan peraturan bisnes dibuat tanpa perbincangan BKK |
| **Claude Code / Claude** | **Legasi (Asal)** | Fasa reka bentuk dan binaan awal projek | Langganan berbayar berulang bagi persatuan |
| **Gemini** | **Sokongan** | **Panduan setup** langkah demi langkah (Render, Vercel, Supabase, Brevo, Google, OAuth) sambil lihat skrin atau panduan dokumentasi | Jangan ubah kod produksi tanpa semakan; jangan tampal maklumat sensitif |

---

## Cara 1 — Google Antigravity (Kaedah Utama & Disyorkan)
Antigravity membaca keseluruhan repositori projek secara automatik, menganalisis hubungan fail, mengedit fail secara langsung, serta mengesahkan integriti kod dengan menjalankan `pytest` dan `npm run build`.

### Persediaan:
1. Buka folder repo projek dalam Antigravity / persekitaran kerja.
2. Fail konteks **`CLAUDE.md`** / **`ANTIGRAVITY.md`** di akar repo mengandungi arahan asas seni bina, aliran perkhidmatan, dan peraturan bisnes yang perlu dipatuhi.
3. Berikan arahan ringkas dan jelas kepada Antigravity menggunakan templat di bawah.

### Templat Prompt untuk Antigravity (Salin & Ubah)
**Ciri baharu**
> Baca CLAUDE.md dan docs/02-peraturan-bisnes.md. Saya nak [terangkan hasil yang dikehendaki dalam 1–3 ayat]. Sila ubah backend + frontend yang berkaitan, tambah ujian jika perlu, dan jalankan `pytest` serta `npm run build`. Beritahu fail yang diubah dan cara saya uji hasilnya. Jika ia menukar peraturan bisnes, kemas kini docs/02 dan docs/07.

**Membaiki Bug / Ralat**
> Ralat: [apa yang berlaku], di skrin [nama komponen/halaman], sepatutnya [tingkah laku yang betul]. Langkah ulang: [1, 2, 3]. Cari punca masalah, betulkan ralat, dan pastikan ujian lulus. Jangan ubah bahagian lain yang tiada kaitan.

**Semakan Kod & Integriti**
> Semak perubahan terkini kod ini. Periksa sama ada terdapat bug, kesan terhadap skema pangkalan data (`migrate.py`), pelanggaran logik peraturan bisnes (`docs/02-peraturan-bisnes.md`), atau ujian yang belum lengkap.

**Pertanyaan Mengenai Kod**
> Terangkan bagaimana fungsi/ciri [nama fungsi] berfungsi, rujuk fail dan komponen yang terlibat. Jangan buat sebarang perubahan kod.

---

## Cara 2 — Claude Code / Claude Chat (Kaedah Legasi)
Jika masih menggunakan Claude Code atau Claude Web, lampirkan fail `CLAUDE.md` dan `docs/02-peraturan-bisnes.md` bagi setiap perbualan baharu untuk memberi konteks awal projek. Minta kod dalam format *diff* atau fail penuh yang spesifik bagi fail besar seperti `services/booking.py`.

---

## Cara 3 — Gemini sebagai Pembantu Konfigurasi & Integrasi
Rujuk [gemini/GEMINI_CONTEXT.md](gemini/GEMINI_CONTEXT.md): fail konteks khusus untuk dirujuk kepada Gemini. Gemini sangat berguna untuk panduan antara muka luar ("di mana butang perlu ditekan pada papan pemuka Supabase / Render / Vercel") dan penyelesaian integrasi perkhidmatan pihak ketiga.

---

## Keselamatan Semasa Menggunakan AI
- **Jangan sesekali mendedahkan kunci rahsia:** Jangan tampal `SECRET_KEY`, `SUPABASE_SERVICE_KEY`, `BREVO_API_KEY`, kata laluan, atau senarai data peribadi ahli sebenar ke dalam prompt umum.
- **Semak perubahan penting:** Beri perhatian rapi pada perubahan di `migrate.py`, `security.py`, dan `routes/admin.py`.
- **Integriti data produksi:** Jangan sesekali jalankan arahan yang memadam data produksi (`DROP TABLE` atau penghapusan storan tanpa sandaran).
- **Peraturan bisnes adalah hak BKK:** Keputusan operasi pengangkutan dan persatuan adalah muktamad mengikut mesyuarat pengurusan BKK; AI tidak boleh mengubah polisi sesuka hati.
