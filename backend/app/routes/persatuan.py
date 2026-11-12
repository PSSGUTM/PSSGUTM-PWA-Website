"""Modul utama PSSGUTM: ahli/alumni, bengkung, jawatan, import, SG->SSG, kehadiran (QR), inventori."""
import csv
import io
import secrets
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, storage
from ..database import get_db
from ..models_main import (AttendRecord, Attendance, BeltHistory, BeltLevel, Biro, Item, Loan, Person, Post)
from ..security import get_current_user, require_admin
from ..services import people as pp
from ..services import booking as svc
from .bookings import save_upload

router = APIRouter(prefix="/persatuan", tags=["persatuan"])

DEFAULT_BIROS = (("BKK", False, False), ("BIT", False, False), ("BLG", True, False))


def ensure_seed(db: Session) -> None:
    """Biro asas (admin boleh ubah nama dan kebenaran). Dijalankan setiap deploy, tidak menimpa suntingan."""
    if db.query(Biro).count() == 0:
        for name, att, inv in DEFAULT_BIROS:
            db.add(Biro(name=name, can_attendance=att, can_inventory=inv))
        db.commit()


# ---------------------------------------------------------------- bantuan

def person_of(db: Session, user: models.User) -> Person | None:
    return db.query(Person).filter(func.lower(Person.email) == (user.email or "").lower()).first()


def can(db: Session, user: models.User, flag: str) -> bool:
    """Admin sentiasa boleh. Selain itu: ada jawatan semasa dalam biro (atau seki di bawah biro) yang diberi kebenaran."""
    if user.role == models.Role.admin:
        return True
    p = person_of(db, user)
    if p is None:
        return False
    cur_sess = pp.session_now(db, svc.today_my())
    if flag == "can_attendance":      # semua pemegang jawatan semasa (jawatankuasa = MT + biro + seki) boleh ambil kehadiran
        return db.query(Post).filter_by(person_id=p.id, session=cur_sess, current=True).first() is not None
    for post in db.query(Post).filter_by(person_id=p.id, session=cur_sess, current=True):
        b = db.get(Biro, post.biro_id) if post.biro_id else None
        while b is not None:
            if getattr(b, flag):
                return True
            b = db.get(Biro, b.parent_id) if b.parent_id else None
    return False


