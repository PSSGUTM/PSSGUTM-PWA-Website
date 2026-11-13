# 07 · Log keputusan (Decision log)

Format: **Keputusan** — sebab — kesan pada kod. BKK akan datang: tambah baris baharu di bawah (tarikh, siapa, keputusan, sebab).

## Teknikal
| Keputusan | Sebab | Di mana |
|---|---|---|
| Render percuma + keepalive GitHub Actions 10 min | Kos sifar; scheduler perlu server hidup | `keepalive.yml` |
| 1 worker sahaja | Scheduler dalam proses; elak kerja berganda | `Dockerfile`, Start Command |
| Brevo HTTP API, bukan SMTP | Render percuma sekat SMTP | `mailer.py` |
| Supabase Storage untuk fail | Cakera Render hilang bila restart | `storage.py` |
| Tiada Alembic; `migrate.py` ADD COLUMN | Skema kecil, kos senggara rendah | `migrate.py` |
| Nilai boleh ubah disimpan dalam jadual `settings` | Admin ubah tanpa kod | `services/booking.py` |
| Algoritma susunan dalam `services/assign.py` (fungsi tulen) | Mudah diuji tanpa DB | `tests/test_assign.py` |
| Seed boleh diulang; `upgrade_v7` hanya sekali (bendera `seed_v7`) | Elak timpa tetapan admin | `seed.py` |

## Bisnes (sesi 2026/2027)
| Keputusan | Sebab |
|---|---|
| Semua 13 kolej & semua sesi/tahun dibuka | Mudahkan semua ahli; KP menunggu checkpoint |
| Tiada tempahan berulang, ahli pilih tarikh | Elak tempahan lapuk |
| Tutup 5 PTG; auto-sah 7:30 PM; bayar sebelum 12 TGH hari esok | Beri masa admin susun; tarikh akhir bayar jelas; tunggakan hanya selepas tarikh itu |
| Selepas 5 PTG hanya admin tambah/buang | Kenderaan sudah diatur |
| Ahli kolej tempat latihan berjalan kaki | Tidak perlu prebet |
| Pilih checkpoint + taip blok; nama pendek wajib | Prebet tahu lokasi tepat; senarai mudah dibaca |
| Keutamaan: kolej sendiri → zon (dekat / empat kolej / jauh lain) | Kurangkan hentian dan jarak prebet |
| Perempuan seorang dengan prebet lelaki → e-hailing auto (tiada keputusan admin) | Adab & keselamatan; mengelak beban admin |
| Prebet boleh banyak kenderaan, satu sehari | Fleksibel |
| Tiada butang batal per tarikh; "Tak dapat bawa? Hubungi BKK" | Elak batal saat akhir tanpa pengetahuan BKK |
| Dua tanda prebet (sampai, hantar) — amaran sahaja | Pantau tanpa menghukum |
| Bayaran prebet **tetap sehari latihan** (kereta 14/10, motosikal 2/1) | Mudah, adil, boleh dijangka; bukan ikut penumpang |
| Kategori bayaran = kategori kenderaan (kolej prebet, atau admin tetapkan) | Satu sumber; "empat kolej" ialah zon susunan sahaja, tetapi kategori bayaran = **jauh** |
| Hanya admin ubah kadar & kaedah bayar; bendahari sahaja bayar | Kawalan kewangan |
| Prebet tidak beroperasi = tiada bayaran | Adil |
| Bayaran digabung ikut kaedah (latihan/minggu/bulan); baki tertunggak dibawa dengan nota tarikh | Kurangkan bilangan pindahan; jelas |
| Satu resit satu prebet | Mudah audit |
| Penyata untung/rugi (admin sahaja), boleh negatif | Ketelusan kewangan; persatuan tanggung demi kebajikan |
| Admin bertugas ikut bulan; nombor laman web 0192278390 sandaran | Hubungan jelas untuk prebet/ahli |
| Kontras ≥ 4.5:1 cerah & gelap; QR/resit dalam bingkai putih | Boleh dibaca & diimbas |
| Aktifkan semula latihan dibatalkan: pulihkan hanya tempahan yang dibatalkan kerana latihan dibatalkan (lajur `cancelled_by_event`) | Ahli yang batal sendiri tak dimasukkan semula tanpa kehendak mereka |
| Kredit bayaran guna pada latihan seterusnya mengikut tarikh yang ahli pilih, ditolak ikut kategori kenderaan | Tiada pemulangan tunai |
| Padam checkpoint: pindahkan ahli ke checkpoint lain (kolej sama) secara automatik | Elak ahli tanpa checkpoint |
| Tema cerah/gelap disimpan pada akaun (lajur `users.theme`) | Ikut ke peranti lain; lalai ikut telefon |
| Butang Muat turun sandaran (zip CSV, admin sahaja), tanpa gambar dan no. akaun penuh | Sandaran dalam fail BKK; kurangkan risiko data sensitif |
| Persetujuan privasi wajib semasa daftar | Ketelusan penggunaan data peribadi (semak dengan pihak universiti jika perlu) |
| Seed mesti idempotent dan jalan automatik setiap deploy | Deploy pernah gagal kerana INSERT duplikat |

