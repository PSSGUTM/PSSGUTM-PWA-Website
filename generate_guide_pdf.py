import os
import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        if self._pageNumber == 1:
            return  # Skip cover page
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#666666"))
        
        # Header line
        self.setStrokeColor(colors.HexColor("#D4A94E"))
        self.setLineWidth(0.5)
        self.line(40, A4[1] - 40, A4[0] - 40, A4[1] - 40)
        self.drawString(40, A4[1] - 35, "PSSGUTM — Panduan Penggunaan Aplikasi Rasmi")
        
        # Footer line
        self.setStrokeColor(colors.HexColor("#E0E0E0"))
        self.line(40, 45, A4[0] - 40, 45)
        self.drawString(40, 32, "Portal PWA: https://pssgutm-app.onrender.com | Sesi 2026/2027")
        self.drawRightString(A4[0] - 40, 32, f"Muka Surat {self._pageNumber} daripada {page_count}")
        self.restoreState()

def build_pdf(filename):
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Colors
    c_primary = colors.HexColor("#7A1818")   # Gayong Crimson / Maroon
    c_accent = colors.HexColor("#B8860B")    # Antique Gold
    c_dark = colors.HexColor("#222222")
    c_muted = colors.HexColor("#555555")
    c_boxbg = colors.HexColor("#FDF9F3")
    c_border = colors.HexColor("#EADCB9")

    # Custom typography styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=c_primary,
        alignment=1, # Center
        spaceAfter=10
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=c_accent,
        alignment=1,
        spaceAfter=25
    )
    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        textColor=c_primary,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )
    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=c_accent,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=c_dark,
        spaceAfter=6
    )
    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13.5,
        textColor=c_dark,
        leftIndent=15,
        spaceAfter=4
    )
    box_text = ParagraphStyle(
        'BoxText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=c_dark
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8.5,
        leading=12,
        textColor=c_muted,
        alignment=1
    )

    story = []

    # ================= COVER / HEADER =================
    story.append(Spacer(1, 20))
    story.append(Paragraph("PANDUAN LENGKAP PENGGUNAAN APLIKASI", title_style))
    story.append(Paragraph("PORTAL RASMI PSSGUTM (PWA)<br/><b>PERSATUAN SILAT SENI GAYONG UNIVERSITI TEKNOLOGI MALAYSIA</b>", subtitle_style))
    
    meta_box_data = [[
        Paragraph(
            "<b>Pautan Web App:</b> https://pssgutm-app.onrender.com<br/>"
            "<b>Sasaran Pengguna:</b> Semua Ahli Biasa, Penumpang, Prebet (Pemandu), Majlis Tertinggi (MT), Biro & Pentadbir BKK<br/>"
            "<b>Versi Sistem:</b> 2.0 (Pengurusan Persatuan & Pengangkutan Bersepadu) | Sesi 2026/2027",
            box_text
        )
    ]]
    meta_table = Table(meta_box_data, colWidths=[doc.width])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_boxbg),
        ('BOX', (0,0), (-1,-1), 1, c_accent),
        ('PADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 15))

    # ================= 1. CARA PASANG APP PWA =================
    story.append(Paragraph("1. CARA MEMASANG APLIKASI PWA PADA TELEFON PINTAR", h1_style))
    story.append(Paragraph(
        "Aplikasi PSSGUTM dibina menggunakan teknologi <i>Progressive Web App (PWA)</i>. "
        "Anda tidak perlu memuat turun dari Google Play Store atau Apple App Store. "
        "Ikuti langkah ringkas ini untuk memasangnya terus pada skrin utama telefon seperti aplikasi biasa:",
        body_style
    ))

    pwa_data = [
        [
            Paragraph("<b>📱 Pengguna Android (Google Chrome)</b>", h2_style),
            Paragraph("<b>🍏 Pengguna iPhone / iOS (Safari)</b>", h2_style)
        ],
        [
            Paragraph(
                "1. Buka pelayar <b>Google Chrome</b> dan layari: <u>https://pssgutm-app.onrender.com</u><br/>"
                "2. Tekan ikon <b>tiga titik bertindih (⋮)</b> di bucu kanan atas.<br/>"
                "3. Pilih <b>'Add to Home screen'</b> atau <b>'Pasang aplikasi'</b>.<br/>"
                "4. Sahkan pemasangan. Ikon PSSGUTM akan muncul di skrin utama telefon anda.",
                box_text
            ),
            Paragraph(
                "1. Buka pelayar <b>Safari</b> dan layari: <u>https://pssgutm-app.onrender.com</u><br/>"
                "2. Tekan butang <b>Kongsi / Share (petak dengan anak panah atas)</b> di bar bawah.<br/>"
                "3. Skrol ke bawah dan pilih <b>'Add to Home Screen' (Tambah ke Skrin Utama)</b>.<br/>"
                "4. Tekan <b>'Add'</b> di bucu kanan atas. Ikon rasmi akan tersedia di skrin telefon.",
                box_text
            )
        ]
    ]
    pwa_table = Table(pwa_data, colWidths=[doc.width * 0.5, doc.width * 0.5])
    pwa_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FAFAFA")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#DDDDDD")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#EEEEEE")),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(pwa_table)
    story.append(Spacer(1, 12))

    # ================= 2. PANDUAN AHLI BIASA & PENUMPANG =================
    story.append(Paragraph("2. PANDUAN AHLI BIASA & PENUMPANG", h1_style))
    
    story.append(Paragraph("A. Log Masuk & Pendaftaran Pertama Kali", h2_style))
    story.append(Paragraph(
        "• <b>Log Masuk Pantas:</b> Gunakan butang <i>'Sign in with Google'</i> dengan emel rasmi UTM (<code>@graduate.utm.my</code>).<br/>"
        "• <b>Log Masuk Manual:</b> Masukkan <b>No. Ahli</b> anda (contoh: <code>SG2627001</code>) dan kata laluan yang didaftarkan.<br/>"
        "• <b>Pendaftaran Baru:</b> Jika belum pernah mendaftar, pilih tab <i>'Daftar'</i>. Pastikan No. Ahli anda telah dimasukkan oleh admin dalam senarai ahli sah.",
        bullet_style
    ))

    story.append(Paragraph("B. Melengkapkan Profil (Wajib untuk Buka Akses Penuh)", h2_style))
    story.append(Paragraph(
        "Bagi ahli baharu atau yang diimport, satu banner amaran kuning akan terpapar di Beranda: <i>'⚠️ Profil Anda Belum Lengkap'</i>. "
        "Tekan butang <b>'Lengkapkan'</b> atau pergi ke <b>Profil Saya ➔ Sunting</b> untuk mengisi:<br/>"
        "1. <b>No. Telefon WhatsApp Aktif:</b> (Elakkan 0000000000) supaya prebet atau admin boleh menghubungi anda.<br/>"
        "2. <b>Kolej Kediaman:</b> Pilih kolej anda (cth: KTDI, KRP, KTF, KDSE, dll).<br/>"
        "3. <b>Blok & Bilik:</b> Masukkan maklumat lokasi bilik (contoh: <code>MA3-102</code>).<br/>"
        "4. <b>Tempat Menunggu (Checkpoint):</b> Pilih lokasi naik kenderaan yang paling hampir dengan kolej anda.",
        bullet_style
    ))

    story.append(Paragraph("C. Cara Tempah Pengangkutan Latihan Silat (Transport)", h2_style))
    story.append(Paragraph(
        "Pengangkutan disediakan untuk latihan mingguan pada setiap <b>Rabu</b> dan <b>Sabtu</b> (9:00 PM – 11:00 PM).<br/>"
        "1. Buka menu <b>Transport</b> dari Beranda.<br/>"
        "2. Pilih tarikh latihan yang berkenaan.<br/>"
        "3. Pilih arah perjalanan anda: <b>Pergi Sahaja</b>, <b>Balik Sahaja</b>, atau <b>Pergi & Balik</b>.<br/>"
        "4. <b>Waktu Tutup (Cut-off Time):</b> Tempahan ditutup tepat pada <b>jam 5:00 petang</b> pada hari latihan! Sila tempah sebelum waktu ini.<br/>"
        "5. <b>Semakan Prebet Bertugas:</b> Selepas jam 5:00 petang, admin BKK akan mengesahkan senarai. Anda boleh melihat siapa pemandu prebet anda, jenis kenderaan, dan waktu menunggu (biasanya 8:30 PM - 8:50 PM).",
        bullet_style
    ))

    story.append(Paragraph("D. Bayaran Tambang Latihan", h2_style))
    story.append(Paragraph(
        "1. Buka menu <b>Bayaran</b> untuk melihat jumlah tambang tertunggak (mengikut kadar zon kolej yang ditetapkan).<br/>"
        "2. Imbas kod QR DuitNow rasmi persatuan yang dipaparkan dalam aplikasi.<br/>"
        "3. Muat naik resit transaksi bank untuk disahkan oleh Bendahari BKK.",
        bullet_style
    ))

    story.append(Paragraph("E. Mengimbas Kod QR Kehadiran Gelanggang", h2_style))
    story.append(Paragraph(
        "1. Apabila tiba di gelanggang latihan atau acara rasmi, buka menu <b>Kod QR</b> di Beranda.<br/>"
        "2. Halakan kamera telefon ke arah Kod QR Kehadiran yang dipaparkan oleh urusetia/biro di gelanggang.<br/>"
        "3. Skrin akan memaparkan notis hijau <i>'Kehadiran Direkodkan'</i>. Peratusan kehadiran sesi anda akan automatik dikemas kini di <b>Profil Saya</b>.",
        bullet_style
    ))

    story.append(Spacer(1, 10))

    # ================= 3. PANDUAN PEMANDU SUKARELA (PREBET) =================
    story.append(Paragraph("3. PANDUAN PEMANDU SUKARELA (PREBET PSSGUTM)", h1_style))
    story.append(Paragraph(
        "Prebet ialah ahli yang mempunyai kenderaan sendiri (kereta atau motosikal) dan menawarkan khidmat mengambil serta menghantar ahli lain ke gelanggang latihan.",
        body_style
    ))
    story.append(Paragraph(
        "• <b>Langkah 1 (Daftar Kenderaan):</b> Pergi ke <b>Transport ➔ Jadi prebet</b>. Masukkan jenis kenderaan, warna, no. pendaftaran (plat), dan muatan tempat duduk.<br/>"
        "• <b>Langkah 2 (Muat Naik Lesen):</b> Muat naik gambar lesen memandu yang sah untuk keselamatan dan pengesahan admin BKK.<br/>"
        "• <b>Langkah 3 (Tanda Ketersediaan):</b> Sebelum jam 5:00 petang hari latihan, buka tab Prebet dan tandakan sama ada anda <b>'Sedia Membawa'</b> atau tidak pada tarikh tersebut.<br/>"
        "• <b>Langkah 4 (Senarai Penumpang):</b> Selepas jam 5:00 petang, semak senarai penumpang yang diperuntukkan kepada anda beserta kolej dan blok bilik mereka.<br/>"
        "• <b>Langkah 5 (Tuntutan Bayaran Minyak):</b> Setiap penumpang yang dibawa akan dikira automatik oleh sistem. Bendahari akan memindahkan bayaran elaun bahan api terus ke akaun bank anda.",
        bullet_style
    ))

    story.append(Spacer(1, 10))

    # ================= 4. PANDUAN PENGURUSAN PERSATUAN (MT & BIRO) =================
    story.append(Paragraph("4. PANDUAN PENGURUSAN PERSATUAN (MT & BIRO)", h1_style))
    story.append(Paragraph(
        "Modul ini diakses melalui menu laci (drawer) ➔ <b>Pengurusan persatuan</b> oleh Majlis Tertinggi, Ketua Biro, dan Pentadbir.",
        body_style
    ))

    admin_features = [
        [
            Paragraph("<b>Tab & Modul</b>", h2_style),
            Paragraph("<b>Fungsi & Cara Penggunaan</b>", h2_style)
        ],
        [
            Paragraph("<b>Ahli & Import CSV</b><br/><i>(Satu Sumber Sah)</i>", box_text),
            Paragraph(
                "• <b>Muat Naik CSV Berpusat:</b> Di tab <b>Import</b>, admin boleh memuat naik senarai ahli menggunakan fail CSV ringkas.<br/>"
                "• <b>Auto-Sync:</b> Data ahli automatik masuk ke senarai Kehadiran, Direktori, dan <i>Member Roster</i> Pengangkutan serentak.<br/>"
                "• <b>Muat Turun Templat:</b> Tekan butang 'Muat turun templat CSV contoh' untuk panduan format.",
                box_text
            )
        ],
        [
            Paragraph("<b>Kehadiran Gelanggang</b><br/><i>(Biro Latihan / MT)</i>", box_text),
            Paragraph(
                "• <b>Buka Sesi Kehadiran:</b> Cipta sesi baharu (cth: Latihan Silat Rabu, Kursus Bengkung, AGM).<br/>"
                "• <b>Papar Kod QR:</b> Tekan butang 'Papar QR' pada skrin telefon/laptop untuk diimbas oleh semua ahli.<br/>"
                "• <b>Ambil Hadir Manual:</b> Cari nama ahli dan tandakan hadir jika telefon ahli tiada bateri.<br/>"
                "• <b>Eksport:</b> Muat turun rekod kehadiran dalam fail CSV untuk dokumentasi aktiviti UTM.",
                box_text
            )
        ],
        [
            Paragraph("<b>Inventori & Pinjaman</b><br/><i>(Biro Logistik / Stor)</i>", box_text),
            Paragraph(
                "• <b>Daftar Aset:</b> Rekod alatan persatuan (senjata parang, sundang, tongkat, tanjak, bendera, PA sistem).<br/>"
                "• <b>Pinjaman Alatan:</b> Rekod nama ahli peminjam, kuantiti, tarikh keluar dan tarikh jangka pulang.<br/>"
                "• <b>Pemulangan:</b> Tandakan barang telah dipulangkan dan semak baki stok semasa stor persatuan.",
                box_text
            )
        ],
        [
            Paragraph("<b>Biro & Jawatankuasa</b>", box_text),
            Paragraph(
                "• Menetapkan senarai pemegang jawatan MT dan Biro (BKK, BIT, BLG, Kebajikan, dll).<br/>"
                "• Menetapkan kebenaran khas (cth: siapa boleh jana kehadiran atau urus inventori).",
                box_text
            )
        ]
    ]
    admin_table = Table(admin_features, colWidths=[doc.width * 0.32, doc.width * 0.68])
    admin_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FFFFFF")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#EAEAEA")),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(admin_table)
    story.append(Spacer(1, 10))

    # ================= 5. PANDUAN PENTADBIR BKK (ADMIN TRANSPORT) & BENDAHARI =================
    story.append(Paragraph("5. PANDUAN PENTADBIR BKK (TRANSPORT) & BENDAHARI", h1_style))
    story.append(Paragraph(
        "• <b>Pengesahan Senarai (Finalise):</b> Tepat jam 5:00 petang hari latihan, admin BKK menekan butang <i>'Sahkan Senarai'</i> di Admin Transport. Sistem akan menyusun kerusi mengikut zon kolej dan menghantar notifikasi kepada penumpang dan prebet.<br/>"
        "• <b>E-Hailing BKK:</b> Sekiranya bilangan prebet tidak mencukupi untuk menampung ahli, admin boleh menanda penumpang untuk perkhidmatan Grab/Maxim dengan subsidi tambang persatuan.<br/>"
        "• <b>Muat Turun Data Ahli Sedia Ada (.CSV):</b> Di Admin Transport ➔ tab <b>Lagi</b> ➔ bahagian <b>📋 Senarai ahli sah</b>, terdapat butang <b>'📥 Muat turun senarai ahli sedia ada (.CSV)'</b> untuk mengeksport keseluruhan rekod ahli bila-bila masa.<br/>"
        "• <b>Tugasan Bendahari:</b> Menyemak resit bayaran ahli, mengesahkan status hutang/tunggakan, dan membuat agihan bayaran elaun kepada prebet mengikut rekod ringkasan bayaran.",
        bullet_style
    ))

    story.append(Spacer(1, 10))

    # ================= 6. SOALAN LAZIM (FAQ) =================
    story.append(Paragraph("6. SOALAN LAZIM (FAQ) & BANTUAN TEKNIKAL", h1_style))
    story.append(Paragraph(
        "<b>S: Apa perlu dibuat jika saya terlupa kata laluan?</b><br/>"
        "J: Tekan pautan <i>'Lupa kata laluan?'</i> di halaman log masuk. Masukkan emel berdaftar anda dan semak pautan set semula yang dihantar ke peti masuk emel anda.<br/><br/>"
        "<b>S: Bolehkah saya membatalkan tempahan transport selepas jam 5:00 petang?</b><br/>"
        "J: Pembatalan selepas waktu pengesahan 5:00 petang memerlukan anda menghubungi Admin BKK secara terus supaya susunan kenderaan dan pemandu dapat diatur semula.<br/><br/>"
        "<b>S: Bagaimana jika nombor ahli saya tiada dalam senarai?</b><br/>"
        "J: Sila hubungi Setiausaha atau Admin BKK persatuan untuk memasukkan nombor ahli anda ke dalam sistem pangkalan data.",
        body_style
    ))

    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1, color=c_accent, spaceBefore=5, spaceAfter=10))
    story.append(Paragraph(
        "<b>Disediakan oleh Pentadbiran & Biro Komunikasi Korporat (BKK)</b><br/>"
        "Persatuan Silat Seni Gayong Universiti Teknologi Malaysia (PSSGUTM)<br/>"
        "Sebarang pertanyaan atau bantuan teknikal, sila hubungi pentadbir sistem melalui menu <b>'Hubungi'</b> di dalam aplikasi.",
        meta_style
    ))

    doc.build(story, canvasmaker=NumberedCanvas)
    print("PDF berjaya dijana:", filename)

if __name__ == "__main__":
    out1 = r"c:\Users\Nursyifaa\OneDrive\Documents\PSSGUTM\BKK\APP DEVELOPMENT (PWA)\PSSGUTM\Panduan_Penggunaan_PSSGUTM.pdf"
    out2 = r"C:\Users\Nursyifaa\.gemini\antigravity\brain\672e569e-bf9b-4ce0-9c67-8b95fce61dc7\Panduan_Penggunaan_PSSGUTM.pdf"
    build_pdf(out1)
    build_pdf(out2)
