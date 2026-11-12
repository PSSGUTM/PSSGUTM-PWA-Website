# 08 · Pembetulan & tambahan (31 Okt 2026)

Bahagian ini mengatasi mana-mana kenyataan bercanggah dalam bahagian 1–7. Ia dimasukkan ke dalam dokumen asal pada kemas kini seterusnya.

## 1. Masa pengesahan senarai
- BKK boleh sahkan senarai kenderaan **dari 5:00 PM** hari latihan. Jika BKK tak sahkan, sistem susun dan sahkan automatik pada **7:00 PM** (bukan 7:30 PM seperti dalam bahagian 2, 5 dan Gemini). Tetapan: `AUTO_FINALISE_TIME`.

## 2. Bayaran hanya selepas senarai disahkan
- **Ahli** hanya boleh bayar selepas senarai disahkan. Sebelum itu butang upload resit tidak aktif dan **maklumat bank + QR persatuan disembunyikan** (server tidak menghantarnya). Ahli nampak mesej "jangan bayar dahulu".
- **Bendahari** hanya boleh bayar prebet bagi latihan yang telah disahkan.
- Selepas disahkan, jumlah dipaparkan jelas: ahli nampak kotak "Perlu bayar RMx"; admin nampak "Ahli perlu bayar" dan "Bendahari perlu bayar prebet" pada kad latihan; bendahari nampak jumlah ikut latihan dan jumlah keseluruhan prebet.

## 3. Admin selepas pengesahan
- Admin masih boleh edit selepas disahkan (termasuk selepas auto-sah): tukar tempat duduk, susun semula, tambah/buang ahli.
- Butang **"↩️ Batalkan pengesahan"**: bayaran ditutup semula, kredit yang sempat digunakan dipulangkan, ahli dimaklumkan jangan bayar dahulu, dan **auto-sah dimatikan untuk latihan itu** (admin sahkan sendiri bila siap). Resit ahli yang sudah masuk kekal.
- **Tidak boleh dibatalkan** jika bayaran prebet untuk tarikh itu sudah dibuat.

## 4. Jantina ahli
- Pilihan ahli semasa daftar didahulukan berbanding CSV (CSV kadang tersalah). Jika berbeza, senarai ahli sah dalam sistem dikemas kini dan **admin dimaklumkan** supaya CSV sumber dibetulkan.
- Tukar jantina kemudian: ahli mohon di Profil (**Tersilap? Mohon tukar**); **perlu kelulusan BKK** (Admin › Lagi). Bila diluluskan, senarai ahli sah dikemas kini, tempat duduk disusun semula dan admin lain dimaklumkan. Admin juga boleh tukar terus.

## 5. Jantina prebet dan kenderaan
- Jantina setiap kenderaan sentiasa sama dengan jantina akaun pemandunya (menentukan susunan tempat duduk dan peraturan prebet perempuan hanya bawa penumpang perempuan).
- Bila jantina pemandu berubah, semua kenderaannya dikemas kini automatik dan latihan terbuka yang akan datang disusun semula. Data lama diselaraskan sekali semasa deploy (`seed_v8`).
- Latihan yang sudah disahkan tidak disusun semula sendiri: Batalkan pengesahan, Susun kereta, kemudian sahkan semula.
- Import CSV ahli tidak mengubah akaun yang sudah berdaftar. Jantina akaun ditukar oleh ahli (permohonan) dan diluluskan BKK di Admin › Lagi.

## 6. Masalah biasa (tambahan)
| Gejala | Punca | Penyelesaian |
|---|---|---|
| Ahli kata dah bayar sebelum disahkan | Bank/QR dahulu dipaparkan awal | Kini disembunyikan sehingga disahkan; semak resit mereka |
| Latihan tak auto-sah | Admin pernah "Batalkan pengesahan" (auto-sah dimatikan untuk latihan itu) | Sahkan sendiri |
| Notifikasi "Jantina ahli berubah" | Ahli pilih/tukar jantina berbeza daripada CSV | Betulkan CSV sumber BKK |
| Kenderaan prebet masih lelaki walaupun akaun perempuan | Data lama sebelum pembetulan | Ahli mohon tukar jantina di Profil, BKK lulus di Admin › Lagi; kenderaan dikemas kini automatik |

