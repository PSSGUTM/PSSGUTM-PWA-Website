"""Sahkan ID token Google (daripada butang 'Log masuk dengan Google') melalui titik akhir tokeninfo Google."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config


class GoogleAuthError(Exception):
    pass


def verify(credential: str) -> dict:
    """Return {email, name} jika token sah untuk app ini dan emel disahkan Google. Raise GoogleAuthError jika tidak."""
    if not config.GOOGLE_CLIENT_ID:
        raise GoogleAuthError("Log masuk Google belum dikonfigurasi")
    url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": credential})
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            info = json.loads(r.read().decode())
    except (urllib.error.URLError, ValueError, TimeoutError):
        raise GoogleAuthError("Token Google tak sah atau tamat tempoh")
    if info.get("aud") != config.GOOGLE_CLIENT_ID:
        raise GoogleAuthError("Token Google bukan untuk app ini")
    if str(info.get("email_verified")).lower() != "true" or not info.get("email"):
        raise GoogleAuthError("Emel Google belum disahkan")
    if int(info.get("exp", 0)) < time.time():
        raise GoogleAuthError("Token Google tamat tempoh")
    return {"email": info["email"].lower(), "name": info.get("name") or ""}
