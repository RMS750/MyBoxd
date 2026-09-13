from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import AuthSession, User

PBKDF2_ITERATIONS = 600_000


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _unb64(salt), int(iterations))
        return hmac.compare_digest(actual, _unb64(expected))
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_session(db: Session, user: User) -> tuple[AuthSession, str]:
    # Limit stale sessions per user and avoid carrying abandoned sessions forever.
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= utcnow()))
    raw = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    session = AuthSession(
        user_id=user.id,
        token_hash=token_hash(raw),
        csrf_token=csrf,
        expires_at=utcnow() + timedelta(days=settings.session_days),
    )
    db.add(session)
    db.flush()
    return session, raw


def find_session(db: Session, raw_token: str | None) -> AuthSession | None:
    if not raw_token:
        return None
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(raw_token)))
    if not session:
        return None
    if session.expires_at <= utcnow():
        db.delete(session)
        db.commit()
        return None
    return session


def password_is_sensible(password: str) -> bool:
    if len(password) < 10 or len(password) > 128:
        return False
    return any(c.isalpha() for c in password) and any(c.isdigit() for c in password)
