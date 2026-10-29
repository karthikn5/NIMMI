"""
Voice product settings in one place. Business numbers (prices, free credits, credits per minute)
read from the environment so they can change without a deploy.
"""
import json
import os

# Bulbul v3 speaks these 11 languages (Saaras can listen to more, but replies need TTS).
LANGUAGES = ["en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN", "od-IN"]

# A curated subset of Sarvam Bulbul v3 speakers. Customers hear each with "Play".
VOICES = [
    {"id": "priya", "name": "Priya", "gender": "female"},
    {"id": "kavya", "name": "Kavya", "gender": "female"},
    {"id": "ritu", "name": "Ritu", "gender": "female"},
    {"id": "neha", "name": "Neha", "gender": "female"},
    {"id": "shreya", "name": "Shreya", "gender": "female"},
    {"id": "kavitha", "name": "Kavitha", "gender": "female"},
    {"id": "shubh", "name": "Shubh", "gender": "male"},
    {"id": "aditya", "name": "Aditya", "gender": "male"},
    {"id": "rahul", "name": "Rahul", "gender": "male"},
    {"id": "gokul", "name": "Gokul", "gender": "male"},
    {"id": "vijay", "name": "Vijay", "gender": "male"},
    {"id": "anand", "name": "Anand", "gender": "male"},
]
VOICE_IDS = {v["id"] for v in VOICES}
DEFAULT_VOICE = "priya"

STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")  # v3 supports the code-mix mode
TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")


# ─── Credits ──────────────────────────────────────────────────────
# Calls are paid for in credits: a call minute is 1 credit for hearing the caller, the voice and the phone line, plus the
# agent's AI model's credits (voice/ai_models.py, from 0.01 a minute). Measured on 40 test calls (Oct 2026): about 450
# spoken characters a minute, so speech and the phone line cost us roughly Rs 2.8 a minute (Rs 3.7 on a busy call). A
# pack credit sells for Rs 4.50-5.49: Bolna charges Rs 5.52 and Ringg Rs 6 a minute; Retell about Rs 7.2 before the model.
FREE_CREDITS = float(os.getenv("VOICE_FREE_CREDITS", "10"))  # every new workspace: tests and a first pilot
BILLING_STEP_SEC = 30  # calls are billed in half-minute steps (Bolna's 30-second pulses)


def _packs() -> list[dict]:
    packs = None
    if raw := os.getenv("VOICE_PACKS_JSON"):
        try:
            packs = json.loads(raw)
        except ValueError:
            pass
    packs = packs or [
        {"id": "p_100", "credits": 100, "price": 549},
        {"id": "p_500", "credits": 500, "price": 2499},
        {"id": "p_1000", "credits": 1000, "price": 4499},
    ]
    # Packs set before credits counted minutes: a minute was a standard-model minute, which is one credit.
    return [{**p, "credits": p.get("credits", p.get("minutes"))} for p in packs]


PACKS = _packs()
PACKS_BY_ID = {p["id"]: p for p in PACKS}

# Credits a bot plan includes each month, by plan name. Empty = plans include none.
PLAN_CREDITS: dict = json.loads(os.getenv("VOICE_PLAN_CREDITS_JSON") or os.getenv("VOICE_PLAN_MINUTES_JSON") or "{}")


NUMBER_MONTHLY_FEE = int(os.getenv("VOICE_NUMBER_MONTHLY_FEE", "999"))

CITIES = ["Chennai", "Coimbatore", "Bengaluru", "Hyderabad", "Mumbai", "Pune", "Delhi"]

# ─── Self-serve numbers (Twilio) ──────────────────────────────────
# India isn't here on purpose: Twilio can't provide Indian numbers for domestic calls (use Exotel).
SELF_SERVE_COUNTRIES = [
    {"code": "US", "name": "United States", "types": ["local", "toll_free"]},
    {"code": "CA", "name": "Canada", "types": ["local", "toll_free"]},
    {"code": "GB", "name": "United Kingdom", "types": ["local", "mobile"]},
    {"code": "AU", "name": "Australia", "types": ["local", "mobile"]},
]
SELF_SERVE_CODES = {c["code"] for c in SELF_SERVE_COUNTRIES}
USD_INR_RATE = float(os.getenv("USD_INR_RATE", "85"))
NUMBER_FEE_MARKUP = float(os.getenv("NUMBER_FEE_MARKUP", "2.0"))  # what customers pay vs. Twilio's price
NUMBER_GRACE_DAYS = int(os.getenv("NUMBER_GRACE_DAYS", "7"))
BALANCE_TOPUPS = [500, 1000, 2000, 5000]  # INR


def number_fee_inr(usd_per_month: float) -> int:
    """Monthly rupee fee for a number, rounded up to the nearest ₹10 (minimum ₹99)."""
    import math
    return max(99, math.ceil(usd_per_month * USD_INR_RATE * NUMBER_FEE_MARKUP / 10) * 10)
