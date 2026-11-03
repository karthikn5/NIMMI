"""
Instagram's APIs, for an app using Business Login for Instagram (instagram_plan.md 4.7, phase 5): signing in, the long-lived token and its refresh,
the account, Meta's webhook subscription, sending DMs (text, quick replies, "typing…", seen), a person's profile, and files people send. Every call
goes through here, so they share time limits and turn Meta's error codes into sentences a business can act on.

Shapes as in Meta's documents, read 3 November 2026:
  developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login (authorize, code, short- and long-lived tokens)
  developers.facebook.com/docs/instagram-platform/reference/refresh_access_token
  developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api (+ /quick-replies, /sender-actions, /user-profile)
  developers.facebook.com/documentation/instagram-platform/webhooks/setup (subscribed_apps)
  developers.facebook.com/docs/messenger-platform/reference/send-api/error-codes
Where the documents disagree (sender actions shown on graph.facebook.com; the short-lived token's answer shown wrapped in "data"), both forms are
taken or the messaging page's form is used. The human agent tag's request isn't on Instagram's pages: it's Messenger's documented shape.
Tokens go in a header, except on Meta's own token endpoints, which take them in the address: those addresses never reach the logs.
"""
import logging
import os
from typing import Optional
from urllib.parse import urlencode

import httpx

from meta_leads import graph as _meta_graph  # noqa: F401  (its log filter hides access_token, client_secret and code in every httpx log line)

logger = logging.getLogger(__name__)

VERSION = os.getenv("INSTAGRAM_API_VERSION", "v26.0")
SCOPES = ("instagram_business_basic", "instagram_business_manage_messages", "instagram_business_manage_comments")
COMMENTS_SCOPE = "instagram_business_manage_comments"   # comment webhooks, private and public replies (phase 6)
# The webhook fields for DMs, as Meta's field list names them (its messaging guide spells two of them differently: tried after).
FIELDS = ("messages", "messaging_postbacks", "messaging_referral", "message_reactions", "messaging_seen")
FIELDS_ALSO = ("messages", "messaging_postbacks", "messaging_referrals", "messaging_reactions", "messaging_seen")
TEXT_BYTES = 1000          # "Message text must be UTF-8 and be a 1000 bytes or less"
QUICK_REPLIES, QUICK_CHARS = 13, 20
TIMEOUT = httpx.Timeout(connect=6.0, read=20.0, write=20.0, pool=6.0)
HUMAN_AGENT = "HUMAN_AGENT"


def graph_url() -> str:
    return os.getenv("INSTAGRAM_GRAPH_URL", "https://graph.instagram.com").rstrip("/")


def api_url() -> str:
    return os.getenv("INSTAGRAM_API_URL", "https://api.instagram.com").rstrip("/")


def dialog_url() -> str:
    return os.getenv("INSTAGRAM_DIALOG_URL", "https://www.instagram.com").rstrip("/")


def app() -> tuple[str, str]:
    """Nimmi's Instagram app: its id and secret from the App Dashboard (Instagram > API setup with Instagram business login)."""
    return os.getenv("INSTAGRAM_APP_ID", ""), os.getenv("INSTAGRAM_APP_SECRET", "")


def available() -> bool:
    app_id, secret = app()
    return bool(app_id and secret)


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT)


class IGError(Exception):
    """Instagram refused or couldn't be reached. `kind`: token (connect again), permission (the account's owner took access away, or a permission is
    missing), window (Instagram's reply window has closed), unavailable (this person can't get messages now), busy (try again shortly), error."""

    def __init__(self, message: str, kind: str = "error", code: Optional[int] = None, subcode: Optional[int] = None):
        super().__init__(message)
        self.kind, self.code, self.subcode = kind, code, subcode


WINDOW_CLOSED = ("Instagram's reply window has closed: anything may go within 24 hours of their last message, and only a person's reply "
                 "within 7 days.")
