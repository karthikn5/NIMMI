"""
All email Nimmi sends: its own (password resets, alerts to a business's team) and customer emails for the
businesses (mail plan). Uses Resend when RESEND_API_KEY is set, otherwise SMTP (SMTP_HOST / SMTP_PORT / SMTP_USER /
SMTP_PASS). With neither, it logs and fails, so local development keeps working.

Nimmi's own emails come from EMAIL_FROM; customer emails from CUSTOMER_EMAIL_FROM (a subdomain such as
mail.nimmiai.in, so customers' mail never affects password resets), or from the business's own verified domain.
"""
import asyncio
import base64
import html
import logging
import os
import re
import smtplib
from contextvars import ContextVar
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_last_error: ContextVar[Optional[str]] = ContextVar("email_last_error", default=None)


def last_error() -> Optional[str]:
    """Why the last send_email in this task failed, in words a business owner understands."""
    return _last_error.get()


@dataclass
class Delivery:
    ok: bool
    id: Optional[str] = None  # Resend's email id: its webhook events name the email by it
    error: Optional[str] = None


def _resend_reason(status: int, body: str) -> str:
    try:
        message = str(httpx.Response(status, content=body).json().get("message") or "")
    except Exception:
        message = body
    if "testing emails" in message or "verify a domain" in message:
        return "Resend is in test mode: it only sends to your own Resend address until your domain is verified"
    if "not verified" in message and "domain" in message:
        return "The sending domain isn't verified in Resend yet"
    if status in (401, 403) and "API key" in message:
        return "Resend rejected the API key"
    if status == 429 and "quota" in message:
        return "Resend's sending allowance for the day or month is used up"
    return f"Resend: {message[:200]}" if message else f"Resend returned {status}"


def resend_url() -> str:
    """Resend's API; RESEND_API_URL points local runs and tests at a fake (dev-scripts/email/fake_resend.py)."""
    return os.getenv("RESEND_API_URL", "https://api.resend.com").rstrip("/")


def resend_client(timeout: float = 15) -> httpx.AsyncClient:
    """Every call to Resend goes through this (tests swap in a mock transport)."""
    return httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "nimmi-ai"})  # Resend refuses requests without one


def dashboard_url() -> str:
    return os.getenv("DASHBOARD_URL", "https://nimmiai.in").rstrip("/")


def _sender() -> str:
    return os.getenv("EMAIL_FROM") or os.getenv("SMTP_USER") or "Nimmi AI <notifications@nimmiai.in>"


def customer_sender() -> str:
    """Where customer emails come from when the business has no verified domain of its own."""
    return os.getenv("CUSTOMER_EMAIL_FROM") or _sender()


def address_of(sender: str) -> str:
    return sender[sender.find("<") + 1:sender.find(">")] if "<" in sender else sender


def is_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY") or (os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASS")))


def _from(from_name: Optional[str], address: Optional[str] = None) -> str:
    """The From line: our sending address (or the one given), under the business's name ("Acme Realty <...>")."""
    sender = f"<{address}>" if address else _sender()
    if not from_name:
        return address or sender
    clean = "".join(ch for ch in from_name if ch not in '<>"\r\n').strip()[:60]
    return f'"{clean}" <{address_of(sender)}>' if clean else (address or sender)


_TAG = re.compile(r"[^A-Za-z0-9_-]")


def header_lines(unsubscribe_url: Optional[str], headers: Optional[dict]) -> dict:
    # One-click unsubscribe (RFC 8058): Gmail and Yahoo expect it on emails to customers.
    extra = {"List-Unsubscribe": f"<{unsubscribe_url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"} if unsubscribe_url else {}
    extra.update({k: v for k, v in (headers or {}).items() if v})
    return extra


def mime(sender: str, to: str, subject: str, text: str, html_body: Optional[str], reply_to: Optional[str], extra: dict,
         attachments: Optional[list[dict]]) -> EmailMessage:
    """The email itself, for SMTP and for someone's own mailbox (mail/mailbox.py). Raises ValueError on a header that can't be written."""
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, to
    if reply_to:
        msg["Reply-To"] = reply_to
    for k, v in extra.items():
        msg[k] = v
    msg.set_content(text)
    msg.add_alternative(html_body or _plain_html(text), subtype="html")
    for a in attachments or []:
        maintype, _, subtype = a["content_type"].partition("/")
        msg.add_attachment(_bytes(a["content"]), maintype=maintype, subtype=subtype.split(";")[0], filename=a["filename"])
    return msg


