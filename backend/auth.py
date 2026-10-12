"""
Authentication and access control.

Every dashboard request carries `Authorization: Bearer <token>`. The token
identifies the person; the optional `X-Workspace` header says whose workspace
they are acting in (their own, or one they were invited to as a team member).
"""
import hashlib
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from backend.models import Bot, TeamMember, User

logger = logging.getLogger(__name__)

TOKEN_TTL_DAYS = 30
ROLES = ("owner", "admin", "agent")


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if secret:
        return secret
    # Stable fallback so tokens survive restarts; set JWT_SECRET in production.
    seed = (os.getenv("SUPABASE_KEY", "") + os.getenv("DATABASE_URL", "") + os.getenv("RAZORPAY_KEY_SECRET", ""))
    if not seed:
        seed = "nimmi-local-dev"
    logger.warning("JWT_SECRET is not set. Using a derived secret; set JWT_SECRET in production.")
    return hashlib.sha256(("nimmi-jwt:" + seed).encode()).hexdigest()


JWT_SECRET = _jwt_secret()


def issue_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(days=TOKEN_TTL_DAYS), "typ": "user"}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "user":
        return None
    return payload.get("sub")


def issue_scoped_token(subject: str, scope: str, ttl_seconds: int) -> str:
    """Short-lived token for one purpose, e.g. opening a voice test session."""
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "scope": scope, "iat": now, "exp": now + timedelta(seconds=ttl_seconds), "typ": "scoped"}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_scoped_token(token: str, scope: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "scoped" or payload.get("scope") != scope:
        return None
    return payload.get("sub")


@dataclass
class AuthContext:
    user_id: str   # the signed-in person
    owner_id: str  # whose workspace the request acts on
    role: str      # owner, admin or agent

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


def _bearer(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


async def _resolve(token: Optional[str], workspace: Optional[str], db: AsyncSession) -> Optional[AuthContext]:
    if not token:
        return None
    user_id = decode_token(token)
    if not user_id:
        return None
    user = (await db.execute(select(User.id).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return None
    if not workspace or workspace == user_id:
        return AuthContext(user_id=user_id, owner_id=user_id, role="owner")
    member = (await db.execute(
        select(TeamMember).where(
            TeamMember.owner_id == workspace,
            TeamMember.member_id == user_id,
            TeamMember.status == "active",
        )
    )).scalars().first()
    if not member:
        raise HTTPException(status_code=403, detail="You are not a member of this workspace")
    return AuthContext(user_id=user_id, owner_id=workspace, role=member.role)


async def get_ctx(request: Request, db: AsyncSession = Depends(get_db)) -> AuthContext:
    """Require a signed-in user."""
    ctx = await _resolve(_bearer(request), request.headers.get("x-workspace"), db)
    if not ctx:
        raise HTTPException(status_code=401, detail="Please sign in again")
    return ctx


async def get_optional_ctx(request: Request, db: AsyncSession = Depends(get_db)) -> Optional[AuthContext]:
    """Signed-in user if there is one; public endpoints use this to show owners more."""
    try:
        return await _resolve(_bearer(request), request.headers.get("x-workspace"), db)
    except HTTPException:
        return None


def require_role(*roles: str):
    """Dependency: allow only these roles in the current workspace."""
    async def dep(ctx: AuthContext = Depends(get_ctx)) -> AuthContext:
        if ctx.role not in roles:
            raise HTTPException(status_code=403, detail="Your role doesn't allow this")
        return ctx
    return dep


require_owner = require_role("owner")
require_manager = require_role("owner", "admin")


async def get_owned_bot(bot_id: str, ctx: AuthContext, db: AsyncSession) -> Bot:
    """Fetch a bot in the caller's workspace, or 404 (never reveal other users' bots)."""
    clean = (bot_id or "").strip()[:36]
    bot = (await db.execute(select(Bot).where(Bot.bot_id == clean))).scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    if os.getenv("LOCAL_DEV", "false").lower() == "true":
        return bot
    if bot.user_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


# ─── Simple in-memory rate limiting for login-style endpoints ─────
_hits: dict = defaultdict(deque)


def rate_limit(key: str, limit: int, window_sec: int) -> None:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window_sec:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait a minute and try again.")
    q.append(now)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
