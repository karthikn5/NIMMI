"""
Transactional email. Uses Resend when RESEND_API_KEY is set, otherwise SMTP
(SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS). With neither, it logs and
returns False so local development keeps working.
"""
import asyncio
import base64
import html
import logging
import os
import smtplib
from contextvars import ContextVar
from email.message import EmailMessage
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_last_error: ContextVar[Optional[str]] = ContextVar("email_last_error", default=None)


def last_error() -> Optional[str]:
    """Why the last send_email in this task failed, in words a business owner understands."""
    return _last_error.get()


def _resend_reason(status: int, body: str) -> str:
    try:
        message = str(httpx.Response(status, content=body).json().get("message") or "")
    except Exception:
        message = body
    if "testing emails" in message or "verify a domain" in message:
        return "Resend is in test mode: it only sends to your own Resend address until your domain is verified"
    if status in (401, 403) and "API key" in message:
        return "Resend rejected the API key"
    return f"Resend: {message[:200]}" if message else f"Resend returned {status}"


def dashboard_url() -> str:
    return os.getenv("DASHBOARD_URL", "https://nimmiai.in").rstrip("/")


def _sender() -> str:
    return os.getenv("EMAIL_FROM") or os.getenv("SMTP_USER") or "Nimmi AI <notifications@nimmiai.in>"


def is_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY") or (os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASS")))


def _from(from_name: Optional[str]) -> str:
    """Our sending address, optionally under the business's name ("Acme Realty <notifications@...>")."""
    sender = _sender()
    if not from_name:
        return sender
    address = sender[sender.find("<") + 1:sender.find(">")] if "<" in sender else sender
    clean = "".join(ch for ch in from_name if ch not in '<>"\r\n').strip()[:60]
    return f'"{clean}" <{address}>' if clean else sender


async def send_email(to: str, subject: str, text: str, html_body: Optional[str] = None,
                     reply_to: Optional[str] = None, from_name: Optional[str] = None,
                     unsubscribe_url: Optional[str] = None, attachments: Optional[list[dict]] = None) -> bool:
    """`attachments`: [{"filename", "content" (text or bytes), "content_type"}], e.g. a calendar invite."""
    # One-click unsubscribe (RFC 8058): Gmail and Yahoo expect it on emails to customers.
    extra = {"List-Unsubscribe": f"<{unsubscribe_url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"} if unsubscribe_url else {}
    _last_error.set(None)
    if os.getenv("RESEND_API_KEY"):
        try:
            payload = {"from": _from(from_name), "to": [to], "subject": subject, "text": text, "html": html_body or _plain_html(text)}
            if reply_to:
                payload["reply_to"] = [reply_to]
            if extra:
                payload["headers"] = extra
            if attachments:
                payload["attachments"] = [{"filename": a["filename"], "content_type": a["content_type"],
                                           "content": base64.b64encode(_bytes(a["content"])).decode()} for a in attachments]
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {os.getenv('RESEND_API_KEY')}"},
                    json=payload,
                )
            if resp.status_code >= 300:
                logger.error(f"Resend rejected email to {to}: {resp.status_code} {resp.text[:200]}")
                _last_error.set(_resend_reason(resp.status_code, resp.text))
                return False
            return True
        except Exception as e:
            logger.error(f"Resend error: {e}")
            _last_error.set("Couldn't reach Resend")
            return False

    host, user, password = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASS")
    if host and user and password:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, _from(from_name), to
        if reply_to:
            msg["Reply-To"] = reply_to
        for k, v in extra.items():
            msg[k] = v
        msg.set_content(text)
        msg.add_alternative(html_body or _plain_html(text), subtype="html")
        for a in attachments or []:
            maintype, _, subtype = a["content_type"].partition("/")
            msg.add_attachment(_bytes(a["content"]), maintype=maintype, subtype=subtype.split(";")[0], filename=a["filename"])

        def _send():
            with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as s:
                s.starttls()
                s.login(user, password)
                s.send_message(msg)

        try:
            await asyncio.to_thread(_send)
            return True
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            _last_error.set(f"SMTP: {str(e)[:200]}")
            return False

    logger.warning(f"Email not configured; would have sent '{subject}' to {to}")
    _last_error.set("Email sending isn't set up on the server")
    return False


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
