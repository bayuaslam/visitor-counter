from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac, sha256
import base64
import hmac
import json
import os
import secrets
from pathlib import Path

from fastapi import Header, HTTPException, Request


ALLOWED_ROLES = {"STUDENT", "LECTURER", "LABORAN", "ADMIN"}
SESSION_COOKIE = "labhub_admin_session"
STUDENT_SESSION_COOKIE = "labhub_student_session"
SESSION_HOURS = 8


def _load_local_env():
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    name: str
    role: str


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_admin_password(password: str) -> bool:
    stored = os.getenv("LABHUB_ADMIN_PASSWORD_HASH", "")
    try:
        algorithm, iterations, salt_text, digest_text = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = pbkdf2_hmac("sha256", password.encode(), _b64decode(salt_text), int(iterations))
        return hmac.compare_digest(_b64encode(digest), digest_text)
    except (ValueError, TypeError):
        return False


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 310_000
    digest = pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = pbkdf2_hmac("sha256", password.encode(), _b64decode(salt_text), int(iterations))
        return hmac.compare_digest(_b64encode(digest), digest_text)
    except (ValueError, TypeError):
        return False


def _create_session(payload: dict) -> tuple[str, int]:
    secret = os.getenv("LABHUB_SESSION_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("LABHUB_SESSION_SECRET belum dikonfigurasi")
    payload = {**payload, "exp": int((datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).timestamp())}
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64encode(hmac.new(secret.encode(), encoded.encode(), sha256).digest())
    return f"{encoded}.{signature}", SESSION_HOURS * 3600


def _read_session(token: str | None) -> dict | None:
    if not token:
        return None
    secret = os.getenv("LABHUB_SESSION_SECRET", "")
    try:
        payload, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(secret.encode(), payload.encode(), sha256).digest())
        data = json.loads(_b64decode(payload))
        if not hmac.compare_digest(signature, expected) or int(data["exp"]) <= int(datetime.now(timezone.utc).timestamp()):
            return None
        return data
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def create_student_session(email: str) -> tuple[str, int]:
    return _create_session({"sub": email, "role": "STUDENT"})


def create_guest_session() -> tuple[str, int]:
    return _create_session({"sub": f"guest:{secrets.token_urlsafe(12)}", "role": "GUEST"})


def student_session(token: str | None) -> dict | None:
    data = _read_session(token)
    return data if data and data.get("role") in {"STUDENT", "GUEST"} else None


def create_admin_session() -> tuple[str, int]:
    secret = os.getenv("LABHUB_SESSION_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("LABHUB_SESSION_SECRET belum dikonfigurasi")
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    payload = _b64encode(json.dumps({"sub": "laboran", "exp": int(expires_at.timestamp())}, separators=(",", ":")).encode())
    signature = _b64encode(hmac.new(secret.encode(), payload.encode(), sha256).digest())
    return f"{payload}.{signature}", SESSION_HOURS * 3600


def valid_admin_session(token: str | None) -> bool:
    if not token:
        return False
    secret = os.getenv("LABHUB_SESSION_SECRET", "")
    try:
        payload, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(secret.encode(), payload.encode(), sha256).digest())
        data = json.loads(_b64decode(payload))
        return hmac.compare_digest(signature, expected) and data.get("sub") == "laboran" and int(data["exp"]) > int(datetime.now(timezone.utc).timestamp())
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False


def current_user(
    request: Request,
    x_labhub_user: str = Header(default="student.demo"),
    x_labhub_name: str = Header(default="Mahasiswa Demo"),
    x_labhub_role: str = Header(default="STUDENT"),
):
    role = x_labhub_role.upper()
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=401, detail="Role tidak valid")
    if role in {"LABORAN", "ADMIN"} and not valid_admin_session(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=401, detail="Silakan login sebagai laboran")
    if role in {"STUDENT", "LECTURER"}:
        session = student_session(request.cookies.get(STUDENT_SESSION_COOKIE))
        if not session:
            raise HTTPException(status_code=401, detail="Silakan login dengan email UII")
        if session.get("role") == "GUEST":
            return CurrentUser(user_id=str(session["sub"])[:120], name="Tamu", role="STUDENT")
        email = str(session["sub"])[:190]
        return CurrentUser(user_id=email, name=email.split("@", 1)[0].replace(".", " ").title(), role="STUDENT")
    return CurrentUser(user_id=x_labhub_user[:120], name=x_labhub_name[:160], role=role)


def require_staff(user: CurrentUser = None):
    if user is None or user.role not in {"LABORAN", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Akses laboran diperlukan")
    return user
