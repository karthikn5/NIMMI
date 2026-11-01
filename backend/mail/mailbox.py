"""
Someone's own Gmail or Outlook (mail plan, phase 8). They connect it with Google or Microsoft, and one-to-one emails can go from it: the email agent's, after-call emails,
journeys, the team's answers in the Inbox. Bulk email never does. It's send-only on purpose: reading mail would be a restricted scope at Google, with a yearly security
audit. Replies come through Nimmi's reply address as they always did. Their calendar is here too: voice/calendars.py uses it for meetings.

Each mailbox has a daily limit, well under Google's (500 for a free Gmail, 2,000 for Workspace). When a mailbox can't send (it needs connecting again, it's over its limit, the
provider refuses), the email goes the usual way, so a customer's email never waits on it.
"""
import base64
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote, urlencode

import httpx
from sqlalchemy import case, or_, update
from sqlalchemy.future import select

import secretbox
from auth import decode_scoped_token, issue_scoped_token
from backend.models import MailConnection, User
from database import async_session
from notify import email

logger = logging.getLogger(__name__)

PROVIDERS = ("google", "microsoft")
PURPOSES = ("mail", "calendar")
SCOPES = {
    "google": {"mail": ["https://www.googleapis.com/auth/gmail.send"],
               "calendar": ["https://www.googleapis.com/auth/calendar.freebusy", "https://www.googleapis.com/auth/calendar.events.owned"]},
    "microsoft": {"mail": ["Mail.Send"], "calendar": ["Calendars.ReadWrite"]},
}
SIGN_IN = {"google": ["openid", "email", "profile"], "microsoft": ["openid", "email", "profile", "offline_access", "User.Read"]}
NEEDS = {"mail": ("gmail.send", "mail.send"), "calendar": ("calendar.events", "calendars.readwrite")}  # in the scopes granted (lowercase)
GOOGLE_AUTH, GOOGLE_TOKEN, GOOGLE_REVOKE = "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token", "https://oauth2.googleapis.com/revoke"
GMAIL_SEND = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
GOOGLE_CALENDAR = "https://www.googleapis.com/calendar/v3"
MICROSOFT_AUTH, MICROSOFT_TOKEN = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize", "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH = "https://graph.microsoft.com/v1.0"
STATE_SECONDS = 600
PAUSE = timedelta(hours=1)  # after the provider's sending limit
ONE_TO_ONE = ("agent", "after_call", "journey")  # what an assistant's mailbox sends; never bulk email


def daily_limit() -> int:
    return int(os.getenv("MAILBOX_DAILY_LIMIT", "200"))


class MailboxError(Exception):
    """The provider refused or couldn't be reached; the message is for the team."""


class NeedsReconnect(MailboxError):
    """Their permission is gone (revoked, a password change, a test app's 7 days): only they can give it back."""


@dataclass
class Tokens:
    access: str
    refresh: Optional[str]
    seconds: int
    scopes: list[str]
    id_token: Optional[str] = None


def _url(real: str) -> str:
    """MAILBOX_API_URL points local runs at a fake (dev-scripts/email/fake_mailbox.py)."""
    fake = os.getenv("MAILBOX_API_URL")
    return f"{fake.rstrip('/')}/{real.split('://', 1)[1].split('/', 1)[1]}" if fake else real


def client(timeout: float = 15) -> httpx.AsyncClient:
    """Every call to Google and Microsoft goes through this (tests swap in a mock transport)."""
    return httpx.AsyncClient(timeout=timeout)


def _credentials(provider: str) -> tuple[str, str]:
    prefix = "GOOGLE_MAIL" if provider == "google" else "MICROSOFT_MAIL"
    return os.getenv(f"{prefix}_CLIENT_ID", ""), os.getenv(f"{prefix}_CLIENT_SECRET", "")


def available() -> dict:
    """Which connections this server can offer: both need an app at the provider (mail_plan.md, decision 8)."""
    return {p: all(_credentials(p)) for p in PROVIDERS}


def _redirect() -> str:
    """Back to the dashboard, whose page finishes it with the signed-in person's token: a link someone else started can't attach your mailbox to their workspace."""
    return f"{email.dashboard_url()}/dashboard/email/settings"


def can(row: MailConnection, purpose: str) -> bool:
    granted = " ".join(row.scopes or []).lower()
    return any(s in granted for s in NEEDS[purpose])


