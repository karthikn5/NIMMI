import asyncio
import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, client_ip, get_ctx, issue_token, rate_limit, revoke_sessions
from database import get_db
from backend.models import TeamMember, User, UserUsage
from notify.email import send_reset_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


EMAIL = re.compile(r"^[^\s@<>\"']{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")
# A real bcrypt hash, so a login for an unknown email costs the same time as a wrong password
# (otherwise the response time reveals which emails have accounts).
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()


class UserSignup(BaseModel):
    email: str = Field(..., max_length=254)
    name: str = Field("", max_length=80)
    password: str = Field(..., max_length=200)


class UserLogin(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=200)


class SocialLogin(BaseModel):
    access_token: str = Field(..., max_length=8000)  # Supabase session token, verified server-side
    name: Optional[str] = Field(None, max_length=80)


class PasswordResetRequest(BaseModel):
    email: str = Field(..., max_length=254)


class PasswordResetSubmit(BaseModel):
    token: str = Field(..., max_length=200)
    new_password: str = Field(..., max_length=200)


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    email: Optional[str] = Field(None, max_length=254)
    current_password: Optional[str] = Field(None, max_length=200)  # required to change the email


def _check_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Use at least 8 characters for your password")
    if len(password.encode("utf-8")) > 72:  # bcrypt only uses the first 72 bytes
        raise HTTPException(status_code=400, detail="Use 72 characters or fewer for your password")


def _check_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not EMAIL.fullmatch(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    return email


def _token_hash(token: str) -> str:
    """Reset links are stored hashed: a database leak must not let anyone reset passwords."""
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:  # malformed hash or over-long password
        return False


def _session(user: User) -> dict:
    return {"user_id": str(user.id), "name": user.name or "", "email": user.email, "token": issue_token(str(user.id))}


async def _accept_pending_invites(user: User, db: AsyncSession) -> None:
    """
    Invites sent to this email become active on sign-in, but only when the email is proven
    (Google sign-in). Password accounts don't verify their email, so they join through the
    invite link, whose token proves they received the invite.
    """
    invites = (await db.execute(
        select(TeamMember).where(func.lower(TeamMember.email) == user.email.lower(), TeamMember.member_id.is_(None))
    )).scalars().all()
    for invite in invites:
        invite.member_id = user.id
        invite.status = "active"
        invite.invite_token = None
    if invites:
        await db.commit()


@router.post("/signup")
async def signup(data: UserSignup, request: Request, db: AsyncSession = Depends(get_db)):
    rate_limit(f"signup:{client_ip(request)}", 10, 3600)
    email = _check_email(data.email)
    _check_password(data.password)
    if (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first():
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = User(email=email, name=data.name.strip(), password_hash=await asyncio.to_thread(hash_password, data.password))
    db.add(user)
    await db.flush()
    db.add(UserUsage(user_id=user.id, total_credits=1, used_credits=0))
    await db.commit()
    await db.refresh(user)
    return {"message": "Signup successful", **_session(user)}


@router.post("/login")
async def login(data: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    email = data.email.strip().lower()
    rate_limit(f"login:{client_ip(request)}", 20, 60)
    rate_limit(f"login-email:{email}", 10, 600)
    user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
    ok = await asyncio.to_thread(verify_password, data.password, user.password_hash if user and user.password_hash else _DUMMY_HASH)
    if not user or not user.password_hash or not ok:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"message": "Login successful", **_session(user)}


_supabase_client: Optional[httpx.AsyncClient] = None


def _supabase_http() -> httpx.AsyncClient:
    """One client kept open, so a Google sign-in reuses the connection instead of a new TLS handshake."""
    global _supabase_client
    if _supabase_client is None or _supabase_client.is_closed:
        _supabase_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0),
                                             limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=300))
    return _supabase_client


async def _supabase_user(access_token: str) -> dict:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise HTTPException(status_code=503, detail="Google sign-in isn't configured on the server")
    try:
        resp = await _supabase_http().get(
            f"{url.strip().rstrip('/')}/auth/v1/user",
            headers={"apikey": key.strip(), "Authorization": f"Bearer {access_token}"},
        )
    except (httpx.HTTPError, ValueError) as e:
        # Usually SUPABASE_URL / SUPABASE_KEY are wrong on the server (e.g. a placeholder).
        logger.error(f"Google sign-in can't reach Supabase at {url!r}: {type(e).__name__}: {e}")
        raise HTTPException(status_code=503, detail="Google sign-in is temporarily unavailable. Please use your email and password for now.")
    if resp.status_code in (401, 403) and resp.headers.get("content-type", "").startswith("application/json") and "Invalid API key" in resp.text:
        logger.error("Google sign-in: Supabase rejected SUPABASE_KEY (use the project's publishable/anon key)")
        raise HTTPException(status_code=503, detail="Google sign-in is temporarily unavailable. Please use your email and password for now.")
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Google sign-in expired. Please try again.")
    return resp.json()


