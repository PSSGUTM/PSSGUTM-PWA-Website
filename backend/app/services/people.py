"""Logik rekod ahli/alumni PSSGUTM (tanpa database supaya senang diuji).

- Sesi masuk: 4 digit, dua digit tahun mula + dua digit tahun akhir (cth 9495, 0001, 2425).
- Ahli semasa: SG + sesi + urutan 3 digit (cth SG2425001). Alumni: SSG + sesi sahaja (cth SSG9495), tidak unik.
- Import Excel: lembaran 'Bengkung', 'Ahli semasa', 'Alumni', 'Jawatan' (lihat format-import-PSSGUTM.xlsx).
"""
import io
import re
from datetime import date, datetime

SHEET_MEMBERS = "Ahli semasa"
SHEET_ALUMNI = "Alumni"
SHEET_POSTS = "Jawatan"
SHEET_BELTS = "Bengkung"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_session(s) -> bool:
    s = str(s or "").strip()
    return bool(re.fullmatch(r"\d{4}", s)) and (int(s[:2]) + 1) % 100 == int(s[2:])


def session_label(s: str) -> str:
    """9495 -> 1994/95 ; 0001 -> 2000/01 (abad ditekan: 70-99 = 19xx, 00-69 = 20xx)."""
    a = int(s[:2])
    return f"{1900 + a if a >= 70 else 2000 + a}/{s[2:]}"


def sg_prefix(session: str) -> str:
    return f"SG{session}"


def ssg_no(session: str) -> str:
    return f"SSG{session}"


def next_sg_no(session: str, existing) -> str:
    """No. SG seterusnya bagi sesi itu, ikut nombor tertinggi sedia ada (tak guna semula nombor)."""
    pre = sg_prefix(session)
    top = 0
    for n in existing:
        n = (n or "").upper()
        if n.startswith(pre) and n[len(pre):].isdigit():
            top = max(top, int(n[len(pre):]))
    return f"{pre}{top + 1:03d}"


def clean_phone(v) -> str:
    d = re.sub(r"[^\d+]", "", str(v or ""))
    if d and not d.startswith("+") and not d.startswith("0") and len(d) >= 9:
        d = "0" + d   # Excel buang sifar di depan
    return d


def parse_date(v) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = str(v).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Tarikh tak sah: {t} (guna HH/BB/TTTT)")


def norm_gender(v) -> str | None:
    t = str(v or "").strip().lower()
    if t in ("lelaki", "male", "l", "m"):
        return "male"
    if t in ("perempuan", "female", "p", "f"):
        return "female"
    return None


def yes(v) -> bool:
    return str(v or "").strip().lower() in ("ya", "y", "yes", "true", "1")


def due_for_conversion(kind: str, study_end, today: date) -> bool:
    """Ahli semasa (SG) yang tarikh tamat pengajiannya sudah tiba: perlu disahkan sama ada sudah tamat."""
    return kind == "SG" and study_end is not None and study_end <= today


def _hdr(v) -> str:
    return re.sub(r"\s*\*\s*$", "", str(v or "")).strip().lower()


def _rows(ws):
    """Baris data dengan nombor baris Excel, abaikan baris kosong dan baris CONTOH."""
    it = ws.iter_rows(values_only=True)
    try:
        head = [_hdr(h) for h in next(it)]
    except StopIteration:
        return
    for i, row in enumerate(it, start=2):
        d = {head[j]: row[j] for j in range(min(len(head), len(row))) if head[j]}
        if not any(str(v).strip() for v in d.values() if v is not None):
            continue
        first = str(next(iter(d.values()), "") or "")
        if first.strip().upper().startswith("CONTOH"):
            continue
        yield i, d


def _s(d, key) -> str:
    v = d.get(key)
    return "" if v is None else str(v).strip()


