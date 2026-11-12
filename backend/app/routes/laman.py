"""Muka depan PSSGUTM: pengumuman, kebajikan, teks halaman, maklum balas."""
import json
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models, storage
from ..database import get_db
from ..models_main import Feedback, Notice, PageText
from ..security import get_current_user, require_admin
from ..services import people as pp
from .bookings import save_upload

router = APIRouter(prefix="/laman", tags=["laman"])

KINDS = ("pengumuman", "kebajikan", "event")   # 'kebajikan' ialah bahagian banner bawah (nama boleh diubah admin)
DEFAULT_TITLES = {"pengumuman": "Pengumuman", "event": "Event", "kebajikan": "News",
                  "sistem": "Sistem & Aplikasi", "jadual": "Jadual Latihan"}
PATTERNS = ("batik", "kawung", "sisik", "tumpal", "luk", "polos")
IMG_PREFIXES = ("notice_", "homebg_", "poster_")
PAGES = {"panduan": "Panduan", "hubungi": "Hubungi", "sokongan": "Sokongan"}
DEFAULT_TEXT = {
    "panduan": ("Cara guna PSSGUTM\n\n"
                "1. Log masuk dengan Google guna emel yang didaftarkan dalam senarai ahli.\n"
                "2. Transport: buka Transport, pilih tarikh latihan Rabu/Sabtu dan tandakan pergi atau balik.\n"
                "3. Bayaran: selepas senarai disahkan, bayar kepada BKK dan muat naik resit di Bayaran saya.\n"
                "4. Kehadiran: imbas kod QR yang ditunjukkan oleh AJK/BLG di menu Kod QR.\n"
                "5. Ada masalah atau cadangan? Hantar di Maklum Balas.\n\n"
                "Admin boleh ubah teks ini di Pengurusan persatuan > Laman > Teks halaman."),
    "hubungi": "Hubungi pentadbir PSSGUTM melalui Maklum Balas dalam app ini.",
    "sokongan": "Jika ada masalah teknikal, hantar Maklum Balas dan pentadbir akan membantu.",
}


def _out(n: Notice, full: bool = True) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body if full else n.body[:140],
            "image": n.image, "link": n.link, "date": (n.on_date or n.created_at.date()).isoformat(),
            "active": n.active}


def _get(db, key, default=""):
    row = db.get(models.Setting, key)
    return row.value if row else default


def _set(db, key, value):
    db.merge(models.Setting(key=key, value=value))


def _titles(db) -> dict:
    try:
        saved = json.loads(_get(db, "home_titles", "{}") or "{}")
    except ValueError:
        saved = {}
    return {k: (saved.get(k) or v) for k, v in DEFAULT_TITLES.items()}


def _design(db) -> dict:
    mode = _get(db, "home_mode", "corak")
    pat = _get(db, "home_pattern", "batik")
    return {"mode": mode if mode in ("corak", "gambar") else "corak", "pattern": pat if pat in PATTERNS else "batik",
            "bg": _get(db, "home_bg") or None, "poster": _get(db, "home_poster") or None}


@router.get("/public")
def public_home(db: Session = Depends(get_db)):
    """Kandungan laman depan sebelum log masuk (tiada data ahli)."""
    return _home(db)