@router.post("/social")
async def social_login(data: SocialLogin, request: Request, db: AsyncSession = Depends(get_db)):
    rate_limit(f"social:{client_ip(request)}", 20, 60)
    profile = await _supabase_user(data.access_token)
    email = (profile.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Your Google account has no email address")
    # Only trust an address Google has confirmed. A Supabase email/password signup could otherwise
    # claim someone else's address and sign in to their Nimmi account.
    app_meta = profile.get("app_metadata") or {}
    providers = {str(p).lower() for p in (app_meta.get("providers") or [app_meta.get("provider") or ""])}
    if "google" not in providers or not (profile.get("email_confirmed_at") or profile.get("confirmed_at")):
        raise HTTPException(status_code=401, detail="Please sign in with Google")
    meta = profile.get("user_metadata") or {}
    name = data.name or meta.get("full_name") or meta.get("name") or ""

    user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
    if not user:
        user = User(email=email, name=name, password_hash=None)
        db.add(user)
        await db.flush()
        db.add(UserUsage(user_id=user.id, total_credits=1, used_credits=0))
        await db.commit()
        await db.refresh(user)
    elif name and not user.name:
        user.name = name
        await db.commit()
    await _accept_pending_invites(user, db)
    return {"message": "Success", **_session(user)}


@router.get("/profile")
async def get_profile(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.id == ctx.user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": str(user.id),
        "email": user.email,
        "name": user.name or "",
        "subscription_tier": user.subscription_tier,
        "has_password": bool(user.password_hash),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.patch("/profile")
async def update_profile(data: ProfileUpdate, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.id == ctx.user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.name is not None:
        user.name = data.name.strip()
    if data.email is not None and data.email.strip().lower() != (user.email or "").lower():
        email = _check_email(data.email)
        # The email is how an account is recovered, so changing it needs the password, not just a session.
        if not user.password_hash:
            raise HTTPException(status_code=400, detail="You sign in with Google, so your email comes from Google. Set a password first to change it.")
        rate_limit(f"email-change:{user.id}", 5, 3600)
        if not await asyncio.to_thread(verify_password, data.current_password or "", user.password_hash):
            raise HTTPException(status_code=400, detail="Enter your current password to change your email")
        taken = (await db.execute(select(User).where(func.lower(User.email) == email, User.id != user.id))).scalars().first()
        if taken:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = email
    await db.commit()
    return {"message": "Profile updated successfully", "name": user.name, "email": user.email}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(data: PasswordChange, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    rate_limit(f"change-pw:{ctx.user_id}", 10, 600)
    _check_password(data.new_password)
    user = (await db.execute(select(User).where(User.id == ctx.user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.password_hash and not await asyncio.to_thread(verify_password, data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Your current password isn't right")
    user.password_hash = await asyncio.to_thread(hash_password, data.new_password)
    revoke_sessions(user)  # anyone signed in with the old password is signed out
    await db.commit()
    return {"message": "Password changed", **_session(user)}


@router.post("/logout-all")
async def logout_everywhere(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Sign out on every device (e.g. a lost laptop). This browser gets a fresh session."""
    user = (await db.execute(select(User).where(User.id == ctx.user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    revoke_sessions(user)
    await db.commit()
    return {"message": "Signed out everywhere else", **_session(user)}


@router.post("/forgot-password")
async def forgot_password(data: PasswordResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    rate_limit(f"forgot:{client_ip(request)}", 5, 600)
    user = (await db.execute(select(User).where(func.lower(User.email) == data.email.strip().lower()))).scalars().first()
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = _token_hash(token)
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        await db.commit()
        await send_reset_email(user.email, token)
    # Same answer either way, so emails can't be enumerated.
    return {"message": "If that email has an account, a reset link is on its way."}


@router.post("/reset-password")
async def reset_password(data: PasswordResetSubmit, request: Request, db: AsyncSession = Depends(get_db)):
    rate_limit(f"reset:{client_ip(request)}", 10, 600)
    _check_password(data.new_password)
    token = data.token.strip()
    user = (await db.execute(select(User).where(User.reset_token == _token_hash(token)))).scalars().first() if token else None
    expires = user.reset_token_expires.replace(tzinfo=None) if user and user.reset_token_expires else None
    if not user or not expires or expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="This reset link has expired. Request a new one.")
    user.password_hash = await asyncio.to_thread(hash_password, data.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    revoke_sessions(user)  # whoever had the account before the reset is signed out
    await db.commit()
    return {"message": "Password reset successful", **_session(user)}
