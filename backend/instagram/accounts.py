"""
Connecting an Instagram professional account with Business Login for Instagram, keeping its sign-in alive, and the assistant that answers it.

A manager starts it on Instagram > Settings; Instagram sends them back there with a code, and the page finishes with the signed-in person's own token,
so a link someone else started can't attach your account to their workspace (the state names the workspace and the person). One account belongs to
one workspace: another workspace's account is named, not taken. The long-lived token lasts 60 days; it's renewed every week (Meta allows it once it's
a day old), and an account whose sign-in ended shows "Connect again" with what happened. Meta's removal and data deletion callbacks forget the sign-in.
"""
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import decode_scoped_token, issue_scoped_token
from backend.models import Bot, InstagramAccount, InstagramChat
from database import async_session
from instagram import graph
from notify import email

logger = logging.getLogger(__name__)

STATE_SECONDS = 900
RENEW_EVERY = timedelta(days=7)      # well inside the 60 days
PASS_EVERY = timedelta(minutes=30)
_last_pass: Optional[datetime] = None


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(at: Optional[datetime]) -> Optional[datetime]:
    return at.replace(tzinfo=timezone.utc) if at is not None and at.tzinfo is None else at


class Taken(Exception):
    """The account is connected to another Nimmi workspace."""


def redirect_uri() -> str:
    return f"{email.dashboard_url()}/dashboard/instagram/settings"


def start_url(owner_id: str, person_id: str) -> str:
    return graph.authorize_url(issue_scoped_token(f"{owner_id}|{person_id}", "instagram_connect", STATE_SECONDS), redirect_uri())


def read_state(state: str) -> Optional[tuple[str, str]]:
    parts = (decode_scoped_token(state or "", "instagram_connect") or "").split("|")
    return (parts[0], parts[1]) if len(parts) == 2 else None


async def finish(code: str, owner_id: str, person_id: str) -> tuple[str, list[str]]:
    """They came back from Instagram: a long-lived sign-in, the account, Meta told to send its DMs here. (account id, permissions not given)."""
    short, login_id, granted = await graph.exchange_code(code, redirect_uri())
    needed = [s for s in graph.SCOPES if s != graph.COMMENTS_SCOPE]  # comments are optional: DMs work without them
    missing = [s for s in needed if granted and s not in granted]
    token, seconds = await graph.long_lived(short)
    info = await graph.me(token)
    ig_id = str(info.get("user_id") or info.get("id"))[:64]
    at = now()
    async with async_session() as db:
        row = (await db.execute(select(InstagramAccount).where(InstagramAccount.ig_id == ig_id))).scalars().first()
        if row is not None and row.user_id != owner_id:
            if row.status != "disconnected":
                raise Taken(f"@{row.username or info.get('username') or ig_id} is already connected to another Nimmi account. Disconnect it there first.")
            row.ig_id = f"{ig_id}:moved:{row.id}"[:64]  # its old chats stay with the workspace that had them
            await db.flush()
            row = None
        if row is None:
            row = InstagramAccount(user_id=owner_id, ig_id=ig_id, ai_enabled=True, settings={})
            db.add(row)
        row.person_id, row.login_id = person_id, (login_id or None) and login_id[:64]
        row.username, row.name = (info.get("username") or "")[:120] or row.username, (info.get("name") or "")[:200] or row.name
        row.access_token, row.token_expires_at, row.token_refreshed_at = token, at + timedelta(seconds=seconds), at
        row.scopes = granted or list(graph.SCOPES)
        row.status, row.status_detail = ("permission", "Instagram messages weren't allowed. Connect again and allow everything it asks.") if missing else ("connected", None)
        await db.commit()
        account_id = row.id
    try:
        await graph.subscribe(ig_id, token, comments=not granted or graph.COMMENTS_SCOPE in granted)
        subscribed, detail = True, None
    except graph.IGError as e:
        subscribed, detail = False, f"Instagram didn't start sending its messages to Nimmi: {e}"
    async with async_session() as db:
        row = await db.get(InstagramAccount, account_id)
        row.subscribed = subscribed
        if detail and row.status == "connected":
            row.status, row.status_detail = "permission", detail[:500]
        await db.commit()
    return account_id, missing


async def assistant(db: AsyncSession, account: InstagramAccount) -> Optional[Bot]:
    """The assistant that answers this account: the one chosen, else the workspace's first active one."""
    if account.bot_id:
        bot = (await db.execute(select(Bot).where(Bot.bot_id == account.bot_id, Bot.user_id == account.user_id))).scalars().first()
        if bot:
            return bot
    return (await db.execute(select(Bot).where(Bot.user_id == account.user_id, Bot.is_active.is_(True)).order_by(Bot.created_at))).scalars().first()