def start_url(provider: str, purpose: str, owner_id: str, person_id: str) -> str:
    """Where to send the person. The state names who asked and for what; `finish` checks it against who comes back."""
    client_id, _ = _credentials(provider)
    state = issue_scoped_token(f"{provider}|{purpose}|{owner_id}|{person_id}", "mailbox_connect", STATE_SECONDS)
    query = {"client_id": client_id, "redirect_uri": _redirect(), "response_type": "code", "state": state,
             "scope": " ".join(SIGN_IN[provider] + SCOPES[provider][purpose])}
    if provider == "google":  # access_type + prompt: a refresh token every time; earlier grants are kept
        return f"{_url(GOOGLE_AUTH)}?{urlencode({**query, 'access_type': 'offline', 'prompt': 'consent', 'include_granted_scopes': 'true'})}"
    return f"{_url(MICROSOFT_AUTH)}?{urlencode({**query, 'response_mode': 'query', 'prompt': 'select_account'})}"


def read_state(state: str) -> Optional[dict]:
    subject = decode_scoped_token(state or "", "mailbox_connect")
    parts = (subject or "").split("|")
    return dict(zip(("provider", "purpose", "owner", "person"), parts)) if len(parts) == 4 else None


def _tokens(data: dict) -> Tokens:
    return Tokens(access=data["access_token"], refresh=data.get("refresh_token"), seconds=int(data.get("expires_in") or 3600),
                  scopes=str(data.get("scope") or "").split(), id_token=data.get("id_token"))


async def _token_request(provider: str, **fields) -> httpx.Response:
    client_id, secret = _credentials(provider)
    async with client() as http:
        return await http.post(_url(GOOGLE_TOKEN if provider == "google" else MICROSOFT_TOKEN),
                               data={"client_id": client_id, "client_secret": secret, **fields})


def _id_claims(id_token: Optional[str]) -> dict:
    """The name and address in the id token. It came straight from the provider over TLS, so its signature needn't be checked (OpenID Connect 3.1.3.7)."""
    try:
        part = (id_token or "").split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (IndexError, ValueError):
        return {}


async def _who(provider: str, tokens: Tokens) -> tuple[str, Optional[str]]:
    """(their address, their name)."""
    if provider == "google":
        claims = _id_claims(tokens.id_token)
        if not claims.get("email"):
            raise MailboxError("Google didn't say which account this is")
        return str(claims["email"]).lower(), claims.get("name")
    async with client() as http:
        resp = await http.get(_url(f"{GRAPH}/me"), headers={"Authorization": f"Bearer {tokens.access}"})
    if resp.status_code >= 300:
        raise MailboxError("Microsoft didn't say which account this is")
    me = resp.json()
    address = me.get("mail") or me.get("userPrincipalName")
    if not address:
        raise MailboxError("This Microsoft account has no mailbox")
    return str(address).lower(), me.get("displayName")


async def finish(provider: str, purpose: str, code: str, owner_id: str, person_id: str) -> MailConnection:
    """They came back with a code: keep what it gives. Connecting a second purpose adds to the same row."""
    resp = await _token_request(provider, code=code, grant_type="authorization_code", redirect_uri=_redirect())
    if resp.status_code >= 300:
        logger.warning(f"{provider} refused a connection: {resp.status_code} {resp.text[:200]}")
        raise MailboxError("That didn't work: the page may have been open too long. Try connecting again.")
    tokens = _tokens(resp.json())
    if not any(s in " ".join(tokens.scopes).lower() for s in NEEDS[purpose]):
        raise MailboxError("Sending email wasn't ticked on the permission page. Try again and tick it." if purpose == "mail"
                           else "The calendar wasn't ticked on the permission page. Try again and tick it.")
    address, name = await _who(provider, tokens)
    async with async_session() as db:
        row = (await db.execute(select(MailConnection).where(MailConnection.user_id == owner_id, MailConnection.provider == provider,
                                                             MailConnection.address == address))).scalars().first()
        if row is None:
            row = MailConnection(user_id=owner_id, provider=provider, address=address)
            db.add(row)
        row.person_id, row.name, row.status, row.error, row.paused_until = person_id, (name or "")[:120] or None, "connected", None, None
        row.scopes = sorted(set(row.scopes or []) | set(tokens.scopes))
        row.access_token, row.expires_at = secretbox.seal(tokens.access), datetime.now(timezone.utc) + timedelta(seconds=tokens.seconds)
        if tokens.refresh:
            row.refresh_token = secretbox.seal(tokens.refresh)
        await db.commit()
        return row


