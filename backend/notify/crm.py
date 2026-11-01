"""
HubSpot and Zoho CRM (mail plan, phase 9). New leads and calls become a contact (HubSpot) or a lead (Zoho), found by email, else by phone, and email events become notes on them, the way LeadSquared
gets them as activities (mail/outbox.py keeps those and retries). HubSpot takes the token of a private app the business makes. Zoho connects through its permission page on Nimmi's own Zoho client, and
answers with the data centre the account lives in (India's: accounts.zoho.in, www.zohoapis.in), so only Zoho's own hosts are accepted. Salesforce isn't here: each customer would need a connected app.
"""
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from sqlalchemy import update
from sqlalchemy.future import select

from auth import decode_scoped_token, issue_scoped_token
from backend.models import IntegrationSettings
from database import async_session
from notify import email
from notify.channels import ChannelError

logger = logging.getLogger(__name__)

HUBSPOT = "https://api.hubapi.com"
NOTE_TO_CONTACT = 202  # HubSpot's association type
ZOHO_START = "https://accounts.zoho.com/oauth/v2/auth"  # every data centre starts here; the answer says where the account lives
ZOHO_SCOPES = "ZohoCRM.modules.leads.ALL,ZohoCRM.modules.notes.ALL"
ZOHO_ACCOUNTS = re.compile(r"https://accounts\.zoho\.(com|eu|in|com\.au|jp|com\.cn|sa|ca|uk)")
ZOHO_API = re.compile(r"https://www\.zohoapis\.(com|eu|in|com\.au|jp|com\.cn|sa|ca|uk)")
STATE_SECONDS = 600


def _url(real: str) -> str:
    """CRM_API_URL points local runs at a fake (dev-scripts/email/fake_crm.py)."""
    fake = os.getenv("CRM_API_URL")
    return f"{fake.rstrip('/')}/{real.split('://', 1)[1].split('/', 1)[1]}" if fake else real


def client(timeout: float = 15) -> httpx.AsyncClient:
    """Every call to a CRM goes through this (tests swap in a mock transport)."""
    return httpx.AsyncClient(timeout=timeout)


