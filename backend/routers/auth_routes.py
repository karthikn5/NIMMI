import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, client_ip, get_ctx, issue_token, rate_limit
from database import get_db
from backend.models import TeamMember, User, UserUsage
from notify.email import send_reset_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class UserSignup(BaseModel):
    email: str
    name: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class SocialLogin(BaseModel):
    access_token: str  # Supabase session token, verified server-side
    name: Optional[str] = None


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetSubmit(BaseModel):
    token: str
    new_password: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _session(user: User) -> dict:
    return {"user_id": str(user.id), "name": user.name or "", "email": user.email, "token": issue_token(str(user.id))}


async def _accept_pending_invites(user: User, db: AsyncSession) -> None:
    """Invites sent to this email before the person had an account become active on sign-in."""
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
    email = data.email.strip().lower()
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Use at least 8 characters for your password")
    if (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first():
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = User(email=email, name=data.name.strip(), password_hash=await asyncio.to_thread(hash_password, data.password))
    db.add(user)
    await db.flush()
    db.add(UserUsage(user_id=user.id, total_credits=1, used_credits=0))
    await db.commit()
    await db.refresh(user)
    await _accept_pending_invites(user, db)
    return {"message": "Signup successful", **_session(user)}


@router.post("/login")
async def login(data: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    email = data.email.strip().lower()
    rate_limit(f"login:{client_ip(request)}", 20, 60)
    rate_limit(f"login-email:{email}", 10, 600)
    user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not await asyncio.to_thread(verify_password, data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await _accept_pending_invites(user, db)
    return {"message": "Login successful", **_session(user)}


async def _supabase_user(access_token: str) -> dict:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise HTTPException(status_code=503, detail="Google sign-in isn't configured on the server")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{url.rstrip('/')}/auth/v1/user",
            headers={"apikey": key, "Authorization": f"Bearer {access_token}"},
        )
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
    if data.email is not None:
        email = data.email.strip().lower()
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
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Use at least 8 characters for your new password")
    user = (await db.execute(select(User).where(User.id == ctx.user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.password_hash and not await asyncio.to_thread(verify_password, data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Your current password isn't right")
    user.password_hash = await asyncio.to_thread(hash_password, data.new_password)
    await db.commit()
    return {"message": "Password changed"}


@router.post("/forgot-password")
async def forgot_password(data: PasswordResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    rate_limit(f"forgot:{client_ip(request)}", 5, 600)
    user = (await db.execute(select(User).where(func.lower(User.email) == data.email.strip().lower()))).scalars().first()
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        await db.commit()
        await send_reset_email(user.email, token)
    # Same answer either way, so emails can't be enumerated.
    return {"message": "If that email has an account, a reset link is on its way."}


@router.post("/reset-password")
async def reset_password(data: PasswordResetSubmit, db: AsyncSession = Depends(get_db)):
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Use at least 8 characters for your password")
    user = (await db.execute(select(User).where(User.reset_token == data.token))).scalars().first()
    expires = user.reset_token_expires.replace(tzinfo=None) if user and user.reset_token_expires else None
    if not user or not expires or expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="This reset link has expired. Request a new one.")
    user.password_hash = await asyncio.to_thread(hash_password, data.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    await db.commit()
    return {"message": "Password reset successful", **_session(user)}
