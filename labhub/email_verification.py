import hashlib
import hmac
import os
import smtplib
import ssl
from email.message import EmailMessage


def code_digest(email: str, code: str) -> str:
    secret = os.getenv("LABHUB_SESSION_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("LABHUB_SESSION_SECRET belum dikonfigurasi")
    value = f"{email.lower()}:{code}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), value, hashlib.sha256).hexdigest()


def send_verification_email(email: str, code: str) -> None:
    host = os.getenv("LABHUB_SMTP_HOST", "").strip()
    port = int(os.getenv("LABHUB_SMTP_PORT", "587"))
    username = os.getenv("LABHUB_SMTP_USERNAME", "").strip()
    password = os.getenv("LABHUB_SMTP_PASSWORD", "")
    sender = os.getenv("LABHUB_SMTP_FROM", username).strip()
    use_ssl = os.getenv("LABHUB_SMTP_SSL", "0").strip() == "1"
    use_starttls = os.getenv("LABHUB_SMTP_STARTTLS", "1").strip() == "1"
    environment = os.getenv("LABHUB_ENV", "development").strip().lower()

    if not host or not sender:
        if environment != "production" and os.getenv("LABHUB_DEV_SHOW_EMAIL_CODE", "0") == "1":
            print(f"[DEV EMAIL] Kode verifikasi {email}: {code}")
            return
        raise RuntimeError("SMTP belum dikonfigurasi untuk verifikasi email UII")

    message = EmailMessage()
    message["Subject"] = "Kode verifikasi Lab Robotika & Inovasi"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        "Kode verifikasi Lab Robotika & Inovasi Anda adalah: "
        f"{code}\n\nKode berlaku 10 menit. Abaikan email ini jika Anda tidak meminta pendaftaran."
    )

    context = ssl.create_default_context()
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as smtp:
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.ehlo()
        if use_starttls:
            smtp.starttls(context=context)
            smtp.ehlo()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)