## 7. Rujukan teknikal
- `vehicles.driver_gender` ialah salinan `users.gender` pemandu; kod yang menukar jantina pemandu mesti memanggil `svc.sync_driver_vehicles`.
- Maklumat bank/QR hanya dihantar kepada ahli jika `svc.user_can_pay_any`; bayaran prebet hanya untuk latihan `finalised`.
- Lajur baharu (ditambah automatik): `training_events.auto_off`, `users.gender_request`, `users.theme`, `bookings.cancelled_by_event`.

## 8. Antara muka dan peranan (update 5)
- **Kad notifikasi di laman Utama** hanya untuk **amaran**. Semua notifikasi lain boleh dilihat di ikon loceng. Setiap notifikasi menunjukkan tarikh ia dikeluarkan.
- **Ahli yang ada kenderaan boleh mohon jadi prebet** di Profil. BKK lulus atau tolak di Admin › Lagi. Selepas lulus: peranan prebet, ahli masih boleh menempah sebagai penumpang; perlu muat naik lesen dan daftar kenderaan.
- **Label kenderaan**: motosikal dipaparkan sebagai "Motor", kereta sebagai "Kereta" (peta kerusi, kad kenderaan, notifikasi).

## 9. E-hailing: tiada yuran persatuan (update 6)
- Trip yang ditanda **e-hailing** (tiada kenderaan prebet) **tidak dikenakan yuran persatuan**. Ahli tempah dan bayar e-hailing sendiri; BKK menyusun dan mencadangkan mereka bergerak bersama.
- Jika ahli sudah bayar kemudian ditanda e-hailing, bayaran dibawa sebagai kredit ke latihan seterusnya. Jika e-hailing dibatalkan atau ahli dapat kenderaan, yuran dikenakan semula.
- Jika satu arah e-hailing dan arah lagi prebet, yuran masih dikenakan (ada trip prebet).
- Angka "Ahli perlu bayar" pada kad latihan tidak lagi mengira ahli e-hailing. Bayaran yang dibatalkan tidak dipaparkan kepada ahli.
- Kos e-hailing tidak direkod dalam sistem dan tidak masuk penyata untung rugi.

## 10. Lebihan bayaran jadi kredit & mesej e-hailing (update 8)
- Semasa **Sahkan** resit (Admin › Bayaran, oleh admin atau bendahari), sistem tanya **jumlah sebenar pada resit**. Jika lebih daripada yang perlu dibayar, **lebihan disimpan sebagai kredit** ahli dan ditolak automatik daripada latihan seterusnya (semasa senarai disahkan). Ahli dimaklumkan dalam loceng.
- Jika jumlah pada resit **kurang** daripada yang perlu, pengesahan ditolak sistem: tolak resit atau masukkan jumlah betul.
- Tiada pemulangan tunai; kredit hanya digunakan untuk latihan seterusnya yang ahli tempah dan mendapat kenderaan.
- Dalam kad e-hailing (Admin › Penumpang), butang **📋 Salin mesej WhatsApp** menyalin senarai ahli e-hailing (nama dan kolej, ikut arah pergi/balik) untuk dihebah di group.

