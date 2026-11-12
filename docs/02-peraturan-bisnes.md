# 02 · Peraturan bisnes (Business rules)

Ini keputusan BKK 2026/2027. **Jangan ubah kod tanpa putuskan di mesyuarat BKK dan catat di [07 Log keputusan](07-log-keputusan.md).**
Nilai bertanda ⚙️ boleh diubah dalam app oleh admin tanpa kod.

## 1. Siapa boleh guna
- Hanya no. ahli dalam senarai ahli sah (roster) boleh daftar. Format ahli: `SG` + 7 digit (`MEMBER_NO_PATTERN`). Prebet tak tertakluk format ini.
- Semua sesi/tahun layak (⚙️ Admin › Lagi › Kelayakan; `*` = semua).
- Semua 13 kolej dibuka. **KP** belum ada checkpoint: admin mesti tambah dahulu, selagi itu ahli KP tak dapat tempah.
- Satu kolej boleh ada **banyak checkpoint**. Ahli nampak checkpoint **aktif** kolej sendiri yang sepadan jantinanya (jantina khusus atau "mana-mana") dan pilih satu semasa daftar (atau tukar di Profil). Tidak pilih = sistem pilih yang sepadan jantina dahulu. Admin boleh nyahaktif atau **padam** checkpoint; jika ahli masih guna, mesti pilih checkpoint lain (kolej sama) dan ahli dipindahkan automatik.
- Ahli taip **blok** tempat tinggal. Semua pengguna isi **nama pendek** (dipapar dalam senarai kenderaan).

## 2. Tempahan & masa (waktu Malaysia)
| Masa | Kejadian | Tetapan |
|---|---|---|
| Hari latihan **5:00 PM** | Tutup: ahli tak boleh tempah/batal sendiri, prebet tak boleh ubah. Selepas itu **admin sahaja** tambah/buang ahli | `CUTOFF_TIME` |
| Hari latihan **7:30 PM** | Senarai disahkan automatik jika admin belum sahkan; kenderaan dikunci, bayaran dibuka | `AUTO_FINALISE_TIME` |
| Hari **selepas** latihan **12:00 tengah hari** | Tarikh akhir ahli bayar. Selepas itu jadi tunggakan | `PAY_DEADLINE_TIME` |
- Pickup pergi 8:30–8:50 PM (ahli sampai 5 minit awal, `ARRIVE_EARLY_MINUTES`); balik bermula 11:00 PM. ⚙️ (Admin › Lagi › sesi)
- Ahli pilih tarikh (sehingga 21 hari ke depan) dan Pergi / Balik / kedua-duanya. Satu ahli satu kenderaan untuk pergi dan balik.
- Cuti/tarikh libur dicatat admin (⚙️ Cuti); tidak dipapar sebagai latihan.
- **Latihan dibatalkan boleh diaktifkan semula** (admin sahaja, selagi tarikh belum lepas, cth pengerusi putuskan latihan diteruskan). Ahli yang ditempah sebelum latihan dibatalkan **dipulihkan**; ahli yang batal sendiri **kekal batal**. Cuti pada tarikh itu dibuang, semua dimaklumkan, kenderaan disusun semula.
- Latihan dibatalkan: bayaran yang sudah dibuat jadi **kredit**. Kredit digunakan pada latihan seterusnya yang ahli tempah, ditolak mengikut kategori kenderaan latihan itu, semasa senarai disahkan.

## 3. Tempat latihan & berjalan kaki
Admin tetapkan tempat latihan setiap latihan. Jika tempat ialah sebuah kolej (cth Dewan Merdeka KRP), **ahli kolej itu berjalan kaki** (tiada prebet). L50 tak mengecualikan sesiapa. Aktiviti luar (⚙️) ada harga & had jarak motosikal sendiri.

## 4. Susunan kenderaan (algoritma auto)
Kereta dahulu, motosikal kemudian; isi kenderaan sehingga penuh. Keutamaan penumpang:
1. Kolej sendiri prebet dahulu (kurangkan hentian).
2. Zon prebet menentukan keutamaan seterusnya:

| Zon prebet | Susunan penumpang diambil |
|---|---|
| Dekat | dekat → empat kolej (KDSE, KTGB, KLG, KDOJ) → jauh lain |
| Empat kolej (jauhA) | empat kolej → dekat → jauh lain |
| Jauh lain (K9 & K10, KTC, KP) | jauh sendiri → dekat → empat kolej |