@router.get("/home")
def home(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _home(db)


def _home(db):
    q = db.query(Notice).filter(Notice.active.is_(True))
    ann = q.filter(Notice.kind == "pengumuman").order_by(Notice.id.desc()).limit(3).all()
    wel = q.filter(Notice.kind == "kebajikan").order_by(Notice.id.desc()).limit(3).all()
    today = date.today()
    ev = q.filter(Notice.kind == "event").all()
    ev.sort(key=lambda n: ((n.on_date or n.created_at.date()) < today, abs(((n.on_date or n.created_at.date()) - today).days)))
    return {"announcements": [_out(n, False) for n in ann], "welfare": [_out(n, False) for n in wel],
            "events": [_out(n, False) for n in ev[:4]], "titles": _titles(db), "design": _design(db),
            "session": {"code": (c := pp.session_now(db, date.today())), "label": pp.session_label(c)}}


class TitlesIn(BaseModel):
    titles: dict[str, str]


@router.put("/titles", dependencies=[Depends(require_admin)])
def set_titles(data: TitlesIn, db: Session = Depends(get_db)):
    clean = {k: v.strip()[:40] for k, v in data.titles.items() if k in DEFAULT_TITLES and v.strip()}
    _set(db, "home_titles", json.dumps(clean, ensure_ascii=False))
    db.commit()
    return _titles(db)


@router.put("/design", dependencies=[Depends(require_admin)])
async def set_design(mode: str = Form("corak"), pattern: str = Form("batik"), remove_bg: bool = Form(False),
                     remove_poster: bool = Form(False), bg: UploadFile | None = File(None),
                     poster: UploadFile | None = File(None), db: Session = Depends(get_db)):
    if mode not in ("corak", "gambar") or pattern not in PATTERNS:
        raise HTTPException(400, "Pilihan tak sah")
    _set(db, "home_mode", mode)
    _set(db, "home_pattern", pattern)
    for key, up, rm, prefix in (("home_bg", bg, remove_bg, "homebg_"), ("home_poster", poster, remove_poster, "poster_")):
        old = _get(db, key)
        if up is not None and up.filename:
            new = await save_upload(up, prefix, images_only=True)
            if old:
                storage.delete(old)
            _set(db, key, new)
        elif rm and old:
            storage.delete(old)
            _set(db, key, "")
    db.commit()
    return _design(db)


@router.get("/notices")
def notices(kind: str = "pengumuman", all: bool = False, user: models.User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    if kind not in KINDS:
        raise HTTPException(400, "Jenis tak sah")
    q = db.query(Notice).filter(Notice.kind == kind)
    if not (all and user.role == models.Role.admin):
        q = q.filter(Notice.active.is_(True))
    return [_out(n) for n in q.order_by(Notice.id.desc()).limit(100)]


@router.get("/img/{name}")
def img(name: str):
    """Gambar pengumuman/kebajikan ialah maklumat umum ahli; nama fail rawak."""
    if not name.startswith(IMG_PREFIXES):
        raise HTTPException(404, "Tak jumpa")
    return storage.serve(name, "Gambar tiada")


async def _save(n: Notice, kind, title, body, link, on_date, active, file):
    if kind not in KINDS:
        raise HTTPException(400, "Jenis tak sah")
    try:
        d = pp.parse_date(on_date) if on_date else None
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not title.strip():
        raise HTTPException(400, "Tajuk wajib")
    n.kind, n.title, n.body, n.link, n.on_date, n.active = kind, title.strip()[:160], body.strip(), link.strip()[:300], d, active
    if file is not None and file.filename:
        new = await save_upload(file, "notice_", images_only=True)
        if n.image:
            storage.delete(n.image)
        n.image = new


@router.post("/notices", dependencies=[Depends(require_admin)])
async def add_notice(kind: str = Form("pengumuman"), title: str = Form(...), body: str = Form(""), link: str = Form(""),
                     on_date: str = Form(""), active: bool = Form(True), file: UploadFile | None = File(None),
                     db: Session = Depends(get_db)):
    n = Notice()
    await _save(n, kind, title, body, link, on_date, active, file)
    db.add(n)
    db.commit()
    return _out(n)


@router.put("/notices/{nid}", dependencies=[Depends(require_admin)])
async def edit_notice(nid: int, kind: str = Form("pengumuman"), title: str = Form(...), body: str = Form(""),
                      link: str = Form(""), on_date: str = Form(""), active: bool = Form(True),
                      remove_image: bool = Form(False), file: UploadFile | None = File(None),
                      db: Session = Depends(get_db)):
    n = db.get(Notice, nid)
    if n is None:
        raise HTTPException(404, "Tak jumpa")
    if remove_image and n.image:
        storage.delete(n.image)
        n.image = None
    await _save(n, kind, title, body, link, on_date, active, file)
    db.commit()
    return _out(n)


@router.delete("/notices/{nid}", dependencies=[Depends(require_admin)])
def delete_notice(nid: int, db: Session = Depends(get_db)):
    n = db.get(Notice, nid)
    if n:
        if n.image:
            storage.delete(n.image)
        db.delete(n)
        db.commit()
    return {"ok": True}


class TextIn(BaseModel):
    body: str = Field(max_length=8000)


@router.get("/page/{key}")
def page(key: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if key not in PAGES:
        raise HTTPException(404, "Halaman tak jumpa")
    row = db.get(PageText, key)
    return {"key": key, "title": PAGES[key], "body": row.body if row else DEFAULT_TEXT[key]}


@router.put("/page/{key}", dependencies=[Depends(require_admin)])
def set_page(key: str, data: TextIn, db: Session = Depends(get_db)):
    if key not in PAGES:
        raise HTTPException(404, "Halaman tak jumpa")
    db.merge(PageText(key=key, body=data.body))
    db.commit()
    return {"ok": True}


class FeedbackIn(BaseModel):
    message: str = Field(min_length=3, max_length=1500)


@router.post("/feedback")
def send_feedback(data: FeedbackIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.add(Feedback(user_id=user.id, message=data.message.strip()))
    db.commit()
    return {"ok": True}


@router.get("/feedback", dependencies=[Depends(require_admin)])
def list_feedback(db: Session = Depends(get_db)):
    rows = db.query(Feedback).order_by(Feedback.id.desc()).limit(200).all()
    out = []
    for f in rows:
        u = db.get(models.User, f.user_id)
        out.append({"id": f.id, "message": f.message, "read": f.read, "at": f.created_at.isoformat(),
                    "name": u.name if u else "", "member_no": u.member_no if u else ""})
    return out


@router.put("/feedback/{fid}", dependencies=[Depends(require_admin)])
def mark_feedback(fid: int, read: bool = True, db: Session = Depends(get_db)):
    f = db.get(Feedback, fid)
    if f:
        f.read = read
        db.commit()
    return {"ok": True}
