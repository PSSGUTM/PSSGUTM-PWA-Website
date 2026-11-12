"""Pembersihan data lama supaya had percuma Supabase (500 MB DB, 1 GB storan) tahan bertahun-tahun.

Dijalankan setiap hari oleh scheduler. Rekod bayaran KEKAL; hanya gambar resit dan notifikasi lama dipadam.
"""
import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from .. import config, models, storage
from ..models import PaymentStatus
from .booking import today_my

log = logging.getLogger("pssgutm")


def _cutoff_date():
    return today_my() - timedelta(days=int(config.RETENTION_MONTHS * 30.5))


def purge_old_receipts(db: Session) -> int:
    """Padam gambar resit yang sudah selesai (disahkan atau dibatalkan) dan lebih RETENTION_MONTHS lama."""
    cutoff = _cutoff_date()
    n = 0
    for p in db.query(models.Payment).filter(
            models.Payment.receipt_path.isnot(None), models.Payment.training_date < cutoff,
            models.Payment.status.in_([PaymentStatus.paid, PaymentStatus.void])).all():
        storage.delete(p.receipt_path)
        p.receipt_path = None
        n += 1
    # Resit bayaran prebet: satu fail dikongsi satu 'batch'; padam hanya jika SEMUA barisnya lama
    by_file: dict[str, list[models.DriverPayout]] = {}
    for r in db.query(models.DriverPayout).filter(models.DriverPayout.receipt_file.isnot(None)).all():
        by_file.setdefault(r.receipt_file, []).append(r)
    for name, rows in by_file.items():
        if all(r.training_date < cutoff for r in rows):
            storage.delete(name)
            for r in rows:
                r.receipt_file = None
            n += 1
    db.commit()
    return n


def purge_old_notifications(db: Session) -> int:
    """Padam notifikasi lama (kecuali amaran yang masih aktif)."""
    from datetime import datetime
    cutoff = datetime.utcnow() - timedelta(days=int(config.RETENTION_MONTHS * 30.5))
    ids = [i for (i,) in db.query(models.Notification.id).filter(
        models.Notification.created_at < cutoff, models.Notification.severity != "warning").limit(5000)]
    if not ids:
        return 0
    db.query(models.NotificationDismissal).filter(
        models.NotificationDismissal.notification_id.in_(ids)).delete(synchronize_session=False)
    db.query(models.Notification).filter(models.Notification.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return len(ids)


def run_retention(db: Session) -> tuple[int, int]:
    if config.RETENTION_MONTHS <= 0:
        return 0, 0
    return purge_old_receipts(db), purge_old_notifications(db)


def expire_stale_warnings(db: Session) -> int:
    """Buang amaran berkaitan tarikh latihan yang sudah lepas dan tak mungkin selesai lagi (supaya tak kekal selama-lamanya).

    - belum tanda sampai/hantar (prebet & bendahari): selepas 2 hari (lepas tempoh amaran dijana)
    - senarai ditarik balik, prebet belum sahkan, perempuan seorang, boleh bawa?: selepas tarikh latihan berlalu
    """
    from sqlalchemy import or_
    today = today_my()
    n = db.query(models.Notification).filter(
        models.Notification.training_date.isnot(None), models.Notification.training_date < today - timedelta(days=2),
        or_(models.Notification.ref.like("tick:%"), models.Notification.ref.like("tickmiss:%"))
    ).delete(synchronize_session=False)
    n += db.query(models.Notification).filter(
        models.Notification.training_date.isnot(None), models.Notification.training_date < today,
        or_(models.Notification.ref.like("unfin:%"), models.Notification.ref.like("unconf:%"),
            models.Notification.ref.like("lone:%"), models.Notification.ref.like("avail:%"))
    ).delete(synchronize_session=False)
    db.commit()
    return n
