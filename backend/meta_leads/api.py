"""
Facebook and Instagram lead ads, connected directly (/api/meta, instagram_plan.md phase 3): connecting Facebook, the Pages and forms, where each form's leads go,
past leads; and Meta's own calls: the leadgen webhook, the app removed, a person's data deleted. Managers connect and route; Meta's calls are checked by the app
secret (a signature on the raw body, or a signed_request).
"""
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, get_owned_bot, rate_limit, require_manager
from backend.models import LeadIntake, MetaConnection, MetaForm, MetaPage, NotificationLog
from database import get_db
from meta_leads import core, graph
from notify.events import fire_and_forget

router = APIRouter(prefix="/api/meta", tags=["meta"])


def _iso(at: Optional[datetime]) -> Optional[str]:
    from voice.schedule import utc
    return utc(at).isoformat() if at else None


@router.get("")
async def overview(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """What's connected: sign-ins, Pages with their state and repair, each Page's forms with where their leads go, and what waits."""
    conns = (await db.execute(select(MetaConnection).where(MetaConnection.user_id == ctx.owner_id).order_by(MetaConnection.created_at))).scalars().all()
    pages = (await db.execute(select(MetaPage).where(MetaPage.user_id == ctx.owner_id).order_by(MetaPage.name))).scalars().all()
    forms = (await db.execute(select(MetaForm).where(MetaForm.user_id == ctx.owner_id).order_by(MetaForm.name))).scalars().all()
    waiting = await core.waiting(ctx.owner_id)
    ticks: dict[str, set] = {}  # the tick boxes each form's leads came with, for choosing which one says yes to WhatsApp
    for origin, consents in (await db.execute(select(LeadIntake.origin, LeadIntake.consents).where(LeadIntake.user_id == ctx.owner_id, LeadIntake.channel == "meta",
                                                                                             LeadIntake.consents.isnot(None)).order_by(LeadIntake.created_at.desc()).limit(500))).all():
        form_id = (origin or {}).get("form_id")
        if form_id:
            ticks.setdefault(form_id, set()).update(str(c.get("id")) for c in consents or [] if isinstance(c, dict) and c.get("id"))
    return {
        "available": graph.available(),
        "connections": [{"id": c.id, "name": c.name, "status": c.status, "error": c.error, "missing": [s for s in graph.SCOPES if s not in (c.scopes or [])],
                         "mine": c.person_id == ctx.user_id} for c in conns],
        "pages": [{"page_id": p.page_id, "name": p.name, "subscribed": bool(p.subscribed), "status": p.status, "error": p.error, "last_lead_at": _iso(p.last_lead_at),
                   "forms": [{"form_id": f.form_id, "name": f.name, "status": f.status, "bot_id": f.bot_id, "settings": {**core.SETTINGS, **(f.settings or {})},
                              "last_lead_at": _iso(f.last_lead_at), "checked_through": _iso(f.checked_through), "waiting": waiting.get(f.form_id, {}),
                              "ticks": sorted(ticks.get(f.form_id, set()))}
                             for f in forms if f.page_id == p.page_id]} for p in pages],
    }


@router.post("/connect")
async def connect(ctx: AuthContext = Depends(require_manager)):
    if not graph.available():
        raise HTTPException(status_code=409, detail="Connecting Facebook comes once Nimmi's Meta app is approved. Use the Zapier link meanwhile.")
    return {"url": core.start_url(ctx.owner_id, ctx.user_id)}


class FinishIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=2000)
    state: str = Field(..., min_length=1, max_length=2000)


@router.post("/connect/finish")
async def finish(data: FinishIn, ctx: AuthContext = Depends(require_manager)):
    """Facebook sent them back to Leads > Sources: only the person who started it, in the workspace they started it in, can finish it."""
    if core.read_state(data.state) != (ctx.owner_id, ctx.user_id):
        raise HTTPException(status_code=403, detail="This sign-in was started by someone else, or took too long. Connect again.")
    rate_limit(f"meta-finish:{ctx.user_id}", 20, 3600)
    try:
        return await core.finish(data.code, ctx.owner_id, ctx.user_id)
    except graph.GraphError as e:
        raise HTTPException(status_code=502, detail=str(e))


async def _owned_page(db: AsyncSession, ctx: AuthContext, page_id: str) -> MetaPage:
    page = (await db.execute(select(MetaPage).where(MetaPage.page_id == page_id[:40], MetaPage.user_id == ctx.owner_id))).scalars().first()
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


@router.post("/pages/{page_id}/subscribe")
async def subscribe(page_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """The Page's new leads come to Nimmi, and its forms are listed."""
    await _owned_page(db, ctx, page_id)
    try:
        await core.subscribe(ctx.owner_id, page_id[:40])
    except graph.GraphError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True}