## Perubahan selepas ini
| Tarikh | Siapa | Keputusan | Sebab |
|---|---|---|---|
| 2026-11-06 | MT/biro (mesyuarat) + Mir | Keputusan laman web PSSGUTM (versi muktamad "Soalan website 2.0"): akaun GitHub/Render/Vercel/Supabase di bawah emel persatuan; kekal pelan percuma; tiada langganan Claude berbayar | Elak beban kewangan persatuan; elak bergantung pada emel peribadi |
| 2026-11-06 | MT/biro + Mir | Pentadbir sistem = semua MT, setiausaha dan biro; pengganti ialah MT/biro sesi seterusnya. Sekretariat tak boleh lihat data ahli | Kesinambungan antara sesi |
| 2026-11-06 | MT/biro + Mir | No. ahli: SG + sesi + urutan (cth SG2728001) selagi pelajar. Bila tamat, bertukar kepada SSG + kod sesi masuk (cth SSG2728, SSG9495) sebagai alumni; no. SG lama disimpan sebagai rujukan. SSG tiada nombor urutan dan tak unik; ID dalaman digunakan sebagai kunci; carian ikut nama, susun A hingga Z | Peraturan persatuan; alumni sambung master guna SSG yang sama |
| 2026-11-06 | MT/biro + Mir | Ahli beri tarikh tamat pengajian semasa daftar (diploma, ijazah, master, PhD, asasi). Bila tarikh tiba, sistem tanya sama ada sudah tamat; jika belum, minta baki tempoh dan tarikh baharu; selepas itu tukar SG ke SSG | Pelajar boleh lewat tamat atau tangguh |
| 2026-11-06 | MT/biro + Mir | Pengangkutan latihan rasmi (Rabu/Sabtu) hanya untuk ahli pelajar yang tinggal di kolej dalam UTM. Alumni dan ahli tinggal luar tidak, kecuali aktiviti luar | Ada ahli tiada kenderaan sendiri; alumni kebanyakan di luar |
| 2026-11-06 | MT/biro + Mir | Aktiviti luar: semua ahli boleh mohon pengangkutan. Ada tempat pergi dan tempat balik berasingan. Admin tetapkan tetap (semua ikut) atau biar ahli pilih kolej atau tempat lain (lalai); admin boleh ubah. Yuran dibundar ke atas ke ringgit penuh. **Dibina** (PEMBETULAN 19) | Ahli biasanya berkumpul di satu tempat untuk aktiviti luar |
| 2026-11-06 | Mir | Tema lalai merah naga (`#a8322a`) dan emas (`#d4a94e`); admin boleh tukar atau set semula | Pilihan pengurusan |
| | | | |
| 2026-11-07 | MT/biro + Mir | Semua ahli layak guna transport kecuali prebet (prebet mohon kepada admin BKK). Hanya ambil ahli di UTM (kolej), bukan yang tinggal luar atau sudah ada kenderaan, untuk latihan rasmi. Alumni berlatih semula sebagai ahli: belum disentuh (bersama kerja SG ke SSG) | Tujuan transport: memudahkan ahli tiada kenderaan ke tempat latihan |
| 2026-11-07 | Mir | Pemberitahuan perubahan tempat ambil cukup dalam app (tiada WhatsApp automatik) | Ringkas |
| 2026-11-07 | Mir | Aktiviti luar: admin boleh pilih persatuan tanggung yuran pengangkutan (ahli tak bayar; persatuan serah kepada BKK kemudian dan BKK bayar prebet). Lalai: ahli bayar kepada BKK, BKK bayar prebet. Tempat pergi dan balik boleh tetap atau pilihan ahli, setiap satu berasingan | Kadang-kadang persatuan tanggung dari yuran penyertaan |
| 2026-11-08 | Mir | Versi penuh PSSGUTM (modul utama + transport satu app) | Log masuk Google; emel mesti ada dalam senarai import untuk akaun auto. Rekod tunggal Person (SG/SSG, sesi, bengkung, jawatan). Bengkung senarai bertingkat boleh diubah admin. SG→SSG melalui senarai pengesahan admin (no. SSG = SSG + sesi). Kehadiran QR oleh BLG + manual. Inventori dengan rekod pinjam/pulang + gambar. Biro/seki/jawatan boleh diubah admin. Transport kekal guna no. SG lama pada akaun (tidak berubah semasa SG→SSG). Susunan kenderaan: seorang sahaja bagi sesuatu jantina → motosikal. |
| 2026-11-08 | Mir | Bengkung hanya untuk ahli semasa, bukan alumni | Isu sensitif (nasihat rakan pentadbir). Alumni tiada medan bengkung; bila SG ditukar SSG, bengkung dan sejarahnya dikosongkan. |
| 2026-11-09 | Mir | Muka depan baharu ikut mockup (header + menu sisi, tanpa tab bawah) | Warna lalai merah naga, admin boleh tukar. Transport sedia ada dibungkus (Buka Transport). Direktori papar nama, sesi, kolej, jawatan sahaja. Pengumuman/kebajikan/panduan/hubungi/sokongan diurus admin. Kehadiran = rekod saya; Kod QR = imbas/masuk kod; semua pemegang jawatan (MT, biro, seki, jawatankuasa) boleh ambil kehadiran. RLS Supabase dihidupkan automatik. |
| 2026-11-09 | Pembangun / BKK | Peralihan alat pembangunan kod: Selepas fasa awal menggunakan Claude Code, pembangunan kini berpindah sepenuhnya kepada Google Antigravity untuk pengaturcaraan AI (coding AI) | Menjimatkan kos persatuan (tanpa kos langganan berbayar Claude), membolehkan pembaikan kod secara langsung, dan pengesahan automatik dalam persekitaran pembangun |
| 2026-11-14 | Pembangun / BKK | Peralihan hos frontend dari Vercel ke Render Static Site | Mengelakkan isu sekatan kolaborator/bayaran Vercel Hobby pada repo persatuan; menyatukan pengurusan frontend dan backend di bawah satu bumbung akaun Render persatuan secara percuma |