def _aware(at: Optional[datetime]) -> Optional[datetime]:
    return at.replace(tzinfo=timezone.utc) if at is not None and at.tzinfo is None else at


async def _needs_reconnect(connection_id: str, why: str) -> None:
    """Once: the row says so, and whoever connected it hears about it."""
    from notify import events
    async with async_session() as db:
        done = await db.execute(update(MailConnection).where(MailConnection.id == connection_id, MailConnection.status == "connected").values(status="reconnect", error=why[:300])
                                .execution_options(synchronize_session=False))
        await db.commit()
        if done.rowcount != 1:
            return
        row = await db.get(MailConnection, connection_id)
        settings = await events._settings(db, row.user_id)
        owner = (await db.execute(select(User.email).where(User.id == row.user_id))).scalar_one_or_none()
        person = (await db.execute(select(User.email).where(User.id == row.person_id))).scalar_one_or_none()
    text = (f"{row.address} needs connecting again: {why}\n\nUntil then your emails go from your usual address, and meetings stay off the calendar.\n\n"
            f"Connect it again: {email.dashboard_url()}/dashboard/email/settings")
    await events._once(row.user_id, "mailbox_reconnect", f"{connection_id}:{date.today().isoformat()}",
                       lambda: events._email_team([person] if person else events.recipients(settings, owner), f"Connect {row.address} again"[:150], text, row.user_id))


async def _token(connection_id: str, force: bool = False) -> tuple[str, str]:
    """(an access token, the provider). No database connection is held while the provider answers."""
    async with async_session() as db:
        row = await db.get(MailConnection, connection_id)
        if row is None or row.status != "connected" or not row.refresh_token:
            raise NeedsReconnect("It isn't connected")
        provider = row.provider
        if not force and row.access_token and row.expires_at and _aware(row.expires_at) > datetime.now(timezone.utc) + timedelta(seconds=60):
            return secretbox.unseal(row.access_token), provider
        refresh = secretbox.unseal(row.refresh_token)
    resp = await _token_request(provider, refresh_token=refresh, grant_type="refresh_token")
    if resp.status_code in (400, 401):
        try:
            error = str(resp.json().get("error") or "")
        except ValueError:
            error = ""
        if error in ("invalid_grant", "interaction_required", "consent_required", "unauthorized_client"):
            why = f"{'Google' if provider == 'google' else 'Microsoft'} ended the connection (a changed password, or access was removed)"
            await _needs_reconnect(connection_id, why)
            raise NeedsReconnect(why)
    if resp.status_code >= 300:
        raise MailboxError(f"{provider} answered {resp.status_code}")
    tokens = _tokens(resp.json())
    async with async_session() as db:
        values = {"access_token": secretbox.seal(tokens.access), "expires_at": datetime.now(timezone.utc) + timedelta(seconds=tokens.seconds)}
        if tokens.refresh:  # Microsoft gives a new one each time
            values["refresh_token"] = secretbox.seal(tokens.refresh)
        await db.execute(update(MailConnection).where(MailConnection.id == connection_id).values(**values))
        await db.commit()
    return tokens.access, provider


async def call(connection_id: str, method: str, url: str, **kw) -> httpx.Response:
    """An API call with their token, renewed once if the provider says it's stale."""
    token, _ = await _token(connection_id)
    headers = kw.pop("headers", {})
    async with client() as http:
        resp = await http.request(method, _url(url), headers={**headers, "Authorization": f"Bearer {token}"}, **kw)
        if resp.status_code == 401:
            token, _ = await _token(connection_id, force=True)
            resp = await http.request(method, _url(url), headers={**headers, "Authorization": f"Bearer {token}"}, **kw)
    if resp.status_code == 401:
        await _needs_reconnect(connection_id, "The provider stopped accepting the connection")
        raise NeedsReconnect("Its token was refused")
    return resp


def _refused_for_good(resp: httpx.Response) -> bool:
    """The permission itself is missing, not a limit."""
    return resp.status_code == 403 and any(s in resp.text for s in ("insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT", "ErrorAccessDenied", "AccessDenied"))


