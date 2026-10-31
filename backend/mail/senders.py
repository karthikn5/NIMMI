"""
Who an assistant's customer emails come from: the name (also {{business}} in the text), the address, where replies go,
and the Resend key to send with. An assistant's own settings (EmailSender) come first, then the workspace's
(IntegrationSettings: sender_name, reply_to, sender_local, sender_domain_id), then the assistant's name.

The address is at the business's own domain once Resend has verified it; until then, and for businesses without one,
it is Nimmi's customer sending address (CUSTOMER_EMAIL_FROM) under the business's name.
"""
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.future import select

from backend.models import Bot, EmailDomain, EmailSender, IntegrationSettings
from notify import email

LOCAL_RE = re.compile(r"[a-z0-9](?:[a-z0-9._+-]{0,62}[a-z0-9])?")
DEFAULT_LOCAL = "hello"


@dataclass
class Sender:
    name: str                    # the From name, and {{business}}
    address: str                 # the From address
    reply_to: Optional[str]      # where replies go
    api_key: Optional[str]       # the domain's own sending key; None = Nimmi's key
    domain: Optional[str]        # the business's verified domain it's sent from; None = Nimmi's address


def clean_local(value: str) -> Optional[str]:
    """The part before the @, as typed ("Priya" -> "priya"); None if it can't be an address."""
    local = (value or "").strip().lower()
    return local if LOCAL_RE.fullmatch(local) and ".." not in local else None


async def sender_for(db, owner_id: str, bot_id: Optional[str] = None,
                     settings: Optional[IntegrationSettings] = None) -> Sender:
    if settings is None:
        settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
    own = await db.get(EmailSender, bot_id) if bot_id else None
    if own is not None and own.user_id != owner_id:
        own = None
    bot_name = (await db.execute(select(Bot.bot_name).where(Bot.bot_id == bot_id))).scalar_one_or_none() if bot_id else None

    name = (own.from_name if own else None) or (settings.sender_name if settings else None) or bot_name or "Our team"
    reply_to = (own.reply_to if own else None) or (settings.reply_to if settings else None)
    domain_id = (own.domain_id if own else None) or (settings.sender_domain_id if settings else None)
    local = (own.local_part if own else None) or (settings.sender_local if settings else None) or DEFAULT_LOCAL

    domain = None
    if domain_id:
        domain = (await db.execute(select(EmailDomain).where(
            EmailDomain.id == domain_id, EmailDomain.user_id == owner_id))).scalars().first()
    if domain is not None and domain.status == "verified":
        return Sender(name=name, address=f"{local}@{domain.name}", reply_to=reply_to,
                      api_key=domain.sending_key or None, domain=domain.name)
    return Sender(name=name, address=email.address_of(email.customer_sender()), reply_to=reply_to, api_key=None, domain=None)
