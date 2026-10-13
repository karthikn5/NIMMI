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


def _cfg(creds: Optional[dict] = None) -> dict:
    """Nimmi's own Exotel account from the environment, or a customer's (`creds`, same keys)."""
    if creds:
        return {"subdomain": "api.exotel.com", **creds}
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


def public_base() -> str:
    return (os.getenv("PUBLIC_BACKEND_URL") or os.getenv("BACKEND_URL") or "").rstrip("/")


def setup_urls(hook: Optional[str] = None) -> dict:
    """The addresses to paste into an Exotel flow (App Bazaar) for this account."""
    base, token = public_base(), hook or ws_secret()
    return {
        "voicebot": base.replace("https://", "wss://").replace("http://", "ws://") + f"/api/voice/ws/exotel/{token}",
        "after_bot": f"{base}/api/voice/exotel/after-bot?secret={token}",
        "transfer_target": f"{base}/api/voice/exotel/transfer-target?secret={token}",
    }


async def verify(creds: dict) -> None:
    """Check the account SID and API key and token work."""
    c = _cfg(creds)
    async with httpx.AsyncClient(timeout=20, auth=(c["key"], c["token"])) as client:
        resp = await client.get(f"https://{c['subdomain']}/v1/Accounts/{c['sid']}/Calls.json", params={"PageSize": 1})
    if resp.status_code in (401, 403):
        raise ExotelError("Exotel didn't accept that account SID, API key and API token")
    if resp.status_code >= 500 or resp.status_code == 404:
        raise ExotelError(f"Couldn't reach that Exotel account ({resp.status_code}). Check the account SID and region.")


async def place_call(to_e164: str, caller_id_e164: str, job_id: str, creds: Optional[dict] = None, hook: Optional[str] = None) -> str:
    """Ring `to_e164` from an ExoPhone and connect them to the voicebot flow. Returns the call SID."""
    c = _cfg(creds)
    if not (creds or configured()):
        raise ExotelError("Exotel isn't configured on the server")
    if not c.get("app_id"):
        raise ExotelError("Add the Exotel flow (app) ID for this account first")
    backend = public_base()
    data = {
        "From": to_e164,
        "CallerId": caller_id_e164,
        "Url": f"http://my.exotel.com/{c['sid']}/exoml/start_voice/{c['app_id']}",
        "CallType": "trans",
        "CustomField": job_id,
        "StatusCallback": f"{backend}/api/voice/exotel/status?secret={hook or ws_secret()}",
    }
    async with httpx.AsyncClient(timeout=20, auth=(c["key"], c["token"])) as client:
        resp = await client.post(f"https://{c['subdomain']}/v1/Accounts/{c['sid']}/Calls/connect.json", data=data)
    if resp.status_code >= 300:
        raise ExotelError(f"Exotel {resp.status_code}: {resp.text[:300]}")
    sid: Optional[str] = (resp.json().get("Call") or {}).get("Sid")
    if not sid:
        raise ExotelError("Exotel didn't return a call ID")
    return sid