## 11. Pembersihan data dan pemampatan gambar (update 9)
- **Resit lama:** gambar resit bayaran ahli (status Dah bayar atau dibatalkan) dan resit bayaran prebet yang lebih **6 bulan** dipadam setiap hari. Rekod bayaran (jumlah, tarikh, status) **kekal**.
- **Notifikasi lama:** notifikasi lebih 6 bulan dipadam; amaran yang masih aktif tidak dipadam.
- **Tetapan:** `RETENTION_MONTHS` (lalai 6, 0 = tutup) di Render. Fail kod: `backend/app/services/retention.py`.
- **Gambar dikecilkan** semasa muat naik (maks 1600 px, JPEG kualiti 80): resit, lesen, insurans. QR dan logo kekal PNG. Jika pemampatan gagal, fail asal disimpan. Fail kod: `backend/app/imaging.py`; pakej baharu `pillow` dalam `requirements.txt`.
- **Istilah:** *sesi* = tahun akademik, ditulis 4 digit (2425 = 2024/25), dan juga dipanggil *batch*. Sesi masuk ahli ialah batchnya; MT (Majlis Tertinggi) dan biro juga ikut sesi (contoh 2627). *Aktif* = pelajar UTM yang masih berlatih (biasanya 3 atau 4 sesi serentak); *alumni* = bekas ahli silat gayung yang sudah tamat pengajian (diploma, ijazah, master). *Jurulatih (cikgu)* = dari luar atau alumni sesi lepas. Pengurusan biasanya pelajar tahun 2 hingga 4; *sekretariat* (pembantu biro, biasanya tahun 1) masih dibincangkan.
- **Dasar import batch lama (34 sesi):** hanya maklumat orang: nama, sesi masuk, kursus dan tahap, status (aktif atau alumni), jawatan pernah dipegang, dan jurulatih. Kehadiran harian batch lama tidak diimport.
- **Sandaran bulanan** dan **semakan Supabase** setiap 2–3 bulan: lihat dokumen 05.
- Peranan: pentadbir sistem (urus data, jawatan, tetapan) dan pembangun (kod, pelayan, akaun teknikal) ialah dua tugas berasingan. Admin/BKK memegang kutipan dan bayar prebet sesi 2026/2027; QR bank ialah milik admin.


## 12. Amaran yang tidak hilang (update 11)
- **Senarai ditarik balik:** amaran "Senarai … ditarik balik, jangan bayar dahulu" kini dibuang daripada semua ahli bila senarai disahkan semula (admin atau auto 7 PM) atau latihan dibatalkan. Sebelum ini ia kekal kerana tiada penanda.
- **Amaran lapuk dibuang sendiri** setiap hari 12:05 pagi: belum tanda sampai/hantar (selepas 2 hari); senarai ditarik balik, prebet belum sahkan, perempuan seorang diri, dan "boleh bawa?" (selepas tarikh latihan berlalu).
- Amaran lain hilang bila perkara berkenaan selesai: lesen dikemas kini, prebet tanda atau sahkan, bayaran direkod, prebet tekan Diterima, tunggakan dilangsaikan.
- Fail kod: `services/booking.py` (`_clear_unfinalised`), `services/retention.py` (`expire_stale_warnings`).
- **Pembersihan sekali jalan (`seed_v9`, jalan automatik semasa deploy):** amaran lama "ditarik balik" yang sudah tersangkut pada ahli dibuang, kecuali untuk latihan yang senarainya memang masih ditarik balik.

## 13. Senarai Pengguna: blok, checkpoint, tapis dan susun (update 13)
- Admin › Lagi › Pengguna kini memaparkan **blok** dan **checkpoint** setiap ahli, carian merangkumi blok, dan ada **tapisan kolej** serta **susun ikut kolej dan blok** (bilangan orang dipaparkan). Fail: `routes/admin.py` (`GET /admin/users` tambah `checkpoint`), `pages/Admin.jsx`.

## 14. Amaran boleh dipadam pada tarikh latihan seterusnya

- Amaran (⚠️) tetap hilang sendiri bila kerja selesai.
- Pengguna juga boleh padam amaran, tetapi hanya bila tarikh latihan **seterusnya** selepas tarikh amaran itu sudah tiba. Cth amaran latihan Rabu: boleh dipadam pada Sabtu; amaran Sabtu: boleh dipadam pada Rabu berikutnya.
- Tarikh rujukan: `training_date` amaran, jika tiada guna tarikh amaran dicipta (waktu Malaysia). Tarikh latihan ikut sesi aktif (termasuk aktiviti sekali sahaja).
- Sebelum tarikh itu, ikon 🔒 dan teks "boleh dipadam [hari, tarikh]" dipaparkan; cubaan padam terus ditolak oleh server (400).
- Kod: `warning_unlock_date` / `warning_deletable` dalam `services/booking.py`; `routes/bookings.py` (GET/DELETE `/notifications`); `components/Notifications.jsx`.

