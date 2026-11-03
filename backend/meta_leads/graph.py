"""
Meta's Graph API for lead ads (instagram_plan.md, phase 3): a person's sign-in and long-lived token, their Pages and each Page's own token, a Page's lead forms,
one lead, a form's leads since a time, and the Page's subscription to Nimmi's app. Every call goes through here, so they share a time limit and turn Meta's
errors into what a business can do about them.

Docs (read 2 Nov 2026): developers.facebook.com/docs/marketing-api/guides/lead-ads/retrieving, .../quickstart/webhooks-integration,
/docs/graph-api/webhooks/getting-started, /docs/facebook-login/guides/access-tokens/get-long-lived. Ids are numbers in Meta's examples and strings in
others: they're always kept as strings here.
"""
import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

VERSION = os.getenv("META_API_VERSION", "v26.0")
TIMEOUT = httpx.Timeout(connect=6.0, read=20.0, write=20.0, pool=6.0)
LEAD_FIELDS = "created_time,id,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,form_id,field_data,custom_disclaimer_responses,is_organic,platform"
FORM_FIELDS = "id,name,status,locale,leads_count,created_time"
SCOPES = ("leads_retrieval", "pages_manage_metadata", "pages_show_list", "pages_read_engagement", "ads_management", "pages_manage_ads")
SECRET_PARAMS = ("access_token", "client_secret", "fb_exchange_token", "code", "input_token")


class _HideSecrets(logging.Filter):
    """httpx logs every request's address at INFO: a token, code or app secret in it must never reach the logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_hidden(a) if isinstance(a, httpx.URL) else a for a in record.args)
        return True


def _hidden(url: httpx.URL) -> httpx.URL:
    if not any(k in url.params for k in SECRET_PARAMS):
        return url
    return url.copy_with(params=[(k, "hidden" if k in SECRET_PARAMS else v) for k, v in url.params.multi_items()])


logging.getLogger("httpx").addFilter(_HideSecrets())


class GraphError(Exception):
    """Meta refused or couldn't be reached. `kind`: token (they must connect again), permission (a permission or Leads Access is missing), busy (try again
    later), gone (the Page, form or lead isn't there or isn't theirs any more), error."""

    def __init__(self, message: str, kind: str = "error", code: Optional[int] = None):
        super().__init__(message)
        self.kind, self.code = kind, code


def base() -> str:
    """META_GRAPH_URL points local runs and tests at a fake (dev-scripts/meta/fake_graph.py)."""
    return os.getenv("META_GRAPH_URL", "https://graph.facebook.com").rstrip("/")


def dialog() -> str:
    return os.getenv("META_DIALOG_URL", "https://www.facebook.com").rstrip("/")


def app() -> tuple[str, str]:
    """Nimmi's own Meta app: its id and secret."""
    return os.getenv("META_APP_ID", ""), os.getenv("META_APP_SECRET", "")


def available() -> bool:
    """Connecting needs Nimmi's Meta app and its Facebook Login for Business configuration (instagram_plan.md, Phase 0)."""
    return all(app()) and bool(os.getenv("META_LOGIN_CONFIG_ID"))


def client() -> httpx.AsyncClient:
    """Every call to Meta goes through this (tests swap in a mock transport)."""
    return httpx.AsyncClient(timeout=TIMEOUT)


def _kind(status: int, error: dict) -> str:
    code, sub = error.get("code"), error.get("error_subcode")
    if code in (190, 102):  # expired, changed password, removed the app: only they can give it back
        return "token"
    if code in (4, 17, 32, 613, 80000, 80001) or status in (429, 503) or status >= 500 or error.get("is_transient"):
        return "busy"
    if code == 100 and sub == 33:
        return "gone"
    if code in (10, 200, 294) or (isinstance(code, int) and 200 <= code < 300):
        return "permission"
    return "error"


MESSAGES = {
    "token": "Facebook's sign-in for this connection has ended. Connect again from Leads > Sources.",
    "permission": "Facebook didn't allow reading these leads. The person who connected needs a Page role that can advertise, and Leads Access in Meta Business Suite.",
    "busy": "Facebook is busy. Nimmi will try again.",
    "gone": "Facebook says this Page, form or lead isn't there any more, or isn't shared with this connection.",
}