KNOWN = {  # (code, subcode): (kind, sentence). Meta's Send API error table, as read 3 November 2026.
    (10, 2534022): ("window", WINDOW_CLOSED),
    (10, 2018278): ("window", WINDOW_CLOSED),
    (200, 2534041): ("permission", "The account's owner turned off Nimmi's access to Instagram messages. Turn it on again in Instagram, then connect again."),
    (551, None): ("unavailable", "This person isn't receiving messages from you right now."),
    (551, 1545041): ("unavailable", "This person isn't available on Instagram right now."),
    (200, 1545041): ("unavailable", "This person isn't available on Instagram right now."),
    (10, 2018108): ("unavailable", "This person can't receive your messages right now."),
    (100, 2534014): ("error", "Instagram doesn't know this person any more."),
    (100, 2534029): ("permission", "Meta has blocked this account from sending messages through apps."),
    (100, 2534037): ("permission", "Another app is handling this conversation in Instagram, so Nimmi can't answer in it."),
    (10, 2534077): ("token", "Instagram couldn't confirm this account's connection. Connect it again."),
    (10, 1893063): ("busy", "Instagram has restricted sending from this account for a while."),
    (613, 2534040): ("busy", "Too many messages at once. Try again in a moment."),
}


def _error(resp: httpx.Response) -> IGError:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    err = body.get("error") if isinstance(body.get("error"), dict) else {}
    code = err.get("code") if err else body.get("code")
    sub = err.get("error_subcode")
    detail = str(err.get("message") or body.get("error_message") or resp.text[:200])[:300]
    try:
        code = int(code) if code is not None else None
        sub = int(sub) if sub is not None else None
    except (TypeError, ValueError):
        code, sub = None, None
    known = KNOWN.get((code, sub)) or KNOWN.get((code, None))
    if known:
        return IGError(known[1], known[0], code, sub)
    if code == 190 or (body.get("error_type") == "OAuthException" and resp.status_code in (400, 401) and "token" in detail.lower()):
        return IGError("Instagram's sign-in for this account has ended. Connect it again.", "token", code, sub)
    if code in (4, 17, 32, 613, 2) or resp.status_code >= 500 or resp.status_code == 429:
        return IGError("Instagram is busy. Nimmi will try again shortly.", "busy", code, sub)
    if code in (10, 200, 230, 3):
        return IGError("Instagram says Nimmi doesn't have permission for this. Connect the account again and allow everything it asks.",
                       "permission", code, sub)
    return IGError(f"Instagram refused it ({code or resp.status_code}): {detail}", "error", code, sub)


