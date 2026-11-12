import os
import time as _time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .database import get_db

# WAJIB tukar dalam production: set env SECRET_KEY (cth: `openssl rand -hex 32`)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
if os.getenv("ENV") == "production" and SECRET_KEY == "dev-only-change-me":
    raise RuntimeError("SECRET_KEY mesti ditetapkan dalam production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7  # 7 hari

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> models.User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sila login semula")
    if creds is None:
        raise unauthorized
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    user = db.get(models.User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != models.Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin sahaja")
    return user


# Laluan yang bendahari (bukan admin) dibenarkan: bayaran ahli, bayar driver, maklumat bank/QR.
TREASURER_PATHS = ("/admin/dashboard", "/admin/payments", "/admin/payouts", "/admin/drivers/",
                   "/admin/settings/payment", "/admin/finance/", "/admin/arrears")


def require_staff(request: Request, user: models.User = Depends(get_current_user)) -> models.User:
    """Admin: semua. Bendahari: hanya laluan kewangan di atas."""
    if user.role == models.Role.admin:
        return user
    if user.is_treasurer and any(request.url.path.startswith(p) for p in TREASURER_PATHS):
        return user
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin sahaja")


# Rate limit ringkas dalam memori (cukup untuk satu server kecil).
_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(max_calls: int, per_seconds: int):
    def dep(request: Request):
        ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?")
        ip = ip.split(",")[0].strip()
        key = f"{request.url.path}:{ip}"
        now = _time.monotonic()
        q = _hits[key]
        while q and now - q[0] > per_seconds:
            q.popleft()
        if len(q) >= max_calls:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Terlalu banyak cubaan. Cuba sebentar lagi.")
        q.append(now)
    return dep
