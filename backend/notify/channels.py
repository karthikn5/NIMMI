"""WhatsApp (Meta Cloud API), signed CRM webhooks and LeadSquared."""
import hashlib
import hmac
import json
import logging
import os
from typing import Optional

import httpx

from netsafe import UnsafeUrl, assert_public_url

logger = logging.getLogger(__name__)


class ChannelError(Exception):
    pass


def whatsapp_configured(token: Optional[str] = None, phone_number_id: Optional[str] = None) -> bool:
    return bool((token or os.getenv("WHATSAPP_TOKEN")) and (phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID")))


async def send_whatsapp_template(
    to_e164: str,
    template: str,
    language: str,
    body_params: list[str],
    phone_number_id: Optional[str] = None,
    token: Optional[str] = None,
) -> None:
    """Send an approved WhatsApp template. Raises ChannelError on failure."""
    tok = token or os.getenv("WHATSAPP_TOKEN")
    pid = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not (tok and pid):
        raise ChannelError("WhatsApp isn't configured on the server")
    version = os.getenv("WHATSAPP_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{version}/{pid}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164.lstrip("+"),
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": language or "en"},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": p[:1000]} for p in body_params]}],
        },
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers={"Authorization": f"Bearer {tok}"}, json=payload)
    if resp.status_code >= 300:
        raise ChannelError(f"WhatsApp {resp.status_code}: {resp.text[:300]}")


async def send_whatsapp_text(
    to_e164: str,
    text: str,
    phone_number_id: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Send a free-form text message over WhatsApp Meta Cloud API. Raises ChannelError on failure."""
    tok = token or os.getenv("WHATSAPP_TOKEN")
    pid = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not (tok and pid):
        raise ChannelError("WhatsApp credentials (token or phone_number_id) are not configured")
    version = os.getenv("WHATSAPP_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{version}/{pid}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_e164.lstrip("+"),
        "type": "text",
        "text": {"preview_url": False, "body": text[:4096]},
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers={"Authorization": f"Bearer {tok}"}, json=payload)
    if resp.status_code >= 300:
        raise ChannelError(f"WhatsApp {resp.status_code}: {resp.text[:300]}")
    return resp.json()


async def mark_whatsapp_read(
    message_id: str,
    phone_number_id: Optional[str] = None,
    token: Optional[str] = None,
) -> None:
    """Mark an inbound WhatsApp message as read (shows blue checkmarks)."""
    tok = token or os.getenv("WHATSAPP_TOKEN")
    pid = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not (tok and pid):
        return
    version = os.getenv("WHATSAPP_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{version}/{pid}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(url, headers={"Authorization": f"Bearer {tok}"}, json=payload)
    except Exception as e:
        logger.debug(f"Failed to mark WhatsApp message {message_id} as read: {e}")



def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def post_webhook(url: str, secret: Optional[str], event: str, data: dict) -> None:
    """POST a JSON event. Receivers verify X-Nimmi-Signature = HMAC-SHA256(secret, body)."""
    try:
        url = await assert_public_url(url)
    except UnsafeUrl as e:
        raise ChannelError(str(e))
    body = json.dumps({"event": event, "data": data}, default=str).encode()
    headers = {"Content-Type": "application/json", "X-Nimmi-Event": event}
    if secret:
        headers["X-Nimmi-Signature"] = sign(secret, body)
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        resp = await client.post(url, content=body, headers=headers)
    if resp.status_code >= 300:
        raise ChannelError(f"Webhook returned {resp.status_code}")


async def push_leadsquared(host: str, access_key: str, secret_key: str, lead: dict) -> None:
    """Create or update a lead in LeadSquared (Lead.Capture de-duplicates on phone/email)."""
    host = host.replace("https://", "").replace("http://", "").strip("/")
    if not host.endswith("leadsquared.com"):
        raise ChannelError("LeadSquared host should look like api-in21.leadsquared.com")
    attributes = [
        ("FirstName", lead.get("name")),
        ("Phone", lead.get("phone")),
        ("EmailAddress", lead.get("email")),
        ("Source", "Nimmi AI"),
        ("Notes", lead.get("summary")),
    ]
    body = [{"Attribute": k, "Value": v} for k, v in attributes if v]
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://{host}/v2/LeadManagement.svc/Lead.Capture",
            params={"accessKey": access_key, "secretKey": secret_key},
            json=body,
        )
    if resp.status_code >= 300:
        raise ChannelError(f"LeadSquared {resp.status_code}: {resp.text[:300]}")