async def _request(method: str, url: str, *, token: Optional[str] = None, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with client() as http:
            resp = await http.request(method, url, headers=headers, **kwargs)
    except httpx.HTTPError as e:
        raise IGError(f"Couldn't reach Instagram ({type(e).__name__}). Try again.", "busy") from e
    if resp.status_code >= 300:
        raise _error(resp)
    try:
        data = resp.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _first(data: dict) -> dict:
    """Some answers come wrapped in "data": [ {...} ] (as Meta's documents show them), some flat: either way, the object."""
    wrapped = data.get("data")
    if isinstance(wrapped, list) and wrapped and isinstance(wrapped[0], dict):
        return wrapped[0]
    return data


# ─── signing in ──────────────────────────────────────────────────
def authorize_url(state: str, redirect_uri: str) -> str:
    app_id, _ = app()
    return f"{dialog_url()}/oauth/authorize?" + urlencode({"client_id": app_id, "redirect_uri": redirect_uri, "response_type": "code",
                                                            "scope": ",".join(SCOPES), "state": state})


async def exchange_code(code: str, redirect_uri: str) -> tuple[str, str, list[str]]:
    """The code from the redirect (valid an hour, once) for a short-lived token: (token, the id Instagram gave, permissions granted)."""
    app_id, secret = app()
    code = (code or "").split("#")[0].strip()  # "The #_ appended to the end of the redirect URI is not part of the code itself"
    data = _first(await _request("POST", f"{api_url()}/oauth/access_token", data={
        "client_id": app_id, "client_secret": secret, "grant_type": "authorization_code", "redirect_uri": redirect_uri, "code": code}))
    token = data.get("access_token")
    if not token:
        raise IGError("Instagram didn't give a sign-in. Try connecting again.", "token")
    granted = data.get("permissions") or ""
    granted = granted if isinstance(granted, list) else [p.strip() for p in str(granted).split(",") if p.strip()]
    return token, str(data.get("user_id") or ""), granted


async def long_lived(short_token: str) -> tuple[str, int]:
    """A short-lived token (an hour) for a long-lived one (60 days): (token, seconds it lasts)."""
    _, secret = app()
    data = await _request("GET", f"{graph_url()}/access_token", params={"grant_type": "ig_exchange_token", "client_secret": secret,
                                                                        "access_token": short_token})
    if not data.get("access_token"):
        raise IGError("Instagram didn't give a lasting sign-in. Try connecting again.", "token")
    return data["access_token"], int(data.get("expires_in") or 60 * 86400)


async def refresh(token: str) -> tuple[str, int]:
    """Another 60 days, for a long-lived token at least a day old and not expired."""
    data = await _request("GET", f"{graph_url()}/refresh_access_token", params={"grant_type": "ig_refresh_token", "access_token": token})
    if not data.get("access_token"):
        raise IGError("Instagram didn't renew the sign-in.", "token")
    return data["access_token"], int(data.get("expires_in") or 60 * 86400)


async def me(token: str) -> dict:
    """The professional account: user_id (the id in webhooks), username, name, account_type."""
    data = _first(await _request("GET", f"{graph_url()}/{VERSION}/me", token=token, params={"fields": "user_id,username,name,account_type"}))
    if not data.get("user_id") and not data.get("id"):
        raise IGError("Instagram didn't say which account this is.", "error")
    return data


async def subscribe(ig_id: str, token: str, comments: bool = False) -> None:
    """Meta sends this account's DMs (and comments, when that was allowed) to Nimmi's webhook. Meta's pages spell two of the fields two ways: the other
    spelling is tried if refused."""
    url = f"{graph_url()}/{VERSION}/{ig_id}/subscribed_apps"
    extra = ("comments",) if comments else ()
    try:
        await _request("POST", url, token=token, params={"subscribed_fields": ",".join(FIELDS + extra)})
    except IGError as e:
        if e.kind != "error":
            raise
        await _request("POST", url, token=token, params={"subscribed_fields": ",".join(FIELDS_ALSO + extra)})


# ─── sending ─────────────────────────────────────────────────────
async def send(ig_id: str, token: str, igsid: str, message: dict, tag: Optional[str] = None) -> str:
    """One DM; Meta's id for it (mid). `tag`: HUMAN_AGENT only, for a person's reply after 24 hours (outbound.py enforces who may use it)."""
    body: dict = {"recipient": {"id": igsid}, "message": message}
    if tag:
        body.update(messaging_type="MESSAGE_TAG", tag=tag)
    data = await _request("POST", f"{graph_url()}/{VERSION}/{ig_id}/messages", token=token, json=body)
    return str(data.get("message_id") or "")


def text_message(text: str, quick_replies: Optional[list[str]] = None) -> dict:
    message: dict = {"text": fit(text)}
    if quick_replies:
        message["quick_replies"] = [{"content_type": "text", "title": q[:QUICK_CHARS], "payload": f"q{i}"}
                                    for i, q in enumerate(quick_replies[:QUICK_REPLIES], 1)]
    return message


def fit(text: str, limit: int = TEXT_BYTES) -> str:
    """Within Instagram's 1,000 bytes (a Tamil letter is 3): cut at a word where it can be."""
    raw = (text or "").encode("utf-8")
    if len(raw) <= limit:
        return text or ""
    cut = raw[:limit].decode("utf-8", "ignore")
    space = cut.rfind(" ")
    return (cut[:space] if space > len(cut) // 2 else cut).rstrip()


async def private_reply(ig_id: str, token: str, comment_id: str, text: str) -> tuple[str, str]:
    """Instagram's private reply to a comment: one message, within 7 days of the comment. (message id, Meta's id for them in DMs)."""
    data = await _request("POST", f"{graph_url()}/{VERSION}/{ig_id}/messages", token=token,
                          json={"recipient": {"comment_id": comment_id}, "message": {"text": fit(text)}})
    return str(data.get("message_id") or ""), str(data.get("recipient_id") or "")


async def public_reply(comment_id: str, token: str, text: str) -> str:
    """A reply under the comment, for everyone to see (a reply to a reply goes under the top-level comment). Its comment id."""
    data = await _request("POST", f"{graph_url()}/{VERSION}/{comment_id}/replies", token=token, json={"message": text[:2200]})
    return str(data.get("id") or "")


async def media(ig_id: str, token: str, limit: int = 30) -> list[dict]:
    """The account's latest posts and reels, for choosing which a rule watches. Meta marks caption as Facebook Login only: asked for, and dropped if refused."""
    fields = "id,caption,media_type,permalink,timestamp,thumbnail_url,media_url"
    url = f"{graph_url()}/{VERSION}/{ig_id}/media"
    try:
        data = await _request("GET", url, token=token, params={"fields": fields, "limit": limit})
    except IGError as e:
        if e.kind != "error":
            raise
        data = await _request("GET", url, token=token, params={"fields": fields.replace("caption,", ""), "limit": limit})
    return [m for m in data.get("data") or [] if isinstance(m, dict) and m.get("id")]


async def set_profile(token: str, ice_breakers: list[str], menu: list[dict]) -> None:
    """Ice breakers (up to 4 questions; a tap comes back as the person's message) and the persistent menu, as the account's messenger profile. Empty
    ones are removed."""
    url = f"{graph_url()}/{VERSION}/me/messenger_profile"
    body: dict = {"platform": "instagram"}
    if ice_breakers:
        body["ice_breakers"] = [{"call_to_actions": [{"question": q[:80], "payload": f"ib{i}"} for i, q in enumerate(ice_breakers[:4], 1)], "locale": "default"}]
    if menu:
        body["persistent_menu"] = [{"locale": "default", "call_to_actions": [
            {"type": "web_url", "title": m["title"][:30], "url": m["url"]} if m.get("url") else {"type": "postback", "title": m["title"][:30], "payload": f"menu{i}"}
            for i, m in enumerate(menu[:5], 1)]}]
    gone = [f for f, have in (("ice_breakers", ice_breakers), ("persistent_menu", menu)) if not have]
    if len(body) > 1:
        await _request("POST", url, token=token, json=body)
    if gone:
        await _request("DELETE", url, token=token, json={"fields": gone})


async def action(ig_id: str, token: str, igsid: str, what: str) -> None:
    """typing_on, typing_off or mark_seen. Best effort: a refusal is only logged."""
    try:
        await _request("POST", f"{graph_url()}/{VERSION}/{ig_id}/messages", token=token, json={"recipient": {"id": igsid}, "sender_action": what})
    except IGError as e:
        logger.info(f"Instagram {what} not shown: {e}")


async def profile(igsid: str, token: str) -> dict:
    """Their name and username: only after they've written to the account, as Meta requires. The picture's address expires in days: not kept."""
    return _first(await _request("GET", f"{graph_url()}/{VERSION}/{igsid}", token=token, params={"fields": "name,username"}))


async def download(url: str, max_bytes: int) -> tuple[bytes, str]:
    """A file someone sent (Meta's own CDN address, from the webhook): (content, type)."""
    if not url or not url.startswith("https://") and not url.startswith(graph_url()):
        raise IGError("No address for the file.")
    try:
        async with client() as http:
            resp = await http.get(url, follow_redirects=True)
    except httpx.HTTPError as e:
        raise IGError(f"Couldn't download the file ({type(e).__name__}).", "busy") from e
    if resp.status_code >= 300 or len(resp.content) > max_bytes:
        raise IGError("Couldn't download the file.")
    return resp.content, resp.headers.get("content-type", "application/octet-stream")
