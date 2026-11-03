"""
Meta's webhook for Instagram DMs (one callback URL for every connected account, set once in Nimmi's Meta app: Webhooks, the Instagram object). GET is
Meta checking the URL with the verify token; POST brings DMs and what happens to them. A POST is answered only once what it brought is kept, so if
something fails Meta sends it again for up to 36 hours (repeats are recognised by Meta's message id). Nothing slow happens before the answer:
understanding files and writing replies run afterwards (replies.py).

The body must be signed (X-Hub-Signature-256: sha256 of the raw body with the app secret). Meta's pages say "your app's App Secret" without saying
whether that's the Instagram app secret or the Meta app's: both are Nimmi's own, so either is accepted. Each entry is for one account, by its id; an
entry for an account nobody has connected is ignored, and one account's DMs only ever reach the workspace that connected it. Meta's removal and data
deletion callbacks forget the sign-ins of the person they name.
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import NotificationLog
from database import async_session, get_db
from instagram import accounts, comments, inbound
from notify.events import fire_and_forget
from security import local_dev

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instagram", tags=["instagram"])

MAX_BODY = 2 * 1024 * 1024  # Meta batches up to 1,000 updates


def verify_token() -> str:
    return os.getenv("INSTAGRAM_VERIFY_TOKEN") or ("nimmi_ig_verify" if local_dev() else "")


def _secrets() -> list[str]:
    return [s for s in (os.getenv("INSTAGRAM_APP_SECRET", ""), os.getenv("META_APP_SECRET", "")) if s]


def signed(raw: bytes, header: Optional[str]) -> bool:
    keys = _secrets()
    if not keys:
        return local_dev()  # only on a developer's machine: anyone could post fake DMs and make the account answer them
    return any(hmac.compare_digest("sha256=" + hmac.new(k.encode(), raw, hashlib.sha256).hexdigest(), header or "") for k in keys)


@router.get("/webhook")
async def verify(hub_mode: Optional[str] = Query(None, alias="hub.mode"), hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
                 hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token")):
    expected = verify_token()
    if hub_mode != "subscribe" or not expected or not hmac.compare_digest(hub_verify_token or "", expected):
        return Response(content="Verification failed", status_code=403)
    return PlainTextResponse(content=str(hub_challenge or ""), status_code=200)


@router.post("/webhook")
async def receive(request: Request):
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return Response(content="Too large", status_code=413)
    if not signed(raw, request.headers.get("x-hub-signature-256")):
        logger.warning("Instagram webhook refused: not signed with Nimmi's app secret")
        return Response(content="Invalid signature", status_code=403)
    try:
        body = json.loads(raw)
    except ValueError:
        return Response(content="Bad Request", status_code=400)
    payloads = body if isinstance(body, list) else [body]  # Meta's examples show both a list and a single object
    work, said = [], []
    async with async_session() as db:
        found: dict = {}
        for payload in payloads:
            if not isinstance(payload, dict) or payload.get("object") != "instagram":
                continue
            for entry in payload.get("entry") or []:
                if not isinstance(entry, dict):
                    continue
                ig_id = str(entry.get("id") or "")
                if ig_id not in found:
                    found[ig_id] = await accounts.by_ig_id(db, ig_id)
                if found[ig_id] is None:
                    continue  # an account no workspace has connected (or one that was disconnected)
                for event in entry.get("messaging") or []:
                    work.append((found[ig_id], event))
                for value in comments._value(entry):  # comments on its posts and reels (phase 6)
                    said.append((found[ig_id], value, entry.get("time")))
    kept = []
    try:
        for account, event in work:
            await inbound.handle(account, event)
        for account, value, sent in said:
            row_id = await comments.keep(account, value, sent)
            if row_id:
                kept.append(row_id)
    except Exception as e:  # Meta sends it again; what was already kept isn't kept twice
        logger.exception(f"Instagram webhook couldn't be kept: {e}")
        return Response(content="Try again", status_code=500)
    for row_id in kept:  # replied to after Meta hears "received"; the scheduler picks up anything a restart leaves
        fire_and_forget(comments.process(row_id))
    return {"status": "ok"}


@router.post("/deauthorize")
async def deauthorize(request: Request):
    """Someone removed Nimmi's app in Instagram: their sign-ins are forgotten."""
    data = accounts.read_signed_request(str((await request.form()).get("signed_request") or ""))
    if data is None or not data.get("user_id"):
        raise HTTPException(status_code=400, detail="Bad signed_request")
    await accounts.forget(str(data["user_id"]))
    return {"ok": True}


@router.post("/deletion")
async def deletion(request: Request, db: AsyncSession = Depends(get_db)):
    """Meta's data deletion request: the sign-ins Nimmi holds for them go now, and the answer says where to check (Meta's format)."""
    data = accounts.read_signed_request(str((await request.form()).get("signed_request") or ""))
    if data is None or not data.get("user_id"):
        raise HTTPException(status_code=400, detail="Bad signed_request")
    count = await accounts.forget(str(data["user_id"]))
    code = secrets.token_hex(8)
    db.add(NotificationLog(user_id=None, kind="instagram_deletion", ref_id=code, status="sent", error=f"{count} sign-ins deleted"))
    await db.commit()
    return JSONResponse({"url": f"{(os.getenv('PUBLIC_BACKEND_URL') or '').rstrip('/')}/api/instagram/deletion/{code}", "confirmation_code": code})


@router.get("/deletion/{code}")
async def deletion_status(code: str, db: AsyncSession = Depends(get_db)):
    found = (await db.execute(select(NotificationLog).where(NotificationLog.kind == "instagram_deletion", NotificationLog.ref_id == code[:20]))).scalars().first()
    if found is None:
        raise HTTPException(status_code=404, detail="No such request")
    return PlainTextResponse(f"Request {code}: Nimmi deleted the Instagram sign-in details it held for this person.")
