from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.entities import AuthSession, User, UserMovieInteraction, UserSetting
from app.recommendation.hybrid_ranker import DEFAULT_WEIGHTS
from app.security import find_session


def get_auth_session(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=settings.cookie_name),
) -> AuthSession:
    session = find_session(db, session_token)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return session


def get_current_user(session: AuthSession = Depends(get_auth_session)) -> User:
    return session.user


def get_interactions(db: Session, user_id: int):
    return list(
        db.scalars(select(UserMovieInteraction).where(UserMovieInteraction.user_id == user_id)).unique().all()
    )


def get_weights(db: Session, user_id: int):
    row = db.scalar(select(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key == "recommendation_weights"))
    if not row:
        return DEFAULT_WEIGHTS.copy()
    saved = dict(row.value or {})
    # Backward compatibility for installs that saved the old `audience` slider.
    if "community" not in saved and "audience" in saved:
        saved["community"] = saved.pop("audience")
    merged = DEFAULT_WEIGHTS.copy()
    merged.update({key: value for key, value in saved.items() if key in DEFAULT_WEIGHTS})
    return merged


def require_csrf(request: Request, session: AuthSession = Depends(get_auth_session)) -> AuthSession:
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or supplied != session.csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request token")
    return session
