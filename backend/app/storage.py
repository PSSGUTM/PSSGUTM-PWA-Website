"""Simpanan fail (logo, QR, resit).

Kalau SUPABASE_URL dan SUPABASE_SERVICE_KEY ditetapkan -> simpan di Supabase Storage (kekal,
tak hilang bila Render restart). Kalau tidak -> simpan di cakera (UPLOAD_DIR) untuk ujian setempat.
"""
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from . import config

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
BUCKET = os.getenv("SUPABASE_BUCKET", "uploads")
MIME = {".jpg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf"}


def remote() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _req(method: str, name: str, data: bytes | None = None, ctype: str | None = None):
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{urllib.parse.quote(name)}"
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY}
    if ctype:
        headers["Content-Type"] = ctype
        headers["x-upsert"] = "true"
    return urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=20)


def put(name: str, content: bytes) -> None:
    if remote():
        ctype = MIME.get(os.path.splitext(name)[1], "application/octet-stream")
        try:
            _req("POST", name, content, ctype).close()
        except Exception:
            raise HTTPException(502, "Gagal simpan fail. Cuba lagi sebentar.")
        return
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    with open(os.path.join(config.UPLOAD_DIR, name), "wb") as f:
        f.write(content)


def serve(name: str, missing: str = "Fail hilang"):
    name = os.path.basename(name or "")
    if not name:
        raise HTTPException(404, missing)
    if remote():
        try:
            with _req("GET", name) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                raise HTTPException(404, missing)
            raise HTTPException(502, "Simpanan fail tak dapat dicapai")
        except Exception:
            raise HTTPException(502, "Simpanan fail tak dapat dicapai")
        return Response(body, media_type=MIME.get(os.path.splitext(name)[1], "application/octet-stream"),
                        headers={"Cache-Control": "private, max-age=300"})
    path = os.path.join(config.UPLOAD_DIR, name)
    if not os.path.isfile(path):
        raise HTTPException(404, missing)
    return FileResponse(path)


def delete(name: str | None) -> None:
    """Padam satu fail (tak pernah gagalkan permintaan)."""
    name = os.path.basename(name or "")
    if not name:
        return
    try:
        if remote():
            _req("DELETE", name).close()
        else:
            path = os.path.join(config.UPLOAD_DIR, name)
            if os.path.isfile(path):
                os.remove(path)
    except Exception:
        pass


def delete_all() -> int:
    """Padam SEMUA fail muat naik (untuk reset data ujian). Return bilangan fail yang dipadam."""
    n = 0
    try:
        if remote():
            import json
            while True:
                req = urllib.request.Request(
                    f"{SUPABASE_URL}/storage/v1/object/list/{BUCKET}",
                    data=json.dumps({"prefix": "", "limit": 500, "offset": 0}).encode(),
                    headers={"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY, "Content-Type": "application/json"},
                    method="POST")
                with urllib.request.urlopen(req, timeout=20) as r:
                    names = [x["name"] for x in json.loads(r.read().decode()) if x.get("name") and x.get("id")]
                if not names:
                    break
                req = urllib.request.Request(
                    f"{SUPABASE_URL}/storage/v1/object/{BUCKET}",
                    data=json.dumps({"prefixes": names}).encode(),
                    headers={"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY, "Content-Type": "application/json"},
                    method="DELETE")
                urllib.request.urlopen(req, timeout=30).close()
                n += len(names)
        elif os.path.isdir(config.UPLOAD_DIR):
            for f in os.listdir(config.UPLOAD_DIR):
                fp = os.path.join(config.UPLOAD_DIR, f)
                if os.path.isfile(fp):
                    os.remove(fp)
                    n += 1
    except Exception:
        pass
    return n
