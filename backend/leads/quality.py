"""
The junk filter (instagram_plan.md, phase 2): a lead nobody could ever reach is marked, raises no alert and reaches nobody. Nothing is deleted, and a manager can overrule it.
A strange name isn't junk, and neither is a business trying its own form: only a way of reaching them that can't work counts.
"""
from datetime import timedelta
from typing import Optional

from mail import address
from phone import to_e164

REPEAT = timedelta(hours=24)  # the same person again this soon: the team has them already


def impossible(e164: Optional[str]) -> bool:
    """A number nobody has: one digit over and over, or an Indian number starting with 0 or 1 (mobiles start with 6 to 9, landlines with their area code, 2 to 8).
    98765 43210 isn't one: it's the usual made-up number, and also someone's real one."""
    if not e164:
        return False
    number = e164[3:] if e164.startswith("+91") else e164[1:]
    return len(set(number)) == 1 or (e164.startswith("+91") and number[:1] in ("0", "1"))


def why_junk(phone: Optional[str], email: Optional[str]) -> Optional[str]:
    """Why nobody could ever reach this lead, or None. `phone` as they gave it."""
    e164 = to_e164(phone or "")
    if (e164 and not impossible(e164)) or (email and not address.throwaway(address.domain_of(email))):
        return None
    if e164:
        return "The number can't be real"
    return "A throwaway email address" if email else None


def fresh(contact) -> bool:
    """Only a lead nothing real has happened with yet can be junk: someone who called, or was worked, is real whatever they type now."""
    return contact.quality is None and not contact.calls and (contact.stage or "new") == "new"