def need(flag: str):
    def dep(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
        if not can(db, user, flag):
            raise HTTPException(403, "Tiada kebenaran")
        return user
    return dep


def _belt_name(db, p):
    b = db.get(BeltLevel, p.belt_id) if p.belt_id else None
    return b.name if b else ""


def person_out(db, p: Person, today: date | None = None) -> dict:
    today = today or svc.today_my()
    return {"id": p.id, "name": p.name, "email": p.email, "phone": p.phone, "gender": p.gender,
            "intake": p.intake, "intake_label": pp.session_label(p.intake) if pp.valid_session(p.intake) else "",
            "kind": p.kind, "member_no": p.member_no,
            "study_end": p.study_end.isoformat() if p.study_end else None, "study_level": p.study_level,
            "college": p.college, "block": p.block, "is_coach": p.is_coach,
            "belt_id": p.belt_id, "belt": _belt_name(db, p),
            "belt_date": p.belt_date.isoformat() if p.belt_date else None, "note": p.note, "active": p.active,
            "due": pp.due_for_conversion(p.kind, p.study_end, today)}


def _posts_out(db, person_id):
    out = []
    for x in db.query(Post).filter_by(person_id=person_id).order_by(Post.id.desc()):
        b = db.get(Biro, x.biro_id) if x.biro_id else None
        parent = db.get(Biro, b.parent_id) if b and b.parent_id else None
        out.append({"id": x.id, "session": x.session, "label": pp.session_label(x.session), "level": x.level,
                    "biro": (parent.name if parent else (b.name if b else "")),
                    "seki": (b.name if parent else ""), "title": x.title, "current": x.current})
    return out


# ---------------------------------------------------------------- saya

@router.get("/me")
def me(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = person_of(db, user)
    n = db.query(AttendRecord).filter_by(person_id=p.id).count() if p else 0
    return {"person": person_out(db, p) if p else None, "posts": _posts_out(db, p.id) if p else [],
            "attended": n,
            "perms": {"admin": user.role == models.Role.admin, "attendance": can(db, user, "can_attendance"),
                      "inventory": can(db, user, "can_inventory")}}


@router.get("/me/belts")
def my_belts(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = person_of(db, user)
    if not p or p.kind != "SG":
        return []
    rows = db.query(BeltHistory).filter_by(person_id=p.id).order_by(BeltHistory.id.desc())
    out = []
    for h in rows:
        b = db.get(BeltLevel, h.belt_id) if h.belt_id else None
        out.append({"belt": b.name if b else "", "date": h.on_date.isoformat() if h.on_date else None})
    return out


# ---------------------------------------------------------------- bengkung

class BeltIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.get("/belts")
def list_belts(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": b.id, "name": b.name, "rank": b.rank}
            for b in db.query(BeltLevel).order_by(BeltLevel.rank, BeltLevel.id)]


@router.post("/belts", dependencies=[Depends(require_admin)])
def add_belt(data: BeltIn, db: Session = Depends(get_db)):
    name = data.name.strip()
    if db.query(BeltLevel).filter(func.lower(BeltLevel.name) == name.lower()).first():
        raise HTTPException(409, "Nama bengkung itu sudah ada")
    top = db.query(func.max(BeltLevel.rank)).scalar()
    b = BeltLevel(name=name, rank=(top if top is not None else -1) + 1)
    db.add(b)
    db.commit()
    return {"id": b.id}


@router.put("/belts/order", dependencies=[Depends(require_admin)])
def order_belts(ids: list[int], db: Session = Depends(get_db)):
    for i, bid in enumerate(ids):
        b = db.get(BeltLevel, bid)
        if b:
            b.rank = i
    db.commit()
    return {"ok": True}


@router.put("/belts/{bid}", dependencies=[Depends(require_admin)])
def rename_belt(bid: int, data: BeltIn, db: Session = Depends(get_db)):
    b = db.get(BeltLevel, bid)
    if b is None:
        raise HTTPException(404, "Tak jumpa")
    name = data.name.strip()
    other = db.query(BeltLevel).filter(func.lower(BeltLevel.name) == name.lower(), BeltLevel.id != bid).first()
    if other:
        raise HTTPException(409, "Nama bengkung itu sudah ada")
    b.name = name
    db.commit()
    return {"ok": True}


@router.delete("/belts/{bid}", dependencies=[Depends(require_admin)])
def delete_belt(bid: int, db: Session = Depends(get_db)):
    if db.query(Person).filter_by(belt_id=bid).count():
        raise HTTPException(400, "Masih ada ahli pada peringkat ini. Tukar peringkat mereka dahulu.")
    b = db.get(BeltLevel, bid)
    if b:
        db.query(BeltHistory).filter_by(belt_id=bid).delete()
        db.delete(b)
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- ahli & alumni

class PersonIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=120)
    phone: str = ""
    gender: str | None = None
    intake: str
    kind: str = "SG"
    study_end: date | None = None
    study_level: str = ""
    college: str = ""
    block: str = ""
    is_coach: bool = False
    belt_id: int | None = None
    belt_date: date | None = None
    note: str = ""
    active: bool = True


def _apply(db, p: Person, d: PersonIn, existing_sg: set[str]):
    if not pp.valid_session(d.intake):
        raise HTTPException(400, "Sesi masuk tak sah (4 digit, cth 2425)")
    if d.kind not in ("SG", "SSG"):
        raise HTTPException(400, "Jenis mesti SG atau SSG")
    if not pp.EMAIL_RE.match(d.email.strip()):
        raise HTTPException(400, "Emel tak sah")
    if d.kind == "SG" and d.gender not in ("male", "female"):
        raise HTTPException(400, "Jantina diperlukan untuk ahli semasa")
    old_kind, old_intake = p.kind, p.intake
    p.name = d.name.strip(); p.email = d.email.strip().lower(); p.phone = pp.clean_phone(d.phone)
    p.gender = d.gender; p.intake = d.intake; p.kind = d.kind
    p.study_end = d.study_end if d.kind == "SG" else None
    p.study_level = d.study_level.strip(); p.college = d.college.strip().upper(); p.block = d.block.strip()
    p.is_coach = d.is_coach; p.note = d.note.strip(); p.active = d.active
    if d.belt_id is not None and db.get(BeltLevel, d.belt_id) is None:
        raise HTTPException(400, "Peringkat bengkung tak wujud")
    if d.kind == "SSG":      # alumni: bengkung tidak disimpan
        d.belt_id, d.belt_date = None, None
    p.belt_id, p.belt_date = d.belt_id, d.belt_date
    if not p.member_no or old_kind != p.kind or old_intake != p.intake:
        if p.kind == "SSG":
            p.member_no = pp.ssg_no(p.intake)
        else:
            p.member_no = pp.next_sg_no(p.intake, existing_sg)
            existing_sg.add(p.member_no)


def _sg_numbers(db) -> set[str]:
    return {n for (n,) in db.query(Person.member_no).filter(Person.member_no.like("SG%")) if n}


@router.get("/people", dependencies=[Depends(require_admin)])
def list_people(q: str = "", kind: str = "", due: bool = False, limit: int = 300, offset: int = 0,
                db: Session = Depends(get_db)):
    qs = db.query(Person)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        qs = qs.filter(func.lower(Person.name).like(like) | func.lower(Person.email).like(like)
                       | func.lower(Person.member_no).like(like))
    if kind in ("SG", "SSG"):
        qs = qs.filter(Person.kind == kind)
    total = qs.count()
    rows = qs.order_by(func.lower(Person.name)).offset(max(offset, 0)).limit(min(max(limit, 1), 500)).all()
    today = svc.today_my()
    items = [person_out(db, p, today) for p in rows]
    if due:
        items = [i for i in items if i["due"]]
    return {"total": total, "items": items}


@router.get("/people/search")
def search_people(q: str = "", user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Carian ringkas (nama) untuk kehadiran manual dan pinjaman: pengurus kehadiran/inventori sahaja."""
    if not (can(db, user, "can_attendance") or can(db, user, "can_inventory")):
        raise HTTPException(403, "Tiada kebenaran")
    if len(q.strip()) < 2:
        return []
    like = f"%{q.strip().lower()}%"
    rows = (db.query(Person).filter(Person.active.is_(True), func.lower(Person.name).like(like))
            .order_by(func.lower(Person.name)).limit(20).all())
    return [{"id": p.id, "name": p.name, "member_no": p.member_no, "kind": p.kind} for p in rows]


@router.post("/people", dependencies=[Depends(require_admin)])
def create_person(data: PersonIn, db: Session = Depends(get_db)):
    if db.query(Person).filter(func.lower(Person.email) == data.email.strip().lower()).first():
        raise HTTPException(409, "Emel itu sudah ada dalam senarai")
    p = Person()
    db.add(p)
    sg = _sg_numbers(db)
    _apply(db, p, data, sg)
    db.flush()
    if p.belt_id:
        db.add(BeltHistory(person_id=p.id, belt_id=p.belt_id, on_date=p.belt_date))
    db.commit()
    return person_out(db, p)


@router.put("/people/{pid}", dependencies=[Depends(require_admin)])
def update_person(pid: int, data: PersonIn, db: Session = Depends(get_db)):
    p = db.get(Person, pid)
    if p is None:
        raise HTTPException(404, "Tak jumpa")
    other = db.query(Person).filter(func.lower(Person.email) == data.email.strip().lower(), Person.id != pid).first()
    if other:
        raise HTTPException(409, "Emel itu dipakai rekod lain")
    prev = (p.belt_id, p.belt_date)
    _apply(db, p, data, _sg_numbers(db))
    if p.belt_id and (p.belt_id, p.belt_date) != prev:
        db.add(BeltHistory(person_id=p.id, belt_id=p.belt_id, on_date=p.belt_date))
    db.commit()
    return person_out(db, p)


@router.get("/people/{pid}", dependencies=[Depends(require_admin)])
def get_person(pid: int, db: Session = Depends(get_db)):
    p = db.get(Person, pid)
    if p is None:
        raise HTTPException(404, "Tak jumpa")
    return {"person": person_out(db, p), "posts": _posts_out(db, pid),
            "attended": db.query(AttendRecord).filter_by(person_id=pid).count()}


# ---------------------------------------------------------------- SG -> SSG

class ConvertIn(BaseModel):
    action: str                 # convert | extend
    new_end: date | None = None


@router.get("/conversions", dependencies=[Depends(require_admin)])
def conversions(db: Session = Depends(get_db)):
    today = svc.today_my()
    rows = (db.query(Person).filter(Person.kind == "SG", Person.study_end.isnot(None), Person.study_end <= today,
                                    Person.active.is_(True)).order_by(Person.study_end, func.lower(Person.name)))
    return [person_out(db, p, today) for p in rows]


@router.post("/conversions/{pid}", dependencies=[Depends(require_admin)])
def convert(pid: int, data: ConvertIn, db: Session = Depends(get_db)):
    p = db.get(Person, pid)
    if p is None or p.kind != "SG":
        raise HTTPException(404, "Ahli semasa tak jumpa")
    if data.action == "convert":
        p.kind = "SSG"
        p.member_no = pp.ssg_no(p.intake)
        p.study_end = None
        p.belt_id, p.belt_date = None, None            # alumni: bengkung tidak disimpan
        db.query(BeltHistory).filter_by(person_id=p.id).delete()
    elif data.action == "extend":
        if data.new_end is None or data.new_end <= svc.today_my():
            raise HTTPException(400, "Tarikh tamat baharu mesti selepas hari ini")
        p.study_end = data.new_end
    else:
        raise HTTPException(400, "Tindakan tak sah")
    db.commit()
    return person_out(db, p)


# ---------------------------------------------------------------- import Excel

@router.post("/import", dependencies=[Depends(require_admin)])
async def import_xlsx(file: UploadFile = File(...), dry_run: bool = Form(True), db: Session = Depends(get_db)):
    raw = await file.read(8_000_001)
    if len(raw) > 8_000_000:
        raise HTTPException(413, "Fail terlalu besar")
    try:
        parsed = pp.parse_workbook(raw)
    except Exception:
        raise HTTPException(400, "Fail tak boleh dibaca. Guna format-import-PSSGUTM.xlsx (.xlsx).")
    stats = {"belts_new": 0, "people_new": 0, "people_updated": 0, "posts_new": 0, "belts_created_from_people": 0}

    # bengkung (ikut susunan dalam fail: bawah ke atas)
    def belt_get(name: str, create_flag: str | None = None):
        row = db.query(BeltLevel).filter(func.lower(BeltLevel.name) == name.lower()).first()
        if row is None:
            top = db.query(func.max(BeltLevel.rank)).scalar()
            row = BeltLevel(name=name, rank=(top if top is not None else -1) + 1)
            db.add(row)
            db.flush()
            stats[create_flag or "belts_new"] += 1
        return row

    for b in parsed["belts"]:
        belt_get(b["name"])

    sg = _sg_numbers(db)
    by_email = {}
    for rec in parsed["members"] + parsed["alumni"]:
        p = db.query(Person).filter(func.lower(Person.email) == rec["email"]).first()
        new = p is None
        if new:
            p = Person(email=rec["email"], name=rec["name"], intake=rec["intake"], kind=rec["kind"])
            db.add(p)
        old = (p.kind, p.intake)
        p.name, p.phone, p.gender = rec["name"], rec["phone"] or p.phone, rec["gender"] or p.gender
        p.intake, p.kind, p.study_end = rec["intake"], rec["kind"], rec["study_end"]
        p.study_level, p.college, p.block = rec["study_level"], rec["college"], rec["block"]
        p.is_coach, p.note = rec["is_coach"], rec["note"]
        if not p.member_no or old != (p.kind, p.intake):
            if p.kind == "SSG":
                p.member_no = pp.ssg_no(p.intake)
            else:
                p.member_no = pp.next_sg_no(p.intake, sg)
                sg.add(p.member_no)
        if rec["belt"] and rec["belt"].lower() != "tidak diketahui":
            belt = belt_get(rec["belt"], "belts_created_from_people")
            if p.belt_id != belt.id or p.belt_date != rec["belt_date"]:
                p.belt_id, p.belt_date = belt.id, rec["belt_date"]
                db.flush()
                db.add(BeltHistory(person_id=p.id, belt_id=belt.id, on_date=rec["belt_date"]))
        db.flush()
        by_email[rec["email"]] = p
        stats["people_new" if new else "people_updated"] += 1

    latest = max((pp.session_year(x["session"]) for x in parsed["posts"]), default=0)
    errors = list(parsed["errors"])
    for x in parsed["posts"]:
        p = by_email.get(x["email"]) or db.query(Person).filter(func.lower(Person.email) == x["email"]).first()
        if p is None:
            errors.append({"sheet": pp.SHEET_POSTS, "row": x["row"], "msg": f"Emel tiada dalam senarai ahli/alumni: {x['email']}"})
            continue
        biro = db.query(Biro).filter(func.lower(Biro.name) == x["biro"].lower()).first()
        if biro is None:
            biro = Biro(name=x["biro"])
            db.add(biro)
            db.flush()
        target = biro
        if x["seki"]:
            target = db.query(Biro).filter(func.lower(Biro.name) == x["seki"].lower()).first()
            if target is None:
                target = Biro(name=x["seki"], parent_id=biro.id)
                db.add(target)
                db.flush()
        level = "Sekretariat" if x["seki"] else x["level"]
        dup = db.query(Post).filter_by(person_id=p.id, session=x["session"], biro_id=target.id, title=x["title"]).first()
        if dup:
            continue
        db.add(Post(person_id=p.id, session=x["session"], level=level, biro_id=target.id, title=x["title"],
                    current=pp.session_year(x["session"]) == latest))
        stats["posts_new"] += 1
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return {"dry_run": dry_run, "stats": stats, "errors": errors[:200], "error_count": len(errors),
            "counts": {"belts": len(parsed["belts"]), "members": len(parsed["members"]),
                       "alumni": len(parsed["alumni"]), "posts": len(parsed["posts"])}}


# ---------------------------------------------------------------- biro, seki, jawatan

class BiroIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: int | None = None
    can_attendance: bool = False
    can_inventory: bool = False


@router.get("/biros")
def list_biros(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": b.id, "name": b.name, "parent_id": b.parent_id, "can_attendance": b.can_attendance,
             "can_inventory": b.can_inventory} for b in db.query(Biro).order_by(Biro.parent_id.isnot(None), Biro.name)]


@router.post("/biros", dependencies=[Depends(require_admin)])
def add_biro(data: BiroIn, db: Session = Depends(get_db)):
    if db.query(Biro).filter(func.lower(Biro.name) == data.name.strip().lower()).first():
        raise HTTPException(409, "Nama itu sudah ada")
    b = Biro(name=data.name.strip(), parent_id=data.parent_id, can_attendance=data.can_attendance,
             can_inventory=data.can_inventory)
    db.add(b)
    db.commit()
    return {"id": b.id}


@router.put("/biros/{bid}", dependencies=[Depends(require_admin)])
def edit_biro(bid: int, data: BiroIn, db: Session = Depends(get_db)):
    b = db.get(Biro, bid)
    if b is None:
        raise HTTPException(404, "Tak jumpa")
    other = db.query(Biro).filter(func.lower(Biro.name) == data.name.strip().lower(), Biro.id != bid).first()
    if other:
        raise HTTPException(409, "Nama itu sudah ada")
    b.name, b.parent_id = data.name.strip(), (data.parent_id if data.parent_id != bid else None)
    b.can_attendance, b.can_inventory = data.can_attendance, data.can_inventory
    db.commit()
    return {"ok": True}


@router.delete("/biros/{bid}", dependencies=[Depends(require_admin)])
def delete_biro(bid: int, db: Session = Depends(get_db)):
    if db.query(Post).filter_by(biro_id=bid).count() or db.query(Biro).filter_by(parent_id=bid).count():
        raise HTTPException(400, "Masih ada jawatan atau seki di bawahnya")
    b = db.get(Biro, bid)
    if b:
        db.delete(b)
        db.commit()
    return {"ok": True}


class PostIn(BaseModel):
    person_id: int
    session: str
    level: str = "Biro"
    biro_id: int | None = None
    title: str = Field(min_length=1, max_length=80)
    current: bool = True


@router.post("/posts", dependencies=[Depends(require_admin)])
def add_post(data: PostIn, db: Session = Depends(get_db)):
    if not pp.valid_session(data.session):
        raise HTTPException(400, "Sesi tak sah (cth 2425)")
    if db.get(Person, data.person_id) is None or (data.biro_id and db.get(Biro, data.biro_id) is None):
        raise HTTPException(404, "Orang atau biro tak jumpa")
    x = Post(person_id=data.person_id, session=data.session, level=data.level, biro_id=data.biro_id,
             title=data.title.strip(), current=data.current)
    db.add(x)
    db.commit()
    return {"id": x.id}


@router.put("/posts/{xid}", dependencies=[Depends(require_admin)])
def edit_post(xid: int, current: bool, db: Session = Depends(get_db)):
    x = db.get(Post, xid)
    if x is None:
        raise HTTPException(404, "Tak jumpa")
    x.current = current
    db.commit()
    return {"ok": True}


@router.delete("/posts/{xid}", dependencies=[Depends(require_admin)])
def delete_post(xid: int, db: Session = Depends(get_db)):
    x = db.get(Post, xid)
    if x:
        db.delete(x)
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- kehadiran

class AttIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    on_date: date


def _att_out(db, a: Attendance):
    return {"id": a.id, "title": a.title, "date": a.on_date.isoformat(), "open": a.open, "token": a.token,
            "count": db.query(AttendRecord).filter_by(attendance_id=a.id).count()}


@router.get("/attendances")
def list_att(user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    return [_att_out(db, a) for a in db.query(Attendance).order_by(Attendance.on_date.desc(), Attendance.id.desc()).limit(100)]


@router.post("/attendances")
def create_att(data: AttIn, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = Attendance(title=data.title.strip(), on_date=data.on_date, token=secrets.token_urlsafe(12), created_by=user.id)
    db.add(a)
    db.commit()
    return _att_out(db, a)


def _att(db, aid) -> Attendance:
    a = db.get(Attendance, aid)
    if a is None:
        raise HTTPException(404, "Kehadiran tak jumpa")
    return a


@router.get("/attendances/{aid}")
def att_detail(aid: int, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = _att(db, aid)
    rows = (db.query(AttendRecord, Person).join(Person, Person.id == AttendRecord.person_id)
            .filter(AttendRecord.attendance_id == aid).order_by(func.lower(Person.name)).all())
    return {**_att_out(db, a), "records": [
        {"id": r.id, "person_id": p.id, "name": p.name, "member_no": p.member_no, "kind": p.kind,
         "manual": r.manual, "at": r.at.isoformat()} for r, p in rows]}


@router.get("/attendances/{aid}/qr")
def att_qr(aid: int, base: str, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = _att(db, aid)
    if not base.startswith(("http://", "https://")):
        raise HTTPException(400, "Alamat asas tak sah")
    url = f"{base.rstrip('/')}/hadir/{a.token}"
    img = None
    try:
        import segno
        img = segno.make(url, error="m").svg_data_uri(scale=8, border=2)
    except Exception:
        img = None   # pustaka QR tiada: paparkan pautan sahaja
    return {"url": url, "image": img}


@router.put("/attendances/{aid}/open")
def att_open(aid: int, open: bool, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = _att(db, aid)
    a.open = open
    db.commit()
    return _att_out(db, a)


class AddIn(BaseModel):
    person_id: int


@router.post("/attendances/{aid}/add")
def att_add(aid: int, data: AddIn, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    _att(db, aid)
    if db.get(Person, data.person_id) is None:
        raise HTTPException(404, "Orang tak jumpa")
    if db.query(AttendRecord).filter_by(attendance_id=aid, person_id=data.person_id).first():
        return {"ok": True, "already": True}
    db.add(AttendRecord(attendance_id=aid, person_id=data.person_id, manual=True))
    db.commit()
    return {"ok": True}


@router.delete("/attendances/{aid}/records/{rid}")
def att_remove(aid: int, rid: int, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    r = db.get(AttendRecord, rid)
    if r and r.attendance_id == aid:
        db.delete(r)
        db.commit()
    return {"ok": True}


@router.delete("/attendances/{aid}")
def att_delete(aid: int, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = _att(db, aid)
    db.query(AttendRecord).filter_by(attendance_id=aid).delete()
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.get("/attendances/{aid}/csv")
def att_csv(aid: int, user: models.User = Depends(need("can_attendance")), db: Session = Depends(get_db)):
    a = att_detail(aid, user, db)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Nama", "No. ahli", "Jenis", "Cara", "Masa"])
    for r in a["records"]:
        w.writerow([r["name"], r["member_no"], r["kind"], "manual" if r["manual"] else "QR", r["at"]])
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="kehadiran.csv"'})


@router.get("/hadir/{token}")
def hadir_info(token: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Attendance).filter_by(token=token).first()
    if a is None:
        raise HTTPException(404, "Kod kehadiran tak sah")
    return {"title": a.title, "date": a.on_date.isoformat(), "open": a.open}


@router.post("/hadir/{token}")
def hadir(token: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ahli imbas QR lalu tekan hadir. Hanya yang ada dalam senarai ahli/alumni (emel padan) direkodkan."""
    a = db.query(Attendance).filter_by(token=token).first()
    if a is None:
        raise HTTPException(404, "Kod kehadiran tak sah")
    if not a.open:
        raise HTTPException(400, "Kehadiran ini sudah ditutup")
    p = person_of(db, user)
    if p is None:
        raise HTTPException(400, "Emel anda tiada dalam senarai ahli/alumni. Hubungi BLG untuk direkodkan secara manual.")
    if db.query(AttendRecord).filter_by(attendance_id=a.id, person_id=p.id).first():
        return {"ok": True, "already": True, "title": a.title}
    db.add(AttendRecord(attendance_id=a.id, person_id=p.id))
    db.commit()
    return {"ok": True, "title": a.title}


# ---------------------------------------------------------------- inventori

class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = ""
    total: int = Field(default=1, ge=0, le=100000)
    note: str = Field(default="", max_length=300)
    active: bool = True


def _out_qty(db, item_id) -> int:
    return int(db.query(func.coalesce(func.sum(Loan.qty), 0)).filter(Loan.item_id == item_id,
                                                                     Loan.returned_at.is_(None)).scalar() or 0)


@router.get("/inventory/items")
def items(user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    rows = db.query(Item).order_by(func.lower(Item.name)).all()
    return [{"id": i.id, "name": i.name, "category": i.category, "total": i.total, "note": i.note,
             "active": i.active, "out": _out_qty(db, i.id), "available": i.total - _out_qty(db, i.id)} for i in rows]


@router.post("/inventory/items")
def add_item(data: ItemIn, user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    i = Item(name=data.name.strip(), category=data.category.strip(), total=data.total, note=data.note.strip(),
             active=data.active)
    db.add(i)
    db.commit()
    return {"id": i.id}


@router.put("/inventory/items/{iid}")
def edit_item(iid: int, data: ItemIn, user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    i = db.get(Item, iid)
    if i is None:
        raise HTTPException(404, "Tak jumpa")
    i.name, i.category, i.total, i.note, i.active = data.name.strip(), data.category.strip(), data.total, data.note.strip(), data.active
    db.commit()
    return {"ok": True}


def _loan_out(db, l: Loan):
    it, p = db.get(Item, l.item_id), db.get(Person, l.person_id)
    return {"id": l.id, "item": it.name if it else "", "item_id": l.item_id, "person": p.name if p else "",
            "person_id": l.person_id, "qty": l.qty, "taken_at": l.taken_at.isoformat(),
            "due_date": l.due_date.isoformat() if l.due_date else None, "taken_note": l.taken_note,
            "taken_photo": l.taken_photo, "returned_at": l.returned_at.isoformat() if l.returned_at else None,
            "return_note": l.return_note, "return_photo": l.return_photo,
            "overdue": bool(l.returned_at is None and l.due_date and l.due_date < svc.today_my())}


@router.get("/inventory/loans")
def loans(open_only: bool = False, user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    qs = db.query(Loan)
    if open_only:
        qs = qs.filter(Loan.returned_at.is_(None))
    return [_loan_out(db, l) for l in qs.order_by(Loan.id.desc()).limit(300)]


@router.post("/inventory/loans")
async def lend(item_id: int = Form(...), person_id: int = Form(...), qty: int = Form(1),
               due_date: str = Form(""), note: str = Form(""), file: UploadFile | None = File(None),
               user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    it = db.get(Item, item_id)
    if it is None or not it.active or db.get(Person, person_id) is None:
        raise HTTPException(404, "Barang atau peminjam tak jumpa")
    if qty < 1 or qty > it.total - _out_qty(db, item_id):
        raise HTTPException(400, "Kuantiti melebihi baki yang ada")
    try:
        due = pp.parse_date(due_date) if due_date else None
    except ValueError as e:
        raise HTTPException(400, str(e))
    photo = await save_upload(file, "inv_", images_only=True) if file is not None and file.filename else None
    l = Loan(item_id=item_id, person_id=person_id, qty=qty, due_date=due, taken_note=note.strip()[:300],
             taken_photo=photo, recorded_by=user.id)
    db.add(l)
    db.commit()
    return _loan_out(db, l)


@router.post("/inventory/loans/{lid}/return")
async def give_back(lid: int, note: str = Form(""), file: UploadFile | None = File(None),
                    user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    l = db.get(Loan, lid)
    if l is None:
        raise HTTPException(404, "Pinjaman tak jumpa")
    if l.returned_at is not None:
        raise HTTPException(400, "Sudah dipulangkan")
    l.return_photo = await save_upload(file, "inv_", images_only=True) if file is not None and file.filename else None
    l.return_note = note.strip()[:300]
    l.returned_at = datetime.utcnow()
    db.commit()
    return _loan_out(db, l)


@router.get("/inventory/photo/{name}")
def loan_photo(name: str, user: models.User = Depends(need("can_inventory")), db: Session = Depends(get_db)):
    if not name.startswith("inv_"):
        raise HTTPException(404, "Tak jumpa")
    return storage.serve(name, "Gambar tiada")


# ---------------------------------------------------------------- muka depan: profil, direktori, struktur

class SessionIn(BaseModel):
    code: str


@router.get("/session", dependencies=[Depends(require_admin)])
def get_session(db: Session = Depends(get_db)):
    code = pp.session_now(db, svc.today_my())
    return {"code": code, "label": pp.session_label(code), "auto": pp.current_session(svc.today_my())}


@router.put("/session", dependencies=[Depends(require_admin)])
def set_session(data: SessionIn, db: Session = Depends(get_db)):
    """Admin tetapkan sesi semasa (cth 2728). Sesi layak tempah transport turut beralih jika ia ikut sesi lama."""
    code = data.code.strip()
    if not pp.valid_session(code):
        raise HTTPException(400, "Sesi tak sah. Guna 4 digit, cth 2728 (tahun akhir = tahun mula + 1)")
    old = pp.session_now(db, svc.today_my())
    db.merge(models.Setting(key="current_session", value=code))
    ey = db.get(models.Setting, "eligible_years")
    if ey is not None and ey.value.strip() == old:
        ey.value = code
    db.query(Post).filter(Post.session != code).update({Post.current: False})
    db.query(Post).filter(Post.session == code).update({Post.current: True})
    db.commit()
    return {"code": code, "label": pp.session_label(code), "auto": pp.current_session(svc.today_my())}


@router.get("/me/attendance")
def my_attendance(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rekod kehadiran saya bagi sesi semasa (bermula 1 Ogos) dan senarai setiap kehadiran."""
    p = person_of(db, user)
    code = pp.session_now(db, svc.today_my())
    start = pp.session_start(code)
    rows = db.query(Attendance).filter(Attendance.on_date >= start).order_by(Attendance.on_date.desc()).all()
    mine = {r.attendance_id for r in db.query(AttendRecord).filter_by(person_id=p.id)} if p else set()
    items = [{"id": a.id, "title": a.title, "date": a.on_date.isoformat(), "present": a.id in mine} for a in rows]
    return {"session": code, "label": pp.session_label(code), "total": len(items),
            "present": sum(1 for i in items if i["present"]), "items": items, "linked": p is not None}


def _dir_item(db, p: Person, with_posts: bool = True) -> dict:
    d = {"id": p.id, "name": p.name, "intake": p.intake,
         "intake_label": pp.session_label(p.intake) if pp.valid_session(p.intake) else "", "kind": p.kind,
         "college": p.college if p.kind == "SG" else "", "is_coach": p.is_coach}
    if with_posts:
        d["posts"] = [x["title"] + (f" ({x['seki'] or x['biro']})" if (x["seki"] or x["biro"]) else "")
                      for x in _posts_out(db, p.id) if x["current"]]
    return d


@router.get("/directory")
def directory(q: str = "", kind: str = "SG", session: str = "", limit: int = 200,
              user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Direktori ahli/alumni untuk semua ahli: nama, sesi, kolej, jawatan sahaja (tiada telefon/emel)."""
    qs = db.query(Person).filter(Person.active.is_(True), Person.kind == ("SSG" if kind == "SSG" else "SG"))
    if q.strip():
        qs = qs.filter(func.lower(Person.name).like(f"%{q.strip().lower()}%"))
    if session:
        qs = qs.filter(Person.intake == session)
    total = qs.count()
    rows = qs.order_by(func.lower(Person.name)).limit(min(max(limit, 1), 500)).all()
    sessions = [s for (s,) in db.query(Person.intake).filter(Person.active.is_(True), Person.kind == ("SSG" if kind == "SSG" else "SG"))
                .distinct().all() if s]
    sessions.sort(key=lambda s: pp.session_year(s) if pp.valid_session(s) else 0, reverse=True)
    return {"total": total, "sessions": sessions, "items": [_dir_item(db, p, kind != "SSG") for p in rows]}


@router.get("/structure")
def structure(session: str = "", user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """MT dan biro bagi sesi tertentu (lalai: sesi terkini yang ada jawatan)."""
    all_sessions = sorted({s for (s,) in db.query(Post.session).distinct()}, key=pp.session_year, reverse=True)
    cur = session.strip() if (session and session.strip()) else (all_sessions[0] if all_sessions else "")
    mt: dict[str, list[str]] = {}
    biros: dict[str, dict[str, list[str]]] = {}
    for x in db.query(Post).filter_by(session=cur).order_by(Post.id):
        p = db.get(Person, x.person_id)
        if p is None:
            continue
        b = db.get(Biro, x.biro_id) if x.biro_id else None
        parent = db.get(Biro, b.parent_id) if b and b.parent_id else None
        if x.level == "MT":
            mt.setdefault(x.title, []).append(p.name)
        else:
            name = (parent.name if parent else (b.name if b else "Lain-lain"))
            title = x.title if not parent else f"{x.title} (seki {b.name})"
            biros.setdefault(name, {}).setdefault(title, []).append(p.name)
    return {"sessions": all_sessions, "session": cur, "label": pp.session_label(cur) if cur else "",
            "mt": [{"title": t, "names": n} for t, n in mt.items()],
            "biros": [{"name": b, "posts": [{"title": t, "names": n} for t, n in ps.items()]}
                      for b, ps in biros.items()]}


@router.get("/inventory/list")
def inventory_list(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Senarai barang untuk semua ahli (nama, kategori, baki). Pinjaman diurus oleh pengurus inventori."""
    rows = db.query(Item).filter(Item.active.is_(True)).order_by(func.lower(Item.name)).all()
    return [{"id": i.id, "name": i.name, "category": i.category, "note": i.note,
             "available": i.total - _out_qty(db, i.id), "total": i.total} for i in rows]
