"""
Exotel telephony: outbound callback calls into the voicebot flow.

Exotel flow to set up once in the Exotel dashboard (App Bazaar):
  1. Voicebot applet  -> wss://<backend>/api/voice/ws/exotel/<EXOTEL_WS_SECRET>
  2. Passthru applet  -> https://<backend>/api/voice/exotel/after-bot?secret=<EXOTEL_WS_SECRET>
       200 OK  -> Connect applet (dial number from URL:
                  https://<backend>/api/voice/exotel/transfer-target?secret=<EXOTEL_WS_SECRET>)
       other   -> Hangup applet
Inbound ExoPhones point at this same flow; outbound callbacks use EXOTEL_APP_ID.
"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class ExotelError(Exception):
    pass


def _cfg() -> dict:
    return {
        "sid": os.getenv("EXOTEL_ACCOUNT_SID", ""),
        "key": os.getenv("EXOTEL_API_KEY", ""),
        "token": os.getenv("EXOTEL_API_TOKEN", ""),
        "subdomain": os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com"),
        "app_id": os.getenv("EXOTEL_APP_ID", ""),
    }


def configured() -> bool:
    c = _cfg()
    return all([c["sid"], c["key"], c["token"], c["app_id"]])


def ws_secret() -> str:
    return os.getenv("EXOTEL_WS_SECRET", "")


async def place_call(to_e164: str, caller_id_e164: str, job_id: str) -> str:
    """Ring `to_e164` from our ExoPhone and connect them to the voicebot flow. Returns the call SID."""
    c = _cfg()
    if not configured():
        raise ExotelError("Exotel isn't configured on the server")
    backend = os.getenv("BACKEND_URL", "").rstrip("/")
    data = {
        "From": to_e164,
        "CallerId": caller_id_e164,
        "Url": f"http://my.exotel.com/{c['sid']}/exoml/start_voice/{c['app_id']}",
        "CallType": "trans",
        "CustomField": job_id,
        "StatusCallback": f"{backend}/api/voice/exotel/status?secret={ws_secret()}",
    }
    async with httpx.AsyncClient(timeout=20, auth=(c["key"], c["token"])) as client:
        resp = await client.post(f"https://{c['subdomain']}/v1/Accounts/{c['sid']}/Calls/connect.json", data=data)
    if resp.status_code >= 300:
        raise ExotelError(f"Exotel {resp.status_code}: {resp.text[:300]}")
    sid: Optional[str] = (resp.json().get("Call") or {}).get("Sid")
    if not sid:
        raise ExotelError("Exotel didn't return a call ID")
    return sid