async def call(method: str, path: str, token: Optional[str] = None, params: Optional[dict] = None) -> dict:
    """One Graph call. The token goes in a header, never the address."""
    url = f"{base()}/{VERSION}/{path.lstrip('/')}"
    try:
        async with client() as http:
            resp = await http.request(method, url, params=params or {}, headers={"Authorization": f"Bearer {token}"} if token else {})
    except httpx.HTTPError as e:
        raise GraphError(MESSAGES["busy"], "busy") from e
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
        error = (data.get("error") if isinstance(data, dict) else None) or {}
        kind = _kind(resp.status_code, error)
        logger.warning(f"Meta refused {method} {path.split('?')[0]}: {resp.status_code} {error.get('code')} {str(error.get('message'))[:200]}")
        raise GraphError(MESSAGES.get(kind) or str(error.get("message") or "Facebook refused")[:300], kind, error.get("code"))
    return data if isinstance(data, dict) else {}


# ─── signing in ──────────────────────────────────────────────────
async def user_token(code: str, redirect: str) -> str:
    """The code from Facebook's dialog, as a user token, then a long-lived one (about 60 days): Page tokens made from it don't expire."""
    app_id, secret = app()
    short = await call("GET", "oauth/access_token", params={"client_id": app_id, "client_secret": secret, "redirect_uri": redirect, "code": code})
    long = await call("GET", "oauth/access_token", params={"grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": secret,
                                                           "fb_exchange_token": short["access_token"]})
    return long["access_token"]


async def me(token: str) -> dict:
    return await call("GET", "me", token, {"fields": "id,name"})


async def granted(token: str) -> list[str]:
    """The permissions the person really gave: Facebook's dialog lets them leave some out."""
    data = await call("GET", "me/permissions", token)
    return [p["permission"] for p in data.get("data", []) if p.get("status") == "granted"]


async def pages(token: str) -> list[dict]:
    """Their Pages, each with its own token and what they may do on it (ADVERTISE is needed for leads)."""
    found, after = [], None
    for _ in range(20):
        data = await call("GET", "me/accounts", token, {"fields": "id,name,access_token,tasks", "limit": 100, **({"after": after} if after else {})})
        found += data.get("data", [])
        after = (data.get("paging") or {}).get("cursors", {}).get("after") if (data.get("paging") or {}).get("next") else None
        if not after:
            break
    return [{"id": str(p["id"]), "name": p.get("name") or "", "token": p.get("access_token"), "tasks": p.get("tasks") or []} for p in found if p.get("id")]


async def subscribe(page_id: str, page_token: str) -> None:
    """The Page sends Nimmi's app its new leads (Meta: both the app's subscription and the Page's are needed)."""
    await call("POST", f"{page_id}/subscribed_apps", page_token, {"subscribed_fields": "leadgen"})


async def unsubscribe(page_id: str, page_token: str) -> None:
    await call("DELETE", f"{page_id}/subscribed_apps", page_token)


async def subscribed(page_id: str, page_token: str) -> bool:
    app_id, _ = app()
    data = await call("GET", f"{page_id}/subscribed_apps", page_token)
    return any(str(a.get("id")) == app_id and "leadgen" in (a.get("subscribed_fields") or ["leadgen"]) for a in data.get("data", []))


async def forms(page_id: str, page_token: str) -> list[dict]:
    found, after = [], None
    for _ in range(20):
        data = await call("GET", f"{page_id}/leadgen_forms", page_token, {"fields": FORM_FIELDS, "limit": 100, **({"after": after} if after else {})})
        found += data.get("data", [])
        after = (data.get("paging") or {}).get("cursors", {}).get("after") if (data.get("paging") or {}).get("next") else None
        if not after:
            break
    return [{"id": str(f["id"]), "name": f.get("name") or "", "status": f.get("status") or "", "leads": f.get("leads_count")} for f in found if f.get("id")]


async def lead(leadgen_id: str, page_token: str) -> dict:
    return await call("GET", str(leadgen_id), page_token, {"fields": LEAD_FIELDS})


async def leads_since(form_id: str, page_token: str, since: int, after: Optional[str] = None) -> tuple[list[dict], Optional[str]]:
    """One page of a form's leads created after `since` (a Unix time), and the cursor for the next page. Graph's paging: no `next`, no more pages."""
    params = {"fields": LEAD_FIELDS, "limit": 100, "filtering": json.dumps([{"field": "time_created", "operator": "GREATER_THAN", "value": int(since)}])}
    data = await call("GET", f"{form_id}/leads", page_token, {**params, **({"after": after} if after else {})})
    paging = data.get("paging") or {}
    return data.get("data", []), (paging.get("cursors") or {}).get("after") if paging.get("next") else None
