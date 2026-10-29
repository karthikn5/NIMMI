"""
Meta's WhatsApp Cloud API (the Graph API): sending messages and files, "typing…", fetching what customers send, and a
number's details. Every call goes through here, so they share time limits and turn Meta's error codes into sentences a
business can act on. Docs: https://developers.facebook.com/docs/whatsapp/cloud-api

Customers are addressed by phone number when Meta shares it, else by Meta's user id for them (BSUID, "IN.1349…"),
which Meta accepts in place of the number since July 2026.
"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

VERSION = os.getenv("WHATSAPP_API_VERSION", "v26.0")
# The local simulator (dev-scripts/whatsapp) points this at a fake Meta.
BASE = os.getenv("WHATSAPP_GRAPH_URL", "https://graph.facebook.com").rstrip("/")
TIMEOUT = httpx.Timeout(connect=6.0, read=25.0, write=60.0, pool=6.0)
BUTTON_CHARS, BUTTONS = 20, 3

# Meta's error codes, as the business should read them.
ERRORS = {
    131047: "The 24-hour window has closed: WhatsApp only allows an approved template now.",
    131026: "WhatsApp couldn't deliver it. The number may not use WhatsApp, or hasn't accepted WhatsApp's latest terms.",
    131030: "This test number can only message numbers added as recipients in your Meta app (API Setup).",
    131049: "Meta didn't deliver it, to limit how many marketing messages this person gets.",
    131050: "This person has turned off marketing messages from you.",
    131051: "WhatsApp doesn't support this kind of message.",
    131052: "The file couldn't be downloaded from WhatsApp.",
    131053: "WhatsApp couldn't take this file. Check its type and size.",
    131056: "Too many messages to this person in a short time. Try again in a moment.",
    131042: "There's a problem with the payment method on your WhatsApp account. Check it in WhatsApp Manager.",
    131031: "Meta has locked or restricted this WhatsApp account.",
    131048: "Meta is limiting this number because many of its messages were blocked or reported.",
    131000: "Something went wrong at WhatsApp. Try again.",
    130429: "This number is sending too fast. Try again in a moment.",
    133010: "This number isn't registered with the WhatsApp Cloud API yet.",
    368: "Meta has temporarily blocked this number for breaking its policies.",
    190: "The access token has expired or was revoked. Connect the number again with a new token.",
    10: "The access token doesn't have permission to use this number.",
    200: "The access token doesn't have permission to use this number.",
}


class GraphError(Exception):
    def __init__(self, message: str, code: Optional[int] = None, status: int = 0, detail: str = ""):
        super().__init__(message)
        self.code, self.status, self.detail = code, status, detail

    @property
    def window_closed(self) -> bool:
        return self.code == 131047

    @property
    def token_problem(self) -> bool:
        return self.code in (190, 10, 200)


def _error(resp: httpx.Response) -> GraphError:
    try:
        err = resp.json().get("error") or {}
    except ValueError:
        err = {}
    code = err.get("code")
    detail = str((err.get("error_data") or {}).get("details") or err.get("message") or resp.text[:200])[:300]
    plain = ERRORS.get(code) or f"WhatsApp refused it ({code or resp.status_code}): {detail}"
    return GraphError(plain, code, resp.status_code, detail)


async def _call(method: str, path: str, token: str, **kwargs) -> dict:
    if not token:
        raise GraphError("This number has no access token. Connect it again.")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.request(method, f"{BASE}/{VERSION}/{path}",
                                        headers={"Authorization": f"Bearer {token}"}, **kwargs)
    except httpx.HTTPError as e:
        raise GraphError(f"Couldn't reach WhatsApp ({type(e).__name__}). Try again.") from e
    if resp.status_code >= 300:
        raise _error(resp)
    try:
        return resp.json()
    except ValueError:
        return {}


def recipient(to: str) -> dict:
    """A phone number ("+91…" or digits) goes in "to"; Meta's user id for someone (it has a dot) in "recipient"."""
    to = (to or "").strip()
    return {"recipient": to} if "." in to else {"to": to.lstrip("+")}


