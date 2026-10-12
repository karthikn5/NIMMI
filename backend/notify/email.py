"""
Transactional email. Uses Resend when RESEND_API_KEY is set, otherwise SMTP
(SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS). With neither, it logs and
returns False so local development keeps working.
"""
import asyncio
import html
import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


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
                     reply_to: Optional[str] = None, from_name: Optional[str] = None) -> bool:
    if os.getenv("RESEND_API_KEY"):
        try:
            payload = {"from": _from(from_name), "to": [to], "subject": subject, "text": text, "html": html_body or _plain_html(text)}
            if reply_to:
                payload["reply_to"] = [reply_to]
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {os.getenv('RESEND_API_KEY')}"},
                    json=payload,
                )
            if resp.status_code >= 300:
                logger.error(f"Resend rejected email to {to}: {resp.status_code} {resp.text[:200]}")
                return False
            return True
        except Exception as e:
            logger.error(f"Resend error: {e}")
            return False

    host, user, password = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASS")
    if host and user and password:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, _from(from_name), to
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(text)
        msg.add_alternative(html_body or _plain_html(text), subtype="html")

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
            return False

    logger.warning(f"Email not configured; would have sent '{subject}' to {to}")
    return False


def _plain_html(text: str) -> str:
    body = "<br>".join(html.escape(line) for line in text.splitlines())
    return f'<div style="font-family:system-ui,sans-serif;font-size:14px;line-height:1.6;color:#1c1719">{body}</div>'


async def send_reset_email(email: str, token: str) -> bool:
    link = f"{dashboard_url()}/auth/reset-password?token={token}"
    if not is_configured():
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