async def send(connection_id: str, to: str, subject: str, text: str, html_body: Optional[str], *, reply_to: Optional[str], from_name: Optional[str],
               unsubscribe_url: Optional[str] = None, headers: Optional[dict] = None, attachments: Optional[list[dict]] = None) -> Optional[email.Delivery]:
    """From their mailbox. None when it can't go this way now: the caller sends it the usual way."""
    today = date.today().isoformat()
    async with async_session() as db:
        row = await db.get(MailConnection, connection_id)
        if row is None or row.status != "connected" or not can(row, "mail"):
            return None
        if row.paused_until and _aware(row.paused_until) > datetime.now(timezone.utc):
            return None
        provider, address = row.provider, row.address
        name = from_name or row.name
        room = await db.execute(update(MailConnection).where(
            MailConnection.id == connection_id,
            or_(MailConnection.sent_day.is_(None), MailConnection.sent_day != today, MailConnection.sent_today < daily_limit())
        ).values(sent_today=case((MailConnection.sent_day == today, MailConnection.sent_today + 1), else_=1), sent_day=today).execution_options(synchronize_session=False))
        await db.commit()
        if room.rowcount != 1:
            return None
    clean = "".join(ch for ch in (name or "") if ch not in '<>"\r\n').strip()[:60]
    try:
        raw = email.mime(f'"{clean}" <{address}>' if clean else address, to, subject, text, html_body, reply_to, email.header_lines(unsubscribe_url, headers), attachments).as_bytes()
    except (ValueError, TypeError) as e:
        logger.warning(f"The email to {to} couldn't be written for {address}: {e}")
        return None
    try:
        if provider == "google":
            resp = await call(connection_id, "POST", GMAIL_SEND, json={"raw": base64.urlsafe_b64encode(raw).decode()})
        else:  # MIME so the Reply-To, the threading and List-Unsubscribe headers survive: Graph's JSON form only takes x- headers
            resp = await call(connection_id, "POST", f"{GRAPH}/me/sendMail", content=base64.b64encode(raw), headers={"Content-Type": "text/plain"})
    except MailboxError as e:
        logger.info(f"{address} couldn't send: {e}")
        return None
    except httpx.HTTPError as e:
        logger.warning(f"{address} couldn't be reached: {e!r}")
        return None
    if resp.status_code < 300:
        sent_id = resp.json().get("id") if provider == "google" else None
        return email.Delivery(True, id=f"{provider}:{sent_id or address}")
    if _refused_for_good(resp):
        await _needs_reconnect(connection_id, "Permission to send was removed")
    elif resp.status_code in (403, 429):  # its limit: the provider's, so leave it alone for a while
        async with async_session() as db:
            await db.execute(update(MailConnection).where(MailConnection.id == connection_id).values(paused_until=datetime.now(timezone.utc) + PAUSE, error="It reached its sending limit"))
            await db.commit()
    logger.warning(f"{address} refused an email: {resp.status_code} {resp.text[:200]}")
    return None


async def of_person(db, owner_id: str, person_id: Optional[str]) -> Optional[str]:
    """The mailbox someone on the team sends from, if they connected one."""
    if not person_id:
        return None
    rows = (await db.execute(select(MailConnection).where(MailConnection.user_id == owner_id, MailConnection.person_id == person_id, MailConnection.status == "connected"))).scalars().all()
    return next((r.id for r in rows if can(r, "mail")), None)


async def of_assistant(db, owner_id: str, bot_id: Optional[str]) -> Optional[str]:
    """The mailbox an assistant's one-to-one emails go from, if it has one and its plan has them."""
    import plans
    from mail import setup
    if not bot_id:
        return None
    chosen = (await setup.settings_for(db, bot_id))["mailbox"]["connection_id"]
    if not chosen or not (await plans.includes(db, bot_id)).email_alerts:
        return None
    row = await db.get(MailConnection, chosen)
    return row.id if row is not None and row.user_id == owner_id and row.status == "connected" and can(row, "mail") else None


async def disconnect(connection_id: str) -> None:
    """Forget it, and take back the permission where the provider lets us (Microsoft has no such call: it stays listed in their account until they remove it)."""
    async with async_session() as db:
        row = await db.get(MailConnection, connection_id)
        if row is None:
            return
        provider, refresh = row.provider, row.refresh_token
        await db.delete(row)
        await db.commit()
    if provider == "google" and refresh:
        try:
            async with client() as http:
                await http.post(f"{_url(GOOGLE_REVOKE)}?token={quote(secretbox.unseal(refresh), safe='')}")
        except Exception as e:
            logger.warning(f"Taking back a Google connection failed: {e!r}")


async def drop_person(owner_id: str, person_id: str) -> None:
    """They left the team: their mailbox and calendar go with them."""
    async with async_session() as db:
        ids = (await db.execute(select(MailConnection.id).where(MailConnection.user_id == owner_id, MailConnection.person_id == person_id))).scalars().all()
    for connection_id in ids:
        await disconnect(connection_id)