async def send(phone_number_id: str, token: str, to: str, kind: str, body: dict,
               reply_to: Optional[str] = None) -> str:
    """Send one message; returns Meta's id for it (wamid)."""
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", **recipient(to), "type": kind, kind: body}
    if reply_to:
        payload["context"] = {"message_id": reply_to}
    data = await _call("POST", f"{phone_number_id}/messages", token, json=payload)
    return ((data.get("messages") or [{}])[0]).get("id", "")


async def send_text(phone_number_id: str, token: str, to: str, text: str, reply_to: Optional[str] = None) -> str:
    return await send(phone_number_id, token, to, "text", {"body": text[:4096], "preview_url": False}, reply_to)


async def send_media(phone_number_id: str, token: str, to: str, kind: str, media_id: str,
                     caption: Optional[str] = None, filename: Optional[str] = None, reply_to: Optional[str] = None) -> str:
    """kind: image, document, video or audio, already uploaded to Meta (upload_media)."""
    body: dict = {"id": media_id}
    if caption and kind in ("image", "video", "document"):
        body["caption"] = caption[:1024]
    if filename and kind == "document":
        body["filename"] = filename[:240]
    return await send(phone_number_id, token, to, kind, body, reply_to)


async def send_buttons(phone_number_id: str, token: str, to: str, text: str, buttons: list[str],
                       reply_to: Optional[str] = None) -> str:
    """A message with up to 3 reply buttons; a tap comes back as the customer's message."""
    action = {"buttons": [{"type": "reply", "reply": {"id": f"b{i}", "title": title[:BUTTON_CHARS]}}
                          for i, title in enumerate(buttons[:BUTTONS], 1)]}
    return await send(phone_number_id, token, to, "interactive",
                      {"type": "button", "body": {"text": text[:1024]}, "action": action}, reply_to)


async def typing(phone_number_id: str, token: str, wamid: str) -> None:
    """Mark their message read (blue ticks) and show "typing…" until the next message or 25 seconds. Best effort."""
    try:
        await _call("POST", f"{phone_number_id}/messages", token, json={
            "messaging_product": "whatsapp", "status": "read", "message_id": wamid, "typing_indicator": {"type": "text"}})
    except GraphError as e:
        logger.info(f"WhatsApp typing indicator not shown: {e}")


async def mark_read(phone_number_id: str, token: str, wamid: str) -> None:
    try:
        await _call("POST", f"{phone_number_id}/messages", token,
                    json={"messaging_product": "whatsapp", "status": "read", "message_id": wamid})
    except GraphError as e:
        logger.info(f"WhatsApp read receipt not sent: {e}")


async def upload_media(phone_number_id: str, token: str, content: bytes, mime: str, filename: str) -> str:
    """Put a file at Meta for sending; returns its media id (Meta keeps it 30 days)."""
    data = await _call("POST", f"{phone_number_id}/media", token, data={"messaging_product": "whatsapp", "type": mime},
                       files={"file": (filename, content, mime)})
    if not data.get("id"):
        raise GraphError("WhatsApp didn't accept the file.")
    return data["id"]


async def download_media(token: str, media_id: str, max_bytes: int) -> tuple[bytes, str]:
    """A file a customer sent: (content, mime type). Meta's link to it works for 5 minutes."""
    info = await _call("GET", media_id, token)
    if int(info.get("file_size") or 0) > max_bytes:
        raise GraphError("The file is too big to open here.")
    if not info.get("url"):
        raise GraphError("WhatsApp didn't give a link to the file.")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(info["url"], headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as e:
        raise GraphError(f"Couldn't download the file ({type(e).__name__}).") from e
    if resp.status_code >= 300 or len(resp.content) > max_bytes:
        raise GraphError("Couldn't download the file.")
    return resp.content, info.get("mime_type") or resp.headers.get("content-type", "application/octet-stream")


async def number_info(phone_number_id: str, token: str) -> dict:
    """The number as Meta has it: display number, approved name, quality rating."""
    return await _call("GET", phone_number_id, token,
                       params={"fields": "display_phone_number,verified_name,quality_rating,name_status"})


async def subscribe_app(waba_id: str, token: str) -> None:
    """Make Meta send this WhatsApp account's messages to the app (needed for numbers not added in the app itself)."""
    await _call("POST", f"{waba_id}/subscribed_apps", token)
