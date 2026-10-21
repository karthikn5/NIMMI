"""Indian phone number helpers: normalise to E.164, format and mask for display."""
import re
from typing import Optional


def to_e164(raw: Optional[str], default_country: str = "91") -> Optional[str]:
    """'+91 98765 43210', '098765 43210', '9876543210' -> '+919876543210'. None if not a number."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("+"):
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    if digits.startswith("00"):
        digits = digits[2:]
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"+{default_country}{digits}"
    if len(digits) == 12 and digits.startswith(default_country):
        return f"+{digits}"
    return None


def display(e164: Optional[str]) -> str:
    """'+919876543210' -> '+91 98765 43210'."""
    if not e164:
        return "Unknown"
    if e164.startswith("+91") and len(e164) == 13:
        n = e164[3:]
        return f"+91 {n[:5]} {n[5:]}"
    if e164.startswith("+1") and len(e164) == 12:  # US, Canada
        n = e164[2:]
        return f"+1 {n[:3]} {n[3:6]} {n[6:]}"
    if e164.startswith("+44") and len(e164) == 13:  # UK
        n = e164[3:]
        return f"+44 {n[:4]} {n[4:]}"
    if e164.startswith("+61") and len(e164) == 12:  # Australia
        n = e164[3:]
        return f"+61 {n[0]} {n[1:5]} {n[5:]}"
    return e164


def mask(e164: Optional[str]) -> str:
    """'+919876543210' -> '+91 98••• ••210'. Shown in lists; full number only in detail views."""
    if not e164:
        return "Unknown"
    if e164.startswith("+91") and len(e164) == 13:
        n = e164[3:]
        return f"+91 {n[:2]}••• ••{n[-3:]}"
    return e164[:4] + "•••" + e164[-3:]


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def extract_contact(captured: Optional[dict]) -> dict:
    """Find name / phone / email in captured fields, whatever the flow named them."""
    out: dict = {}
    for key, value in (captured or {}).items():
        if value is None:
            continue
        k, v = str(key).lower(), str(value).strip()
        if "email" in k or (_EMAIL.fullmatch(v) and "email" not in out):
            if _EMAIL.fullmatch(v):
                out["email"] = v
        elif any(w in k for w in ("phone", "mobile", "number", "whatsapp", "contact")) and to_e164(v):
            out["phone"] = to_e164(v)
        elif "name" in k and "name" not in out:
            out["name"] = v
    return out


# Country calling codes we place calls to (India, US/Canada, UK, Australia), set with CALL_COUNTRY_CODES.
# Anything else is refused, so a web form or an uploaded list can't make us ring premium-rate numbers
# abroad (international revenue share fraud).
_DEFAULT_CALL_CODES = "91,1,44,61"
# +1 numbers outside the US and Canada (the Caribbean), a common target of that fraud.
_RISKY_NANP = {"242", "246", "264", "268", "284", "345", "441", "473", "649", "658", "664", "721", "758",
               "767", "784", "809", "829", "849", "868", "869", "876"}


def callable_destination(e164: Optional[str]) -> bool:
    """True if we're willing to dial this number."""
    import os
    if not e164 or not e164.startswith("+"):
        return False
    digits = e164[1:]
    codes = [c.strip() for c in (os.getenv("CALL_COUNTRY_CODES") or _DEFAULT_CALL_CODES).split(",") if c.strip()]
    code = next((c for c in sorted(codes, key=len, reverse=True) if digits.startswith(c)), None)
    if code is None:
        return False
    if code == "1" and digits[1:4] in _RISKY_NANP:
        return False
    return True
