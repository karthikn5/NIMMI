"""
Authentication and access control.

Every dashboard request carries `Authorization: Bearer <token>`. The token
identifies the person; the optional `X-Workspace` header says whose workspace
they are acting in (their own, or one they were invited to as a team member).
"""
import hashlib
import logging
import math
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
from security import is_production, local_dev
try:
    from backend.models import Bot, TeamMember, User
except ImportError:
    from models import Bot, TeamMember, User

logger = logging.getLogger(__name__)

TOKEN_TTL_DAYS = 30
ROLES = ("owner", "admin", "agent")


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if secret:
        if is_production() and len(secret) < 32:
            raise RuntimeError("JWT_SECRET is too short. Use at least 32 random characters.")
        return secret
    if is_production():
        # A secret derived from other settings can be guessed by anyone who learns them, and then
        # sessions for any account can be forged. Production must have its own random secret.
        raise RuntimeError("JWT_SECRET is not set. Refusing to start in production without it.")
    # Stable local fallback so tokens survive restarts during development.
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


def _user_claims(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"require": ["exp", "iat", "sub"]})
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == "user" else None


def decode_token(token: str) -> Optional[str]:
    """The user id in a well-formed, unexpired session token. Use `user_for_token` to also check revocation."""
    claims = _user_claims(token)
    return claims.get("sub") if claims else None


def _issued_after(claims: dict, valid_after: Optional[datetime]) -> bool:
    if not valid_after:
        return True
    cutoff = valid_after if valid_after.tzinfo else valid_after.replace(tzinfo=timezone.utc)
    return int(claims.get("iat", 0)) >= int(cutoff.timestamp())


async def user_for_token(token: Optional[str], db: AsyncSession) -> Optional[str]:
    """The signed-in user's id, if the token is valid and wasn't revoked (password change, sign out everywhere)."""
    claims = _user_claims(token or "")
    if not claims:
        return None
    row = (await db.execute(select(User.id, User.tokens_valid_after).where(User.id == claims["sub"]))).first()
    if not row or not _issued_after(claims, row.tokens_valid_after):
        return None
    return row.id


def revoke_sessions(user: User) -> None:
    """Sign the user out everywhere; tokens issued from now on stay valid."""
    user.tokens_valid_after = datetime.now(timezone.utc).replace(microsecond=0)


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
    user_id = await user_for_token(token, db)
    if not user_id:
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
    if local_dev():
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
        minutes = math.ceil((window_sec - (now - q[0])) / 60)  # until the oldest attempt no longer counts
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again in "
                                                    + ("a minute." if minutes <= 1 else f"{minutes} minutes."))
    q.append(now)


def client_ip(request: Request) -> str:
    """
    The caller's address for rate limits. Proxies append to X-Forwarded-For, so the trustworthy
    entry is the one our own proxy added (the last one, with Railway's single hop). The first entry
    is whatever the caller typed and can't be trusted. TRUSTED_PROXY_HOPS adjusts this (e.g. 2 behind
    Cloudflare plus Railway; 0 when the app is reached directly).
    """
    hops = int(os.getenv("TRUSTED_PROXY_HOPS", "1") or 0)
    forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if hops > 0 and forwarded:
        return forwarded[-min(hops, len(forwarded))]
    return request.client.host if request.client else "unknown"
