import io
from datetime import date

from openpyxl import Workbook

from app.services import people as pp


def test_session_rules():
    assert pp.valid_session("9495") and pp.valid_session("9900") and pp.valid_session("2425")
    assert not pp.valid_session("2426") and not pp.valid_session("24") and not pp.valid_session("abcd")
    assert pp.session_label("9495") == "1994/95" and pp.session_label("0001") == "2000/01"
    assert pp.session_year("9900") == 1999 and pp.session_year("0102") == 2001


def test_member_numbers():
    assert pp.ssg_no("9495") == "SSG9495"
    assert pp.next_sg_no("2425", []) == "SG2425001"
    assert pp.next_sg_no("2425", ["SG2425001", "SG2425009", "SG2324005"]) == "SG2425010"


def test_dates_phone_gender():
    assert pp.parse_date("31/07/2028") == date(2028, 7, 31)
    assert pp.parse_date("2028-07-31") == date(2028, 7, 31)
    assert pp.parse_date("") is None
    assert pp.clean_phone("123456789") == "0123456789"
    assert pp.norm_gender("Lelaki") == "male" and pp.norm_gender("perempuan") == "female" and pp.norm_gender("x") is None


def test_due_for_conversion():
    t = date(2026, 11, 8)
    assert pp.due_for_conversion("SG", date(2026, 11, 8), t)
    assert not pp.due_for_conversion("SG", date(2026, 12, 1), t)
    assert not pp.due_for_conversion("SSG", date(2020, 1, 1), t)
    assert not pp.due_for_conversion("SG", None, t)


def _book():
    wb = Workbook()
    wb.remove(wb.active)
    b = wb.create_sheet("Bengkung"); b.append(["Nama bengkung *", "Susunan"])
    b.append(["CONTOH Putih", ""]); b.append(["Putih", ""]); b.append(["Hijau", ""])
    m = wb.create_sheet("Ahli semasa")
    m.append(["Nama penuh *", "Emel (Google) *", "No. telefon *", "Jantina *", "Sesi masuk *", "Peringkat pengajian *",
              "Tarikh tamat pengajian *", "Kolej", "Blok", "Jurulatih", "Bengkung semasa *", "Tarikh naik bengkung"])
    m.append(["CONTOH Ahmad", "contoh@gmail.com", "0123456789", "Lelaki", "2728", "Ijazah", "31/07/2031", "KTC", "S44", "Tidak", "Putih", ""])
    m.append(["Ali Bin Abu", "ali@gmail.com", 123456789, "Lelaki", "2425", "Ijazah", date(2028, 7, 31), "ktc", "S44", "Ya", "Hijau", "15/03/2026"])
    m.append(["Tanpa Emel", "", "0111", "Lelaki", "2425", "Ijazah", "31/07/2028"])
    m.append(["Salah Sesi", "x@gmail.com", "0111", "Lelaki", "2426", "Ijazah", "31/07/2028"])
    m.append(["Ali Dua", "ali@gmail.com", "0111", "Lelaki", "2425", "Ijazah", "31/07/2028"])
    m.append(["Tiada Tamat", "t@gmail.com", "0111", "Perempuan", "2425", "Ijazah", None])
    a = wb.create_sheet("Alumni")
    a.append(["Nama penuh *", "Emel (Google) *", "No. telefon", "Sesi masuk *", "Jurulatih", "Bengkung semasa *"])
    a.append(["Siti", "siti@gmail.com", None, "9495", "Tidak", "Hitam"])
    j = wb.create_sheet("Jawatan")
    j.append(["Emel ahli/alumni *", "Sesi jawatan *", "Peringkat *", "Biro *", "Sekretariat (seki)", "Jawatan *"])
    j.append(["ali@gmail.com", "2425", "Biro", "BLG", "", "Ketua"])
    j.append(["ali@gmail.com", "2425", "Biro", "", "", "Tiada biro"])
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


def test_parse_workbook():
    r = pp.parse_workbook(_book())
    assert [b["name"] for b in r["belts"]] == ["Putih", "Hijau"]          # baris CONTOH diabaikan
    assert [x["email"] for x in r["members"]] == ["ali@gmail.com"]
    ali = r["members"][0]
    assert ali["phone"] == "0123456789" and ali["college"] == "KTC" and ali["is_coach"] and ali["gender"] == "male"
    assert ali["study_end"] == date(2028, 7, 31) and ali["belt_date"] == date(2026, 3, 15)
    assert [x["email"] for x in r["alumni"]] == ["siti@gmail.com"] and r["alumni"][0]["kind"] == "SSG"
    assert r["alumni"][0]["belt"] == "" and r["alumni"][0]["belt_date"] is None   # alumni: tiada bengkung
    msgs = " | ".join(e["msg"] for e in r["errors"])
    for needle in ("Emel tak sah", "Sesi masuk tak sah", "Emel berulang", "Tarikh tamat pengajian wajib", "Biro dan jawatan wajib"):
        assert needle in msgs
    assert len(r["posts"]) == 1
