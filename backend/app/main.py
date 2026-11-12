import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import config, models, storage
from .database import Base, SessionLocal, engine, get_db
from .migrate import enable_rls, run_migrations
import os

from fastapi import HTTPException
from fastapi.responses import FileResponse

from . import models_main  # noqa: F401  (daftar jadual modul utama)
from .routes import admin, auth, bookings, driver, laman, member, persatuan
from .security import get_current_user
from .services import booking as svc

log = logging.getLogger("pssgutm")


def _job(fn_name):
    def run():
        db = SessionLocal()
        try:
            if fn_name == "daily":
                log.info("Scheduler: %s booking baru, %s reminder, %s peringatan keselamatan, %s peringatan bayar driver",
                         svc.generate_bookings(db), svc.send_reminders(db), svc.send_safety_reminders(db),
                         svc.send_payout_reminders(db))
                svc.send_licence_reminders(db)
                svc.send_arrears_reminders(db)
                from .services import retention
                log.info("Pembersihan: %s resit, %s notifikasi lama dipadam", *retention.run_retention(db))
                log.info("Amaran lapuk dibuang: %s", retention.expire_stale_warnings(db))
            else:
                svc.send_prebet_notices(db)
                svc.send_tick_warnings(db)
                n = svc.auto_finalise(db)
                if n:
                    log.info("Scheduler: %s senarai disahkan automatik", n)
        except Exception:
            log.exception("Scheduler gagal (%s)", fn_name)
        finally:
            db.close()
    return run


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_migrations()
    enable_rls()
    _db = SessionLocal()
    try:
        persatuan.ensure_seed(_db)
    finally:
        _db.close()
    scheduler = BackgroundScheduler(timezone="Asia/Kuala_Lumpur")
    scheduler.add_job(_job("daily"), "cron", hour=0, minute=5)
    scheduler.add_job(_job("finalise"), "cron", minute="*/10")  # setiap 10 minit (auto sahkan 7:00 mlm, tanda prebet)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="PSSGUTM API", version="3.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, member.router, bookings.router, driver.router, admin.router, persatuan.router, laman.router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/colleges")
def list_colleges(db: Session = Depends(get_db)):
    """Untuk borang daftar & paparan syarat."""
    pts: dict[int, list] = {}
    for p in db.query(models.PickupPoint).filter_by(active=True).order_by(models.PickupPoint.id):
        pts.setdefault(p.college_id, []).append({"id": p.id, "name": p.name, "gender": p.gender.value})
    return [{"id": c.id, "code": c.code, "name": c.name, "category": c.category,
             "points": pts.get(c.id, []),
             "transport_available": c.transport_available,
             "fee_car": svc.fee_amount(db, "car", c.category),
             "fee_motorcycle": svc.fee_amount(db, "motorcycle", c.category)}
            for c in db.query(models.College).order_by(models.College.id)]


@app.get("/rules")
def rules(db: Session = Depends(get_db)):
    """Syarat ringkas + jadual checkpoint & tempat latihan, dipaparkan dalam app."""
    colleges = {c.id: c for c in db.query(models.College)}
    pts = [{"college": colleges[p.college_id].code, "gender": p.gender.value, "name": p.name}
           for p in db.query(models.PickupPoint).filter_by(active=True)]
    venues = [{"name": v.name, "excluded": [c for c in v.excluded_codes.split(",") if c]}
              for v in db.query(models.Venue).filter_by(active=True)]
    today = svc.today_my()
    sessions = [{"name": s.name, "start": svc.fmt12(s.start_time), "pickup": svc.pickup_window(s),
                 "return": svc.fmt12(s.end_time)}
                for s in db.query(models.TrainingSession).filter_by(active=True)
                if s.one_off_date is None]
    activities = [{"name": s.name, "date": s.one_off_date.isoformat(), "fee": float(s.activity_fee or 0.0),
                   "start": svc.fmt12(s.start_time),
                   "pickup": svc.pickup_window(s), "return": svc.fmt12(s.end_time)}
                  for s in db.query(models.TrainingSession).filter_by(active=True)
                  if s.one_off_date is not None and s.one_off_date >= today]
    years = svc.eligible_years(db)
    known = {svc.member_year(r[0]) for r in db.query(models.MemberRoster.member_no)} - {None}
    all_sessions = "*" in years or (bool(known) and known <= set(years))
    return {"fees": svc.fee_tables(db)["fees"], "checkpoints": pts, "venues": venues, "sessions": sessions,
            "activities": activities, "eligible_years": years,
            "eligible_labels": [svc.year_label(y) for y in years], "all_sessions": all_sessions,
            "cutoff_time": config.CUTOFF_TIME, "auto_finalise_time": config.AUTO_FINALISE_TIME,
            "pay_deadline_time": config.PAY_DEADLINE_TIME,
            "default_rules": svc.default_rules(db),
            "custom_rules": (db.get(models.Setting, "rules_text").value if db.get(models.Setting, "rules_text") else "")}


@app.get("/contacts")
def contacts(date: str | None = None, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Admin bertugas hari itu (urusan prebet/pengangkutan) dan hubungan masalah laman web."""
    from datetime import date as _d
    try:
        d = _d.fromisoformat(date) if date else None
    except ValueError:
        d = None
    return svc.duty_contacts(db, d)


@app.get("/branding")
def branding(db: Session = Depends(get_db)):
    """Nama, warna dan logo (awam: dipaparkan pada halaman login)."""
    return bookings.read_branding(db)


@app.get("/branding/logo")
def branding_logo(db: Session = Depends(get_db)):
    s = db.get(models.Setting, "brand_logo_file")
    if not s or not s.value:
        raise HTTPException(404, "Tiada logo")
    return storage.serve(s.value, "Fail logo hilang")