async def deliver(to: str, subject: str, text: str, html_body: Optional[str] = None, *,
                  reply_to: Optional[str] = None, from_name: Optional[str] = None, from_address: Optional[str] = None,
                  unsubscribe_url: Optional[str] = None, attachments: Optional[list[dict]] = None,
                  tags: Optional[dict] = None, idempotency_key: Optional[str] = None,
                  api_key: Optional[str] = None, headers: Optional[dict] = None) -> Delivery:
    """
    Send one email. `attachments`: [{"filename", "content" (text or bytes), "content_type"}], e.g. a calendar invite.
    `tags` (workspace, email, kind) come back on Resend's events; `idempotency_key` makes a repeated request a no-op at
    Resend for 24 hours; `api_key` is a domain's own sending key; `from_address` sends from that address; `headers` are
    added to the email (In-Reply-To and References keep a conversation together).
    """
    extra = header_lines(unsubscribe_url, headers)
    _last_error.set(None)
    key = api_key or os.getenv("RESEND_API_KEY")
    if key:
        payload = {"from": _from(from_name, from_address), "to": [to], "subject": subject, "text": text,
                   "html": html_body or _plain_html(text)}
        if reply_to:
            payload["reply_to"] = [reply_to]
        if extra:
            payload["headers"] = extra
        if attachments:
            payload["attachments"] = [{"filename": a["filename"], "content_type": a["content_type"],
                                       "content": base64.b64encode(_bytes(a["content"])).decode()} for a in attachments]
        if tags:
            payload["tags"] = [{"name": _TAG.sub("_", str(k))[:256], "value": _TAG.sub("_", str(v))[:256]}
                               for k, v in tags.items() if v]
        sending = {"Authorization": f"Bearer {key}"}
        if idempotency_key:
            sending["Idempotency-Key"] = idempotency_key[:256]
        try:
            async with resend_client() as client:
                for attempt in range(2):
                    resp = await client.post(f"{resend_url()}/emails", headers=sending, json=payload)
                    wait = resp.headers.get("retry-after")
                    # Over 10 requests a second (the team's limit, across four processes): wait it out once.
                    if resp.status_code == 429 and attempt == 0 and "quota" not in resp.text and (wait or "1").isdigit() and int(wait or "1") <= 2:
                        await asyncio.sleep(int(wait or "1"))
                        continue
                    break
            if resp.status_code >= 300:
                logger.error(f"Resend rejected email to {to}: {resp.status_code} {resp.text[:200]}")
                reason = _resend_reason(resp.status_code, resp.text)
                _last_error.set(reason)
                return Delivery(False, error=reason)
            try:
                provider_id = resp.json().get("id")
            except Exception:
                provider_id = None
            return Delivery(True, id=provider_id)
        except Exception as e:
            logger.error(f"Resend error: {e}")
            _last_error.set("Couldn't reach Resend")
            return Delivery(False, error="Couldn't reach Resend")

    host, user, password = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASS")
    if host and user and password:
        msg = mime(_from(from_name, from_address), to, subject, text, html_body, reply_to, extra, attachments)

        def _send():
            with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as s:
                s.starttls()
                s.login(user, password)
                s.send_message(msg)

        try:
            await asyncio.to_thread(_send)
            return Delivery(True)
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            _last_error.set(f"SMTP: {str(e)[:200]}")
            return Delivery(False, error=f"SMTP: {str(e)[:200]}")

    logger.warning(f"Email not configured; would have sent '{subject}' to {to}")
    _last_error.set("Email sending isn't set up on the server")
    return Delivery(False, error="Email sending isn't set up on the server")


async def send_email(to: str, subject: str, text: str, html_body: Optional[str] = None,
                     reply_to: Optional[str] = None, from_name: Optional[str] = None,
                     unsubscribe_url: Optional[str] = None, attachments: Optional[list[dict]] = None, **more) -> bool:
    """`deliver`, for callers that only need to know whether it went (`more`: deliver's other options)."""
    return (await deliver(to, subject, text, html_body, reply_to=reply_to, from_name=from_name,
                          unsubscribe_url=unsubscribe_url, attachments=attachments, **more)).ok


def _bytes(content) -> bytes:
    return content if isinstance(content, bytes) else str(content).encode()


def _plain_html(text: str) -> str:
    body = "<br>".join(html.escape(line) for line in text.splitlines())
    return f'<div style="font-family:system-ui,sans-serif;font-size:14px;line-height:1.6;color:#1c1719">{body}</div>'


async def send_reset_email(email: str, token: str) -> bool:
    link = f"{dashboard_url()}/auth/reset-password?token={token}"
    if not is_configured():
        from security import is_production
        if is_production():  # a reset link in the logs would let anyone who reads them take over the account
            logger.error("Email isn't configured, so a password reset email couldn't be sent")
        else:
            logger.warning(f"Email not configured. Password reset link for {email}: {link}")
        return False
    return await send_email(
        email,
        "Reset your Nimmi AI password",
        f"Hi,\n\nSomeone asked to reset the password for your Nimmi AI account.\n"
        f"Set a new password here (the link works for 1 hour):\n\n{link}\n\n"
        f"If this wasn't you, you can ignore this email.\n\nNimmi AI",
    )


async def send_invite_email(email: str, inviter: str, workspace: str, token: str) -> bool:
    link = f"{dashboard_url()}/auth/invite?token={token}"
    return await send_email(
        email,
        f"{inviter} invited you to {workspace} on Nimmi AI",
        f"Hi,\n\n{inviter} invited you to help manage {workspace} on Nimmi AI.\n\n"
        f"Accept the invite here:\n{link}\n\nNimmi AI",
    )