async def by_ig_id(db: AsyncSession, ig_id: str) -> Optional[InstagramAccount]:
    if not ig_id:
        return None
    return (await db.execute(select(InstagramAccount).where(InstagramAccount.ig_id == str(ig_id)[:64],
                                                            InstagramAccount.status != "disconnected"))).scalars().first()


async def trouble(account_id: str, e: graph.IGError) -> None:
    """Instagram said the sign-in ended or access was taken away: the account shows its repair (Instagram > Settings)."""
    if e.kind not in ("token", "permission"):
        return
    async with async_session() as db:
        row = await db.get(InstagramAccount, account_id)
        if row is not None and row.status != "disconnected":
            row.status, row.status_detail = e.kind, str(e)[:500]
            await db.commit()


async def renew(account_id: str, at: Optional[datetime] = None) -> bool:
    """Another 60 days for its sign-in, claimed so one process does it. Whether it was renewed."""
    at = at or now()
    async with async_session() as db:
        claimed = await db.execute(update(InstagramAccount).where(
            InstagramAccount.id == account_id, InstagramAccount.status == "connected", InstagramAccount.token_refreshed_at <= at - RENEW_EVERY)
            .values(token_refreshed_at=at).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return False
        row = await db.get(InstagramAccount, account_id)
        token = row.access_token
    try:
        token, seconds = await graph.refresh(token)
    except graph.IGError as e:
        logger.warning(f"Instagram sign-in for account {account_id} not renewed: {e}")
        if e.kind == "token":
            await trouble(account_id, e)
        return False
    async with async_session() as db:
        row = await db.get(InstagramAccount, account_id)
        row.access_token, row.token_expires_at = token, at + timedelta(seconds=seconds)
        await db.commit()
    return True


async def tick(at: Optional[datetime] = None) -> None:
    """Scheduler: renew sign-ins a week old; an account whose sign-in has run out shows "Connect again"."""
    global _last_pass
    at = at or now()
    if _last_pass and at - _last_pass < PASS_EVERY:
        return
    _last_pass = at
    async with async_session() as db:
        ended = await db.execute(update(InstagramAccount).where(
            InstagramAccount.status == "connected", InstagramAccount.token_expires_at.isnot(None), InstagramAccount.token_expires_at < at)
            .values(status="token", status_detail="Instagram's sign-in for this account ran out. Connect it again.").execution_options(synchronize_session=False))
        due = (await db.execute(select(InstagramAccount.id).where(
            InstagramAccount.status == "connected", InstagramAccount.token_refreshed_at <= at - RENEW_EVERY).limit(50))).scalars().all()
        if ended.rowcount:
            await db.commit()
    for account_id in due:
        try:
            await renew(account_id, at)
        except Exception as e:  # noqa: BLE001  one account's trouble never stops the others
            logger.warning(f"Renewing Instagram account {account_id} failed: {e!r}")


async def disconnect(owner_id: str, account_id: str) -> None:
    """Nimmi stops answering it and forgets its sign-in. Its chats stay."""
    async with async_session() as db:
        row = (await db.execute(select(InstagramAccount).where(InstagramAccount.id == account_id, InstagramAccount.user_id == owner_id))).scalars().first()
        if row is None:
            raise LookupError(account_id)
        row.status, row.status_detail, row.access_token, row.subscribed = "disconnected", None, None, False
        await db.execute(update(InstagramChat).where(InstagramChat.account_id == account_id).values(reply_due_at=None)
                         .execution_options(synchronize_session=False))
        await db.commit()


def read_signed_request(value: str) -> Optional[dict]:
    """Meta's signed_request, if Nimmi's Instagram app secret signed it."""
    _, secret = graph.app()
    try:
        signature, payload = (value or "").split(".", 1)
        sent = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, TypeError):
        return None
    if not secret or not hmac.compare_digest(sent, expected) or str(data.get("algorithm") or "").upper() != "HMAC-SHA256":
        return None
    return data


async def forget(user_id: str) -> int:
    """Someone removed Nimmi's app in Instagram, or asked Meta to delete their data: the sign-ins that came from them go. How many."""
    async with async_session() as db:
        rows = (await db.execute(select(InstagramAccount).where(
            (InstagramAccount.login_id == str(user_id)) | (InstagramAccount.ig_id == str(user_id))))).scalars().all()
        for row in rows:
            row.status, row.status_detail, row.access_token, row.subscribed = "disconnected", "Removed in Instagram", None, False
        await db.commit()
    return len(rows)