3. **Adab tempat duduk (sentiasa dikuatkuasakan):** satu baris satu jantina; lelaki tak duduk di belakang perempuan; konfigurasi baris 5 seat = 1,3; 7 seat = 1,3,2; motosikal bawa seorang, rider & penumpang sama jantina; prebet perempuan hanya bawa perempuan.
4. **Perempuan seorang diri dalam kereta prebet lelaki tidak dibenarkan** (mesti 0 atau ≥ 2). Dia diletakkan sebagai **e-hailing automatik** (tiada amaran perlu keputusan admin).
5. Kenderaan yang bawa sangat sedikit (≤ `COMBINE_BELOW_PASSENGERS`=2) digabung ke kenderaan lain jika semua muat dan ikut adab.
6. Selebihnya (penuh / langgar adab) → e-hailing. Admin boleh tukar tempat duduk manual dan "susun semula".
7. Prebet boleh ada **beberapa kenderaan** tetapi **satu kenderaan sehari** (dipilih semasa sahkan).
8. Prebet mesti **sahkan "boleh bawa"** setiap tarikh. Tak dapat bawa → hubungi BKK (admin bertugas); tiada butang batal per tarikh.
9. Prebet tanda dua kali: **dah sampai tempat latihan** dan **dah hantar semua selepas latihan** (amaran sahaja jika lupa; tetap dibayar).
10. Kenderaan perlu lulus admin: jenama, warna, no. plat; gambar lesen + tarikh tamat wajib. Akuan keselamatan rider pilihan (peringatan berkala).

## 5. Yuran ahli ⚙️ (Admin › Lagi › Harga)
Seorang per latihan (pergi+balik; tiada potongan sehala):
| | Kolej dekat | Kolej jauh |
|---|---|---|
| Kereta | RM3 | RM4 |
| Motosikal | RM1 | RM2 |
- Muktamad selepas senarai disahkan. Latihan dibatalkan → bayaran jadi **kredit** (tiada pemulangan tunai). Tiada tunai: resit sahaja, disahkan bendahari/admin.
- Tunggakan: ahli yang lewat masih boleh naik; disekat hanya jika bayaran tertua melebihi `ARREARS_BLOCK_DAYS` (183 hari).

## 6. Bayaran prebet ⚙️ (hanya **admin** boleh ubah kadar)
**Tetap sehari latihan** (bukan ikut bilangan penumpang), ikut kategori kenderaan (kolej prebet, atau ditetapkan admin):
| | Dekat | Jauh |
|---|---|---|
| Kereta | RM10 | RM14 |
| Motosikal | RM1 | RM2 |
- Prebet yang **tidak beroperasi** pada latihan itu (tiada penumpang / tak sahkan) **tidak dikenakan bayaran**.
- Admin pilih kaedah bayar ⚙️: **per latihan / mingguan / bulanan**. Bayaran digabung ikut tempoh.
- **Baki tertunggak dibawa ke bayaran seterusnya** dengan nota tarikh. Contoh: RM10 latihan 15/10 terlupa dibayar → bayaran seterusnya RM20 = "RM10 untuk 15/10 + RM10 untuk 18/10".
- Bendahari bayar **seorang prebet seorang**: nampak bank/QR prebet, bayar di luar app, muat naik **satu resit**. Prebet tekan "Diterima".
- Penyata untung/rugi (admin sahaja): kutipan ahli − bayaran prebet. Boleh negatif (persatuan tanggung demi kebajikan ahli).

## 7. Admin bertugas & hubungan
Setiap admin pilih hari bertugas dalam bulan itu + nombor telefon. Ahli/prebet nampak admin bertugas hari itu. Masalah **laman web** (bukan urusan prebet): `SITE_CONTACT_PHONE` (0192278390, pentadbir laman web).

## 8. Data peribadi & sandaran
- Semua pendaftar mesti tanda persetujuan: maklumat disimpan oleh BKK untuk urusan pengangkutan latihan sahaja dan tidak dikongsi dengan pihak luar.
- Data disimpan di Supabase (teks dalam PostgreSQL; gambar lesen/resit/QR dalam Storage). Kata laluan disimpan sebagai hash, tidak boleh dibaca sesiapa.
- **Sandaran:** Admin › Lagi › "Muat turun sandaran" (admin sahaja) menghasilkan zip CSV (ahli & prebet, kenderaan, tempahan, bayaran ahli, bayaran prebet). Tidak termasuk kata laluan, gambar, dan no. akaun bank penuh (4 digit akhir sahaja). Simpan dalam folder Drive BKK peribadi (2–3 orang). Sebulan sekali dan sebelum reset tahunan.
- Pilihan paparan cerah/gelap/ikut telefon disimpan pada akaun pengguna (ikut ke peranti lain).

## 9. Lain-lain
- Lupa kata laluan: emel (Brevo) jika dikonfigurasi, jika tidak permintaan pergi kepada admin yang beri kata laluan sementara.
- Log masuk Google pilihan (`GOOGLE_CLIENT_ID`).
- Teks "Syarat" dalam app boleh disunting admin (⚙️ Lagi › Peraturan); lalai ditulis dalam kod.
