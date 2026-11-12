"""Hantar emel ringkas. Brevo HTTP API (berfungsi pada Render percuma) atau SMTP. Tiada pustaka tambahan."""
import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from . import config

log = logging.getLogger("pssgutm.mail")
last_error = ""   # sebab terakhir gagal hantar (untuk log / semakan admin)


def configured() -> bool:
    return bool((config.BREVO_API_KEY and config.MAIL_FROM) or (config.SMTP_HOST and config.SMTP_FROM))


def send_mail(to: str, subject: str, text: str) -> bool:
    """True jika berjaya dihantar. Tidak pernah melempar ralat (pemanggil guna fallback). Sebab gagal direkod dalam log."""
    global last_error
    last_error = ""
    try:
        if config.BREVO_API_KEY and config.MAIL_FROM:
            body = json.dumps({"sender": {"email": config.MAIL_FROM, "name": config.MAIL_FROM_NAME},
                               "to": [{"email": to}], "subject": subject, "textContent": text}).encode()
            req = urllib.request.Request("https://api.brevo.com/v3/smtp/email", data=body, method="POST",
                                         headers={"api-key": config.BREVO_API_KEY, "content-type": "application/json",
                                                  "accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return 200 <= r.status < 300
        if config.SMTP_HOST and config.SMTP_FROM:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = config.SMTP_FROM, to, subject
            msg.set_content(text)
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
                s.starttls()
                if config.SMTP_USER:
                    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
            return True
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:300]
        except Exception:
            pass
        last_error = f"Brevo menolak ({e.code}): {detail}"
        hint = " Kemungkinan emel penghantar (MAIL_FROM) belum disahkan di Brevo > Senders." if e.code in (400, 401, 403) else ""
        log.error("Emel gagal: %s.%s", last_error, hint)
        return False
    except Exception as e:
        last_error = f"{type(e).__name__}: {e}"
        log.error("Emel gagal: %s", last_error)
        return False
    last_error = "Tiada penghantar emel dikonfigurasi (BREVO_API_KEY + MAIL_FROM)"
    return False
