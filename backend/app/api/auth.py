from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_auth_session, get_current_user, require_csrf
from app.config import settings
from app.database import get_db
from app.models.entities import AuthSession, User
from app.rate_limit import auth_limiter
from app.schemas.requests import LoginRequest, PasswordChangeRequest, ProfileUpdateRequest, RegisterRequest
from app.security import create_session, hash_password, password_is_sensible, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _public_user(user: User, csrf_token: str | None = None) -> dict:
    payload = {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
    if csrf_token:
        payload["csrf_token"] = csrf_token
    return payload


def _set_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=raw_token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, summary="Create a MyBoxd account")
def register(req: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    auth_limiter.check(f"register:{request.client.host if request.client else 'unknown'}:{req.email}")
    if not password_is_sensible(req.password):
        raise HTTPException(400, "Password must be at least 10 characters and include letters and numbers")
    if db.scalar(select(User.id).where(User.email == req.email)):
        raise HTTPException(409, "An account with that email already exists")
    user = User(name=req.name, email=req.email, password_hash=hash_password(req.password))
    db.add(user)
    db.flush()
    session, raw = create_session(db, user)
    db.commit()
    _set_cookie(response, raw)
    return {"user": _public_user(user, session.csrf_token)}


@router.post("/login", summary="Log in")
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    auth_limiter.check(f"login:{request.client.host if request.client else 'unknown'}:{req.email}")
    user = db.scalar(select(User).where(User.email == req.email))
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    session, raw = create_session(db, user)
    db.commit()
    _set_cookie(response, raw)
    return {"user": _public_user(user, session.csrf_token)}


@router.get("/me", summary="Get the current account")
def me(session: AuthSession = Depends(get_auth_session)):
    return {"user": _public_user(session.user, session.csrf_token)}


@router.post("/logout", summary="Log out")
def logout(
    response: Response,
    session: AuthSession = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    db.delete(session)
    db.commit()
    response.delete_cookie(
        settings.cookie_name,
        path="/",
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
    return {"ok": True}


@router.put("/profile", summary="Update account profile")
def update_profile(
    req: ProfileUpdateRequest,
    _: AuthSession = Depends(require_csrf),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.name = req.name
    db.commit()
    db.refresh(user)
    return {"user": _public_user(user)}


@router.put("/password", summary="Change password")
def change_password(
    req: PasswordChangeRequest,
    session: AuthSession = Depends(require_csrf),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if not password_is_sensible(req.new_password):
        raise HTTPException(400, "New password must be at least 10 characters and include letters and numbers")
    user.password_hash = hash_password(req.new_password)
    # Keep the current session but invalidate every other browser session.
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.id != session.id))
    db.commit()
    return {"ok": True}