## 15. Kadar bayaran prebet ikut penumpang, bukan kolej prebet

- Kategori bayaran (dekat/jauh) ditentukan oleh **kolej penumpang** dalam kenderaan itu hari tersebut, bukan kolej prebet.
- Jika ada seorang atau lebih penumpang kolej jauh dalam kereta/motosikal = kadar jauh; jika semua dekat = kadar dekat. Sama untuk kereta dan motosikal.
- Kod: `payout_category` dalam `services/booking.py`, digunakan di senarai bayaran prebet. Yuran penumpang sedia ada sudah ikut kolej penumpang (tak berubah).

## 16. Kotak tarikh lepas kekal sehingga latihan seterusnya

- Kotak tarikh (tab Utama ahli, tab Utama prebet) tidak lagi hilang sebaik tarikh/sesi tamat. Ia kekal sehingga hari latihan seterusnya tiba. Cth kotak Sabtu kekal hingga Rabu; kotak Rabu kekal hingga Sabtu.
- Kotak yang sudah lepas diberi tanda `past` (prebet: "sudah lepas" pada tajuk). Ia tidak dikira untuk "tugasan seterusnya" dan "sahkan N tarikh". Ahli masih boleh bayar atau muat naik resit; prebet masih boleh tanda "dah hantar" selepas tengah malam.
- Admin (Ringkasan, Penumpang) tidak berubah: masih hari ini dan seterusnya sahaja.
- Kod: `last_session_date`, `prebet_dates(keep_recent=True)` dalam `services/booking.py`; `routes/bookings.py` (GET `/bookings`); `Home.jsx`, `Prebet.jsx`.

## 17. Tema merah malap, logo bulat berukir

- Dipilih: "merah naga" (`#a8322a`). Tema lalai bertukar daripada hijau kepada merah malap (utama `#a8322a`, butang/aksen emas `#d4a94e`). Mod gelap pun diubah ke nada hangat. Diubah dalam `styles.css`, `index.html`, `manifest.webmanifest` dan `BRAND_DEFAULTS` (`routes/bookings.py`).
- Warna jenama yang admin simpan dalam Admin › Lagi › Jenama mengatasi nilai lalai. `seed_v10` (sekali sahaja) membuang warna tersimpan hanya jika ia masih hijau/emas lama, supaya tema baharu terpakai. Warna pilihan admin sendiri tidak disentuh.
- Halaman pembuka (sebelum login): logo bulat dengan gelang ukiran emas (tumpal batik, awan larat, titik) yang berputar perlahan, dan corak sisik naga di bahagian bawah. Menghormati tetapan "kurangkan gerakan" peranti.
- Semua logo (`BrandMark`) kini dipaparkan bulat. Logo upload yang tidak segi empat sama dipotong di tengah (object-fit cover), jadi guna imej hampir petak untuk hasil terbaik.
- Kod: `components/Emblem.jsx` (`BrandMark`, `OrnateMark`), `pages/Landing.jsx`, `styles.css`.

## 18. Ikon app dan skrin pembuka telefon (splash)

- Skrin yang keluar sebaik app ditekan di telefon dijana oleh Android daripada `background_color` dan ikon dalam `manifest.webmanifest`. Ia tidak boleh dianimasikan atau diubah melalui kod halaman.
- `icon-512-maskable.png` dan `apple-touch-icon.png` kini: latar merah malap + logo bulat dengan gelang ukiran emas (dalam zon selamat 80%). Latar splash merah (`background_color` sudah ditukar dalam bahagian 17).
- Telefon yang sudah pasang app menyimpan ikon dan manifest lama. Kemas kini automatik boleh ambil masa; untuk serta-merta, buang app dan pasang semula dari pelayar.
- Butang "Set semula warna ke lalai" (Admin › Lagi › Branding) memadam warna utama dan butang yang tersimpan supaya lalai kod digunakan (`POST /admin/branding/reset-colours`). Nama app dan maklumat lain tak berubah.

## 19. Aktiviti luar: tempat pergi, tempat balik dan pembundaran yuran

