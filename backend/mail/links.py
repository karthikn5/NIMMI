"""
Links in customer emails go through Nimmi (GET /api/email/l/<token>): the business sees who opened its price list or
pressed "Book a time", and a file is downloaded from Nimmi's storage without a public address of its own. A link made
for a preview or a test isn't recorded.
"""
import os
import secrets
from typing import Optional

from backend.models import EmailLink


def base() -> str:
    return (os.getenv("PUBLIC_BACKEND_URL") or os.getenv("BACKEND_URL", "http://localhost:8000")).rstrip("/")


class Tracker:
    """Collects the links of one email while it's made; `rows()` are then saved with the email."""

    def __init__(self, owner_id: str, job_id: Optional[str]):
        self.owner_id, self.job_id = owner_id, job_id
        self._rows: list[EmailLink] = []

    def __call__(self, url: str, kind: str, label: str) -> str:
        token = secrets.token_urlsafe(16)[:22]
        self._rows.append(EmailLink(token=token, user_id=self.owner_id, job_id=self.job_id, kind=kind,
                                    target=url, label=(label or "")[:200]))
        return f"{base()}/api/email/l/{token}"

    def rows(self) -> list[EmailLink]:
        return self._rows


def preview(url: str, kind: str, label: str) -> str:
    """In a preview or a test email: files go nowhere (they need a real email), other links go where they go."""
    return "#" if kind == "file" else url


MONTHS = 60 * 24 * 3600


def _signed(path: str, subject: str, scope: str, extra: str = "") -> str:
    from auth import issue_scoped_token
    return f"{base()}/api/email/p/{path}?token={issue_scoped_token(subject, scope, MONTHS)}{extra}"


def meeting_url(meeting_id: str, view: str = "") -> str:
    """Their meeting's page; `view`: change or cancel opens that part."""
    return _signed("meeting", meeting_id, "email_meeting", f"&view={view}" if view else "")


def book_url(owner_id: str, bot_id: str, to: str) -> str:
    return _signed("book", f"{owner_id}|{bot_id}|{to.lower()}", "email_book")


def call_url(owner_id: str, bot_id: str, to: str) -> str:
    return _signed("call", f"{owner_id}|{bot_id}|{to.lower()}", "email_call")


def rsvp_url(broadcast_id: str, to: str) -> str:
    return _signed("rsvp", f"{broadcast_id}|{to.lower()}", "email_rsvp")


def feedback_url(contact_id: str) -> str:
    return _signed("feedback", contact_id, "email_feedback")


async def actions_for(db, owner_id: str, bot_id: Optional[str], to: str) -> dict:
    """The Book a time and Call me buttons, when the assistant takes those (Voice > Schedule, on a plan with it)."""
    import plans
    from voice import schedule
    if not bot_id or not (await plans.includes(db, bot_id)).schedule:
        return {}
    settings = await schedule.settings_for(bot_id, db)
    return {**({"book": book_url(owner_id, bot_id, to)} if settings["meetings"]["enabled"] else {}),
            **({"call": call_url(owner_id, bot_id, to)} if settings["callbacks"]["enabled"] else {})}