def _names(name: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    parts = (name or "").split()
    return (parts[0], " ".join(parts[1:]) or None) if parts else (None, None)


def _refused(service: str, resp: httpx.Response) -> ChannelError:
    if resp.status_code in (401, 403):
        return ChannelError(f"{service} refused the connection: connect it again in Integrations")
    return ChannelError(f"{service} {resp.status_code}: {resp.text[:300]}")


# ─── HubSpot ──────────────────────────────────────────────────────
async def _hubspot_contact(http: httpx.AsyncClient, token: str, email_address: Optional[str], phone: Optional[str], properties: dict) -> str:
    """The contact's id, made or updated."""
    auth = {"Authorization": f"Bearer {token}"}
    if email_address:
        resp = await http.post(_url(f"{HUBSPOT}/crm/v3/objects/contacts/batch/upsert"), headers=auth,
                               json={"inputs": [{"idProperty": "email", "id": email_address, "properties": {**properties, "email": email_address}}]})
        if resp.status_code >= 300:
            raise _refused("HubSpot", resp)
        return resp.json()["results"][0]["id"]
    resp = await http.post(_url(f"{HUBSPOT}/crm/v3/objects/contacts/search"), headers=auth, json={"filterGroups": [{"filters": [{"propertyName": "phone", "operator": "EQ", "value": phone}]}], "limit": 1})
    if resp.status_code >= 300:
        raise _refused("HubSpot", resp)
    found = resp.json().get("results") or []
    resp = await (http.patch(_url(f"{HUBSPOT}/crm/v3/objects/contacts/{found[0]['id']}"), headers=auth, json={"properties": properties}) if found
                  else http.post(_url(f"{HUBSPOT}/crm/v3/objects/contacts"), headers=auth, json={"properties": {**properties, "phone": phone}}))
    if resp.status_code >= 300:
        raise _refused("HubSpot", resp)
    return resp.json()["id"]


async def _hubspot_note(http: httpx.AsyncClient, token: str, contact_id: str, text: str, at: Optional[str] = None) -> None:
    when = at or datetime.now(timezone.utc).isoformat()
    resp = await http.post(_url(f"{HUBSPOT}/crm/v3/objects/notes"), headers={"Authorization": f"Bearer {token}"}, json={
        "properties": {"hs_timestamp": when, "hs_note_body": text[:60000]},
        "associations": [{"to": {"id": contact_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": NOTE_TO_CONTACT}]}]})
    if resp.status_code >= 300:
        raise _refused("HubSpot", resp)


async def hubspot_lead(token: str, lead: dict) -> None:
    """A lead or a call: the contact, and what was said as a note."""
    address, phone = lead.get("email"), lead.get("phone")
    if not address and not phone:
        raise ChannelError("No email or phone to find the contact by")
    first, last = _names(lead.get("name"))
    properties = {k: v for k, v in {"firstname": first, "lastname": last, "phone": phone}.items() if v}
    async with client() as http:
        contact = await _hubspot_contact(http, token, address, phone, properties)
        if lead.get("summary"):
            await _hubspot_note(http, token, contact, lead["summary"])


async def hubspot_note(token: str, address: str, text: str, at: Optional[str] = None) -> None:
    if not address:
        raise ChannelError("No email address to find the contact by")
    async with client() as http:
        await _hubspot_note(http, token, await _hubspot_contact(http, token, address, None, {}), text, at)


# ─── Zoho ─────────────────────────────────────────────────────────
def zoho_available() -> bool:
    return bool(os.getenv("ZOHO_CLIENT_ID") and os.getenv("ZOHO_CLIENT_SECRET"))


def _zoho_redirect() -> str:
    return f"{email.dashboard_url()}/dashboard/integrations"


def zoho_start_url(owner_id: str, person_id: str) -> str:
    state = issue_scoped_token(f"{owner_id}|{person_id}", "zoho_connect", STATE_SECONDS)
    return f"{_url(ZOHO_START)}?" + urlencode({"client_id": os.getenv("ZOHO_CLIENT_ID", ""), "response_type": "code", "scope": ZOHO_SCOPES, "access_type": "offline", "prompt": "consent",
                                              "redirect_uri": _zoho_redirect(), "state": state})


def zoho_state(state: str) -> Optional[tuple[str, str]]:
    parts = (decode_scoped_token(state or "", "zoho_connect") or "").split("|")
    return (parts[0], parts[1]) if len(parts) == 2 else None


async def zoho_finish(owner_id: str, code: str, accounts_server: str) -> None:
    """They came back with a code and the server their account lives on."""
    accounts = (accounts_server or "").rstrip("/")
    if not ZOHO_ACCOUNTS.fullmatch(accounts):
        raise ChannelError("That isn't one of Zoho's servers")
    async with client() as http:
        resp = await http.post(_url(f"{accounts}/oauth/v2/token"), data={"grant_type": "authorization_code", "code": code, "redirect_uri": _zoho_redirect(),
                                                                         "client_id": os.getenv("ZOHO_CLIENT_ID", ""), "client_secret": os.getenv("ZOHO_CLIENT_SECRET", "")})
    data = resp.json() if resp.status_code < 500 else {}
    api = str(data.get("api_domain") or "").rstrip("/")
    if not data.get("refresh_token") or not ZOHO_API.fullmatch(api):
        raise ChannelError("Zoho didn't connect: the page may have been open too long. Try again.")
    async with async_session() as db:
        s = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
        if s is None:
            s = IntegrationSettings(user_id=owner_id)
            db.add(s)
        s.zoho_enabled, s.zoho_accounts_url, s.zoho_api_domain = True, accounts, api
        s.zoho_refresh_token, s.zoho_access_token = data["refresh_token"], data.get("access_token")
        s.zoho_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in") or 3600))
        await db.commit()


async def zoho_disconnect(owner_id: str) -> None:
    async with async_session() as db:
        s = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
        if s is None:
            return
        accounts, refresh = s.zoho_accounts_url, s.zoho_refresh_token
        s.zoho_enabled, s.zoho_accounts_url, s.zoho_api_domain, s.zoho_refresh_token, s.zoho_access_token, s.zoho_expires_at = False, None, None, None, None, None
        await db.commit()
    if accounts and refresh:
        try:
            async with client() as http:
                await http.post(_url(f"{accounts}/oauth/v2/token/revoke"), params={"token": refresh})
        except httpx.HTTPError as e:
            logger.warning(f"Taking back a Zoho connection failed: {e!r}")


def _aware(at: Optional[datetime]) -> Optional[datetime]:
    return at.replace(tzinfo=timezone.utc) if at is not None and at.tzinfo is None else at


async def _zoho_token(owner_id: str) -> tuple[str, str]:
    """(an access token, the API's address). Zoho limits how often a refresh token is used, so the access token is kept for its hour."""
    async with async_session() as db:
        s = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == owner_id))).scalars().first()
        if s is None or not s.zoho_refresh_token:
            raise ChannelError("Zoho CRM isn't connected")
        if s.zoho_access_token and s.zoho_expires_at and _aware(s.zoho_expires_at) > datetime.now(timezone.utc) + timedelta(seconds=60):
            return s.zoho_access_token, s.zoho_api_domain
        accounts, refresh, api = s.zoho_accounts_url, s.zoho_refresh_token, s.zoho_api_domain
    async with client() as http:
        resp = await http.post(_url(f"{accounts}/oauth/v2/token"), data={"grant_type": "refresh_token", "refresh_token": refresh, "client_id": os.getenv("ZOHO_CLIENT_ID", ""),
                                                                         "client_secret": os.getenv("ZOHO_CLIENT_SECRET", "")})
    data = resp.json() if resp.status_code < 500 else {}
    if not data.get("access_token"):
        raise ChannelError("Zoho ended the connection: connect it again in Integrations")
    async with async_session() as db:
        await db.execute(update(IntegrationSettings).where(IntegrationSettings.user_id == owner_id).values(
            zoho_access_token=data["access_token"], zoho_expires_at=datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in") or 3600))))
        await db.commit()
    return data["access_token"], api


async def _zoho_upsert(http: httpx.AsyncClient, token: str, api: str, record: dict) -> str:
    resp = await http.post(_url(f"{api}/crm/v8/Leads/upsert"), headers={"Authorization": f"Zoho-oauthtoken {token}"}, json={"data": [record], "duplicate_check_fields": ["Email", "Phone"]})
    if resp.status_code >= 300:
        raise _refused("Zoho CRM", resp)
    row = (resp.json().get("data") or [{}])[0]
    if row.get("status") != "success":
        raise ChannelError(f"Zoho CRM: {str(row.get('message') or row)[:300]}")
    return row["details"]["id"]


async def zoho_lead(owner_id: str, lead: dict) -> None:
    address, phone = lead.get("email"), lead.get("phone")
    if not address and not phone:
        raise ChannelError("No email or phone to find the lead by")
    first, last = _names(lead.get("name"))
    record = {k: v for k, v in {"Last_Name": last or first or address or phone, "First_Name": first if last else None, "Email": address, "Phone": phone, "Description": lead.get("summary")}.items() if v}
    token, api = await _zoho_token(owner_id)
    async with client() as http:
        await _zoho_upsert(http, token, api, record)


async def zoho_note(owner_id: str, address: str, title: str, text: str) -> None:
    if not address:
        raise ChannelError("No email address to find the lead by")
    token, api = await _zoho_token(owner_id)
    auth = {"Authorization": f"Zoho-oauthtoken {token}"}
    async with client() as http:
        resp = await http.get(_url(f"{api}/crm/v8/Leads/search"), headers=auth, params={"email": address})
        if resp.status_code >= 300 and resp.status_code != 304:
            raise _refused("Zoho CRM", resp)
        found = resp.json().get("data") if resp.status_code == 200 and resp.content else None  # 204: nobody
        lead_id = found[0]["id"] if found else await _zoho_upsert(http, token, api, {"Last_Name": address, "Email": address})
        resp = await http.post(_url(f"{api}/crm/v8/Leads/{lead_id}/Notes"), headers=auth, json={"data": [{"Note_Title": title[:120], "Note_Content": text[:30000]}]})
    if resp.status_code >= 300:
        raise _refused("Zoho CRM", resp)