@router.post("/pages/{page_id}/forms")
async def refresh_forms(page_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await _owned_page(db, ctx, page_id)
    try:
        return {"forms": await core.refresh_forms(ctx.owner_id, page_id[:40])}
    except graph.GraphError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.delete("/pages/{page_id}")
async def forget_page(page_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Nimmi stops getting the Page's leads. Leads already in stay."""
    await _owned_page(db, ctx, page_id)
    await core.unsubscribe(ctx.owner_id, page_id[:40])
    return {"ok": True}


class FormIn(BaseModel):
    bot_id: Optional[str] = Field(None, max_length=36)
    email: Optional[bool] = None
    call: Optional[bool] = None
    whatsapp_tick: Optional[str] = Field(None, max_length=80)  # "" for none


@router.put("/forms/{form_id}")
async def route(form_id: str, data: FormIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Where a form's leads go, and whether each gets the email and the assistant's call (both off until turned on)."""
    form = (await db.execute(select(MetaForm).where(MetaForm.form_id == form_id[:40], MetaForm.user_id == ctx.owner_id))).scalars().first()
    if form is None:
        raise HTTPException(status_code=404, detail="Form not found")
    bot_id = form.bot_id if data.bot_id is None else (data.bot_id or None)
    if bot_id:
        bot_id = (await get_owned_bot(bot_id, ctx, db)).bot_id
        await plans.require_feature(db, bot_id, "email_alerts")  # lead ads come with Growth, as leads from other places do
    await core.route(ctx.owner_id, form.form_id, bot_id, {k: v for k, v in (("email", data.email), ("call", data.call), ("whatsapp_tick", data.whatsapp_tick)) if v is not None})
    if bot_id:
        fire_and_forget(core.tick())
    return {"ok": True}


class ImportIn(BaseModel):
    days: int = Field(core.IMPORT_DAYS, ge=1, le=core.IMPORT_DAYS)


@router.post("/forms/{form_id}/import")
async def import_past(form_id: str, data: ImportIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """A form's leads from before it was connected: they come in over the next minutes, and nobody is contacted."""
    form = (await db.execute(select(MetaForm).where(MetaForm.form_id == form_id[:40], MetaForm.user_id == ctx.owner_id))).scalars().first()
    if form is None or not form.bot_id:
        raise HTTPException(status_code=404 if form is None else 409, detail="Form not found" if form is None else "Choose an assistant for this form first")
    rate_limit(f"meta-import:{ctx.owner_id}", 5, 3600)
    fire_and_forget(core.import_past(ctx.owner_id, form.form_id, data.days))
    return {"started": True}


@router.delete("/connections/{connection_id}")
async def disconnect(connection_id: str, ctx: AuthContext = Depends(require_manager)):
    try:
        await core.disconnect(ctx.owner_id, connection_id[:36])
    except LookupError:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


# ─── Meta's calls ────────────────────────────────────────────────
@router.get("/webhook")
async def verify(mode: Optional[str] = Query(None, alias="hub.mode"), token: Optional[str] = Query(None, alias="hub.verify_token"),
                 challenge: Optional[str] = Query(None, alias="hub.challenge")):
    import os
    expected = os.getenv("META_LEADS_VERIFY_TOKEN", "")
    if mode == "subscribe" and expected and secrets.compare_digest(token or "", expected):
        return PlainTextResponse(challenge or "")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive(request: Request):
    """Meta's new leads: signed with the app secret, kept before the 200 (Meta retries anything else for 36 hours), then fetched by one process."""
    raw = await request.body()
    if not core.signed(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=403, detail="Bad signature")
    import json
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Not JSON")
    for event_id in await core.keep(payload if isinstance(payload, dict) else {}):
        fire_and_forget(core.process(event_id))
    return {"status": "received"}


@router.post("/deauthorize")
async def deauthorize(request: Request):
    """Someone removed Nimmi's app in Facebook: their sign-in and Pages are forgotten."""
    data = core.read_signed_request(str((await request.form()).get("signed_request") or ""))
    if data is None or not data.get("user_id"):
        raise HTTPException(status_code=400, detail="Bad signed_request")
    await core.forget_person(str(data["user_id"]))
    return {"ok": True}


@router.post("/deletion")
async def deletion(request: Request, db: AsyncSession = Depends(get_db)):
    """Meta's data deletion request: what Nimmi holds from their Facebook sign-in is deleted now, and the answer is where to check (Meta's format)."""
    data = core.read_signed_request(str((await request.form()).get("signed_request") or ""))
    if data is None or not data.get("user_id"):
        raise HTTPException(status_code=400, detail="Bad signed_request")
    count = await core.forget_person(str(data["user_id"]))
    code = secrets.token_hex(8)
    db.add(NotificationLog(user_id=None, kind="meta_deletion", ref_id=code, status="sent", error=f"{count} sign-ins deleted"))
    await db.commit()
    import os
    return JSONResponse({"url": f"{(os.getenv('PUBLIC_BACKEND_URL') or '').rstrip('/')}/api/meta/deletion/{code}", "confirmation_code": code})


@router.get("/deletion/{code}")
async def deletion_status(code: str, db: AsyncSession = Depends(get_db)):
    found = (await db.execute(select(NotificationLog).where(NotificationLog.kind == "meta_deletion", NotificationLog.ref_id == code[:20]))).scalars().first()
    if found is None:
        raise HTTPException(status_code=404, detail="No such request")
    return PlainTextResponse(f"Request {code}: Nimmi deleted the Facebook sign-in and Page details it held for this person.")