- Semua ahli (termasuk tinggal luar kampus dan alumni berlatih semula sebagai ahli) boleh mohon pengangkutan untuk **aktiviti luar**. Latihan rasmi Rabu/Sabtu tak berubah: hanya pelajar di kolej UTM yang ada perkhidmatan. Prebet naik sebagai penumpang melalui permohonan kepada admin BKK (peraturan sedia ada).
- **Dua tempat:** setiap aktiviti ada tempat **pergi** (ambil) dan tempat **balik** (hantar). Kalau ahli pilih kolej, ia dihantar balik ke kolej. Setiap tempahan (pergi atau balik) menyimpan tempatnya sendiri.
- **Admin tetapkan tempat** (Admin › Lagi › Aktiviti, butang "Tempat"): tempat **pergi tetap** dan/atau tempat **balik tetap** (atau "balik = pergi"), kosong = ahli pilih sendiri. Arah yang tetap wajib diikut semua ahli dan tempahan sedia ada ditukar; arah yang kosong dipilih ahli (lalai: kolej atau tempat lain; boleh dihadkan kepada `rumah` atau `kolej` sahaja). Pergi tetap dengan balik pilihan ahli (atau sebaliknya) dibenarkan.
- **Ahli** (pemilih tarikh dalam Tetapan): pilih "Kolej saya" atau "Tempat lain" (taip nama) untuk pergi, dan tanda "Hantar balik ke tempat yang sama" atau pilih tempat balik berasingan. Pilihan sedia ada kekal bila ahli hanya menukar pergi atau balik. Ahli tanpa kolej dalam senarai hanya ada "Tempat lain".
- **Admin tukar seorang ahli** (Admin › Penumpang, pada tarikh aktiviti: "Tukar tempat pergi/balik" pada setiap baris; kosong = kembali ke checkpoint kolej ahli). Ahli dimaklumkan dalam app.
- **Yuran** kekal sama untuk semua dan kini **dibundar ke atas ke ringgit penuh** (cth RM41 ÷ 4 kerusi = RM10.25 jadi RM11; motosikal RM3.40 jadi RM4). Bayaran kepada prebet kekal harga penuh kenderaan yang admin tetapkan, jadi lebihan bundaran kekal pada persatuan.
- **Susunan kereta:** yang diambil dari kolej mengikut keutamaan sedia ada (kolej sama, kategori dekat/jauh); yang diambil dari tempat lain neutral dan dikumpul ikut nama tempat pergi yang sama.
- Prebet nampak "Pergi: X · Balik: Y" bila kedua-duanya berbeza.
- Data: lajur baharu `bookings.pickup_place`, `training_sessions.pickup_mode`, `gather_place`, `return_place` (ditambah automatik oleh `run_migrations`). Eksport CSV tempahan menunjukkan tempat lain jika ada.
- Kod: `services/booking.py` (`resolve_activity_pickup`, `fixed_place`, `_pickup_info`, `admin_set_member_pickup`, `admin_set_activity_pickup`, `book_date`, `activity_price`), `routes/admin.py`, `routes/member.py`, `components/DatePicker.jsx`, `pages/Admin.jsx`, `pages/Prebet.jsx`.
- **Penanggung yuran:** lalai ahli bayar kepada BKK dan BKK bayar prebet. Admin boleh pilih "Persatuan tanggung" (semasa tambah aktiviti, atau butang "Persatuan tanggung"/"Ahli bayar" pada senarai): ahli tak ada bayaran (diberitahu "ditanggung persatuan"), bayaran kepada prebet kekal harga penuh kenderaan, dan Admin › Aktiviti menunjukkan jumlah yang persatuan perlu serah kepada BKK (dikira selepas senarai disahkan) dengan penanda "sudah diserah". Jika admin tukar kepada persatuan selepas ahli sudah bayar, bayaran itu dibawa sebagai kredit (tidak hilang); resit "menunggu semakan" menjadi kredit bila admin sahkan. Bila ditukar semula kepada ahli bayar dan senarai sudah disahkan, kredit digunakan semula pada bayaran baharu. Data: `training_sessions.fee_by_assoc`, `assoc_settled`, `return_same`.
