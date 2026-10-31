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