def parse_workbook(content: bytes) -> dict:
    """Baca fail import. Return {belts, members, alumni, posts, errors}; errors = [{sheet,row,msg}]."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    out = {"belts": [], "members": [], "alumni": [], "posts": [], "errors": []}

    def err(sheet, row, msg):
        out["errors"].append({"sheet": sheet, "row": row, "msg": msg})

    seen = set()
    if SHEET_BELTS in wb.sheetnames:
        for r, d in _rows(wb[SHEET_BELTS]):
            name = _s(d, "nama bengkung") or _s(d, "bengkung") or _s(d, "nama")
            if not name:
                err(SHEET_BELTS, r, "Nama bengkung kosong")
            else:
                out["belts"].append({"name": name})

    def person(sheet, r, d, kind):
        email = _s(d, "emel (google)").lower() or _s(d, "emel").lower()
        name = _s(d, "nama penuh") or _s(d, "nama")
        if not name:
            return err(sheet, r, "Nama kosong")
        if not EMAIL_RE.match(email):
            return err(sheet, r, f"Emel tak sah: {email or '(kosong)'}")
        if email in seen:
            return err(sheet, r, f"Emel berulang dalam fail: {email}")
        sess = _s(d, "sesi masuk")
        if not valid_session(sess):
            return err(sheet, r, f"Sesi masuk tak sah: {sess or '(kosong)'} (cth 2425)")
        try:
            end = parse_date(d.get("tarikh tamat pengajian"))
            belt_date = parse_date(d.get("tarikh naik bengkung"))
        except ValueError as e:
            return err(sheet, r, str(e))
        g = norm_gender(d.get("jantina"))
        if kind == "SG":
            if g is None:
                return err(sheet, r, "Jantina mesti Lelaki atau Perempuan")
            if end is None:
                return err(sheet, r, "Tarikh tamat pengajian wajib untuk ahli semasa")
        seen.add(email)
        out["members" if kind == "SG" else "alumni"].append({
            "row": r, "name": name, "email": email, "phone": clean_phone(d.get("no. telefon")),
            "gender": g, "intake": sess, "kind": kind, "study_end": end,
            "study_level": _s(d, "peringkat pengajian"), "college": _s(d, "kolej").upper(),
            "block": _s(d, "blok"), "is_coach": yes(d.get("jurulatih")),
            # Bengkung hanya untuk ahli semasa; alumni tidak disimpan (keputusan persatuan: isu sensitif)
            "belt": _s(d, "bengkung semasa") if kind == "SG" else "",
            "belt_date": belt_date if kind == "SG" else None, "note": _s(d, "catatan"),
        })

    for sheet, kind in ((SHEET_MEMBERS, "SG"), (SHEET_ALUMNI, "SSG")):
        if sheet in wb.sheetnames:
            for r, d in _rows(wb[sheet]):
                person(sheet, r, d, kind)

    if SHEET_POSTS in wb.sheetnames:
        for r, d in _rows(wb[SHEET_POSTS]):
            email = _s(d, "emel ahli/alumni").lower()
            sess = _s(d, "sesi jawatan")
            level = _s(d, "peringkat")
            title = _s(d, "jawatan")
            biro = _s(d, "biro")
            if not EMAIL_RE.match(email):
                err(SHEET_POSTS, r, f"Emel tak sah: {email or '(kosong)'}")
            elif not valid_session(sess):
                err(SHEET_POSTS, r, f"Sesi jawatan tak sah: {sess or '(kosong)'}")
            elif not title or not biro:
                err(SHEET_POSTS, r, "Biro dan jawatan wajib")
            else:
                out["posts"].append({"row": r, "email": email, "session": sess, "level": level or "Biro",
                                     "biro": biro, "seki": _s(d, "sekretariat (seki)"), "title": title})
    return out


def session_year(s: str) -> int:
    """Tahun mula sesi (untuk menyusun): 9495 -> 1994, 0001 -> 2000."""
    a = int(s[:2])
    return 1900 + a if a >= 70 else 2000 + a


def current_session(today: date) -> str:
    """Sesi akademik semasa (bermula 1 Ogos): Nov 2026 -> '2627'."""
    y = today.year if today.month >= 8 else today.year - 1
    return f"{y % 100:02d}{(y + 1) % 100:02d}"


def session_now(db, today: date) -> str:
    """Sesi semasa: ditetapkan admin (Setting 'current_session') jika ada, jika tidak ikut tarikh (1 Ogos)."""
    from .. import models
    row = db.get(models.Setting, "current_session")
    if row is not None and valid_session(row.value):
        return row.value.strip()
    return current_session(today)


def session_start(code: str) -> date:
    return date(session_year(code), 8, 1)
