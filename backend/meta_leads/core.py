"""
Meta Lead Ads, connected directly (instagram_plan.md, phase 3). A business connects Facebook, chooses its Pages and gives each lead form an assistant. Meta's
webhook only names a new lead: it's kept first (MetaEvent, ids only) and Meta hears "received" at once; then one process fetches the answers with the Page's
own token and hands them to mail/intake.py like any other lead: a contact, the team told, Leads. Every 15 minutes a catch-up reads each form's leads since
the last one it saw, with an overlap, so a webhook Meta never delivered isn't a lost lead. A form's automatic email and call are off until turned on.

Meta retries a webhook for 36 hours unless it hears 200, and may send a lead twice or in a batch of up to 1,000: each lead id is kept once. A Page belongs to one
workspace. A sign-in that ends (a password change, the app removed) or a missing permission shows on the Page with its repair, and its leads wait: nothing is
lost while it's fixed.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from auth import decode_scoped_token, issue_scoped_token
from backend.models import Bot, LeadIntake, MetaConnection, MetaEvent, MetaForm, MetaPage
from database import async_session
from leads import origin as lead_origin
from meta_leads import graph
from notify import email

logger = logging.getLogger(__name__)

STATE_SECONDS = 600
ESSENTIAL = ("leads_retrieval", "pages_show_list", "pages_manage_metadata")  # without these no lead can be read
OVERLAP = timedelta(minutes=30)          # the catch-up reads back this far past what it last saw
CATCH_UP_EVERY = timedelta(minutes=15)
CATCH_UP_PAGES = 10                       # pages of 100 a form, a pass; the rest next pass
STUCK = timedelta(minutes=3)
TRIES = 6
BACKOFF = (1, 5, 15, 60, 180, 720)        # minutes after each failed try
REPAIR_WAIT = timedelta(minutes=15)       # a Page that needs its sign-in or a permission back: its leads try again after this
PASS_EVERY = timedelta(seconds=30)
IMPORT_DAYS = 90                          # Meta keeps lead answers for 90 days
SETTINGS = {"email": False, "call": False, "whatsapp_tick": None}  # whatsapp_tick: the key of the form's tick box that says yes to WhatsApp (phase 4)
PERSONAL = ("full_name", "first_name", "last_name", "email", "work_email", "phone_number", "work_phone_number", "phone")
_last_pass: Optional[datetime] = None
_last_catch_up: Optional[datetime] = None


def now() -> datetime:
    return datetime.utcnow()


def _utc(at: Optional[datetime]) -> Optional[datetime]:
    return at.replace(tzinfo=timezone.utc) if at is not None and at.tzinfo is None else at


# ─── connecting ──────────────────────────────────────────────────
def redirect_uri() -> str:
    """Back to Leads > Sources, which finishes with the signed-in person's token: a link someone else started can't attach your Pages to their workspace."""
    return f"{email.dashboard_url()}/dashboard/leads/sources"


def start_url(owner_id: str, person_id: str) -> str:
    """Facebook Login for Business, with the configuration that asks for the lead ads permissions (META_LOGIN_CONFIG_ID)."""
    app_id, _ = graph.app()
    state = issue_scoped_token(f"{owner_id}|{person_id}", "meta_connect", STATE_SECONDS)
    query = {"client_id": app_id, "redirect_uri": redirect_uri(), "state": state, "config_id": os.getenv("META_LOGIN_CONFIG_ID", ""), "response_type": "code",
             "override_default_response_type": "true"}
    return f"{graph.dialog()}/{graph.VERSION}/dialog/oauth?{urlencode(query)}"


def read_state(state: str) -> Optional[tuple[str, str]]:
    parts = (decode_scoped_token(state or "", "meta_connect") or "").split("|")
    return (parts[0], parts[1]) if len(parts) == 2 else None


async def finish(code: str, owner_id: str, person_id: str) -> dict:
    """They came back from Facebook: a long-lived token, what they granted, their Pages with each one's own token. A Page another workspace has stays theirs."""
    token = await graph.user_token(code, redirect_uri())
    who = await graph.me(token)
    scopes = await graph.granted(token)
    found = await graph.pages(token)
    missing = [s for s in graph.SCOPES if s not in scopes]
    taken = []
    async with async_session() as db:
        conn = (await db.execute(select(MetaConnection).where(MetaConnection.user_id == owner_id, MetaConnection.meta_user == str(who["id"])))).scalars().first()
        if conn is None:
            conn = MetaConnection(user_id=owner_id, meta_user=str(who["id"]))
            db.add(conn)
        conn.person_id, conn.name, conn.token, conn.scopes, conn.updated_at = person_id, (who.get("name") or "")[:120], token, scopes, now()
        conn.status, conn.error = ("missing_permission", f"Not given: {', '.join(s for s in ESSENTIAL if s not in scopes)}") if any(s not in scopes for s in ESSENTIAL) else ("active", None)
        await db.flush()
        for p in found:
            row = (await db.execute(select(MetaPage).where(MetaPage.page_id == p["id"]))).scalars().first()
            if row is not None and row.user_id != owner_id:
                taken.append(p["name"] or p["id"])
                continue
            if row is None:
                row = MetaPage(user_id=owner_id, page_id=p["id"], subscribed=False)
                db.add(row)
            row.connection_id, row.name, row.token, row.tasks = conn.id, p["name"][:200], p["token"], p["tasks"]
            row.status, row.error = ("active", None) if "ADVERTISE" in p["tasks"] or not p["tasks"] else ("permission", "Your Page role can't advertise: ask an admin of the Page for one that can")
        await db.commit()
    await _retry_waiting(owner_id)  # leads that waited for this sign-in
    return {"pages": len(found) - len(taken), "taken": taken, "missing": missing}


async def _page(db, owner_id: str, page_id: str) -> Optional[MetaPage]:
    return (await db.execute(select(MetaPage).where(MetaPage.page_id == page_id, MetaPage.user_id == owner_id))).scalars().first()


async def _fail(page_id: str, e: graph.GraphError) -> None:
    """What went wrong shows on the Page, with its repair (graph.MESSAGES)."""
    if e.kind in ("token", "permission", "gone"):
        async with async_session() as db:
            await db.execute(update(MetaPage).where(MetaPage.page_id == page_id).values(status=e.kind, error=str(e)[:300]).execution_options(synchronize_session=False))
            await db.commit()


async def subscribe(owner_id: str, page_id: str) -> None:
    """The Page's new leads come to Nimmi from now, and its forms are listed. Raises GraphError."""
    async with async_session() as db:
        page = await _page(db, owner_id, page_id)
        token = page.token if page else None
    if page is None:
        raise LookupError(page_id)
    try:
        await graph.subscribe(page_id, token)
    except graph.GraphError as e:
        await _fail(page_id, e)
        raise
    async with async_session() as db:
        await db.execute(update(MetaPage).where(MetaPage.page_id == page_id).values(subscribed=True, status="active", error=None).execution_options(synchronize_session=False))
        await db.commit()
    await refresh_forms(owner_id, page_id)


async def unsubscribe(owner_id: str, page_id: str) -> None:
    """Nimmi stops getting the Page's leads, and forgets it and its forms. Leads already in stay."""
    async with async_session() as db:
        page = await _page(db, owner_id, page_id)
        if page is None:
            raise LookupError(page_id)
        token = page.token
    try:
        await graph.unsubscribe(page_id, token)
    except graph.GraphError as e:
        logger.warning(f"Unsubscribing Page {page_id} at Meta failed: {e}")  # forgotten here all the same
    async with async_session() as db:
        await db.delete(await _page(db, owner_id, page_id))
        await db.commit()


async def refresh_forms(owner_id: str, page_id: str) -> int:
    """The Page's lead forms as Meta has them. A new form starts from now: older leads come in only when asked for (import)."""
    async with async_session() as db:
        page = await _page(db, owner_id, page_id)
        if page is None:
            raise LookupError(page_id)
        token = page.token
    try:
        found = await graph.forms(page_id, token)
    except graph.GraphError as e:
        await _fail(page_id, e)
        raise
    async with async_session() as db:
        known = {f.form_id: f for f in (await db.execute(select(MetaForm).where(MetaForm.page_id == page_id))).scalars().all()}
        for f in found:
            row = known.get(f["id"])
            if row is None:
                db.add(MetaForm(user_id=owner_id, page_id=page_id, form_id=f["id"], name=f["name"][:200], status=f["status"][:20], settings=dict(SETTINGS), checked_through=now()))
            else:
                row.name, row.status = f["name"][:200], f["status"][:20]
        await db.commit()
    return len(found)


async def route(owner_id: str, form_id: str, bot_id: Optional[str], settings: dict) -> None:
    """Where a form's leads go, and whether each gets the email and the call. Leads that waited for an assistant come in now."""
    async with async_session() as db:
        form = (await db.execute(select(MetaForm).where(MetaForm.form_id == form_id, MetaForm.user_id == owner_id))).scalars().first()
        if form is None:
            raise LookupError(form_id)
        form.bot_id = bot_id
        clean = {k: (str(v or "").strip()[:80] or None) if k == "whatsapp_tick" else bool(v) for k, v in settings.items() if k in SETTINGS}
        form.settings = {**SETTINGS, **(form.settings or {}), **clean}
        if bot_id:
            await db.execute(update(MetaEvent).where(MetaEvent.form_id == form_id, MetaEvent.user_id == owner_id, MetaEvent.status == "waiting")
                             .values(status="new", claimed_at=None, retry_at=None).execution_options(synchronize_session=False))
        await db.commit()


async def disconnect(owner_id: str, connection_id: str) -> None:
    """Their sign-in, its Pages and forms are forgotten (the Pages stop sending leads). Leads already in stay."""
    async with async_session() as db:
        conn = (await db.execute(select(MetaConnection).where(MetaConnection.id == connection_id, MetaConnection.user_id == owner_id))).scalars().first()
        if conn is None:
            raise LookupError(connection_id)
        pages = (await db.execute(select(MetaPage).where(MetaPage.connection_id == conn.id))).scalars().all()
        held = [(p.page_id, p.token) for p in pages if p.subscribed]
    for page_id, token in held:
        try:
            await graph.unsubscribe(page_id, token)
        except graph.GraphError as e:
            logger.warning(f"Unsubscribing Page {page_id} at Meta failed: {e}")
    async with async_session() as db:
        conn = await db.get(MetaConnection, connection_id)
        if conn is not None:
            await db.delete(conn)
        await db.commit()


# ─── Meta's webhook ──────────────────────────────────────────────
def signed(raw: bytes, header: Optional[str]) -> bool:
    """X-Hub-Signature-256: sha256= and the SHA256 HMAC of the raw body with the app secret."""
    _, secret = graph.app()
    if not secret or not (header or "").startswith("sha256="):
        return False
    return hmac.compare_digest(hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(), header[7:])


def _id(value) -> str:
    """Meta's ids, numbers in some of its examples and strings in others: kept as strings of digits, or nothing."""
    text = str(value if value is not None else "").strip()
    return text if text.isdigit() and len(text) <= 40 else ""


async def keep(payload: dict, via: str = "webhook") -> list[str]:
    """The new leads a webhook names, each kept once, before Meta hears anything. Pages nobody connected are left out. The events' ids, to handle."""
    if payload.get("object") != "page":
        return []
    named = [(c.get("value") or {}) for e in payload.get("entry") or [] if isinstance(e, dict) for c in e.get("changes") or []
             if isinstance(c, dict) and c.get("field") == "leadgen"]
    leads = [(_id(v.get("leadgen_id")), _id(v.get("page_id")), _id(v.get("form_id"))) for v in named if isinstance(v, dict)]
    return await _keep([(lid, pid, fid) for lid, pid, fid in leads if lid and pid], via)


async def _keep(leads: list[tuple[str, str, str]], via: str) -> list[str]:
    kept: list[str] = []
    if not leads:
        return kept
    async with async_session() as db:
        owners = dict((await db.execute(select(MetaPage.page_id, MetaPage.user_id).where(MetaPage.page_id.in_({p for _, p, _ in leads})))).all())
        seen = set((await db.execute(select(MetaEvent.leadgen_id).where(MetaEvent.leadgen_id.in_({lid for lid, _, _ in leads})))).scalars().all())
    for leadgen_id, page_id, form_id in leads:
        if page_id not in owners or leadgen_id in seen:
            continue
        seen.add(leadgen_id)
        async with async_session() as db:
            row = MetaEvent(user_id=owners[page_id], leadgen_id=leadgen_id, page_id=page_id, form_id=form_id or None, via=via, status="new")
            db.add(row)
            try:
                await db.commit()
            except IntegrityError:  # the same lead, a moment ago, on another process
                continue
            kept.append(row.id)
    return kept


# ─── fetching a lead ─────────────────────────────────────────────
def from_lead(data: dict, form_name: Optional[str]) -> tuple[dict, Optional[dict], list]:
    """Meta's answers as a lead (mail/intake.py's shape), where it came from, and the tick boxes as they were answered. Every answer stays: a
    multiple choice is joined, an unknown question kept as "Question: answer"."""
    from mail import intake
    answers = {}
    for f in data.get("field_data") or []:
        if isinstance(f, dict) and f.get("name"):
            values = f.get("values") if isinstance(f.get("values"), list) else [f.get("values")]
            answers[str(f["name"]).strip()[:80]] = ", ".join(str(v).strip() for v in values if v not in (None, ""))[:500]
    platform = str(data.get("platform") or "").lower()
    found = intake.form_lead({**answers, "platform": platform}, ads=True)
    known = {n for names in intake.FORM_NAMES.values() for n in names} | set(PERSONAL)
    others = [f"{k.replace('_', ' ').strip().capitalize()}: {v}" for k, v in answers.items() if v and k.lower() not in known]
    found["wants"] = "; ".join(x for x in (found["wants"], *others) if x)[:400]
    found.pop("consent", None)  # Meta's own tick boxes are below, with their keys: what each one said is on the form in Meta
    came = lead_origin.clean({"channel": "meta_ads", "campaign_id": data.get("campaign_id"), "campaign_name": data.get("campaign_name"), "adset_id": data.get("adset_id"),
                              "adset_name": data.get("adset_name"), "ad_id": data.get("ad_id"), "ad_name": data.get("ad_name"), "form_id": data.get("form_id"),
                              "form_name": form_name, "platform": platform or None})
    ticks = [{"id": str(c.get("checkbox_key") or "")[:80], "agreed": str(c.get("is_checked")).strip().lower() in ("1", "true")}
             for c in data.get("custom_disclaimer_responses") or [] if isinstance(c, dict)]
    return found, came, ticks


async def process(event_id: str, at: Optional[datetime] = None) -> None:
    """One lead Meta named: claimed by one process, fetched with the Page's token, then handled like any other lead. A failure waits and tries again."""
    at = at or now()
    async with async_session() as db:
        claimed = await db.execute(update(MetaEvent).where(
            MetaEvent.id == event_id, MetaEvent.status.in_(("new", "working")), or_(MetaEvent.claimed_at.is_(None), MetaEvent.claimed_at < at - STUCK),
            or_(MetaEvent.retry_at.is_(None), MetaEvent.retry_at <= at))
            .values(status="working", claimed_at=at, attempts=MetaEvent.attempts + 1).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return
        event = await db.get(MetaEvent, event_id)
        page = (await db.execute(select(MetaPage).where(MetaPage.page_id == event.page_id))).scalars().first()
        form = (await db.execute(select(MetaForm).where(MetaForm.page_id == event.page_id, MetaForm.form_id == event.form_id))).scalars().first() if event.form_id else None
        leadgen_id, attempts, via, owner_id, page_id, form_id = event.leadgen_id, event.attempts or 1, event.via, event.user_id, event.page_id, event.form_id
        token = page.token if page else None
        bot = await db.get(Bot, form.bot_id) if form is not None and form.bot_id else None
        form_name, settings = (form.name, {**SETTINGS, **(form.settings or {})}) if form is not None else (None, dict(SETTINGS))
        if page is None or page.user_id != owner_id:
            event.status, event.error, event.claimed_at = "failed", "The Page isn't connected any more", None
            await db.commit()
            return
        if bot is None or bot.user_id != owner_id:
            event.status, event.error, event.claimed_at = "waiting", "This form has no assistant yet: choose one in Leads > Sources", None
            await db.commit()
            return
    try:
        data = await graph.lead(leadgen_id, token)
    except graph.GraphError as e:
        await _fail(page_id, e)
        async with async_session() as db:
            row = await db.get(MetaEvent, event_id)
            if e.kind in ("token", "permission"):  # waits for the repair, however long it takes
                row.status, row.retry_at = "new", at + REPAIR_WAIT
            elif e.kind == "gone" or attempts >= TRIES:
                row.status = "failed"
            else:
                row.status, row.retry_at = "new", at + timedelta(minutes=BACKOFF[min(attempts, len(BACKOFF)) - 1])
            row.error, row.claimed_at = str(e)[:300], None
            await db.commit()
        return
    found, came, ticks = from_lead(data, form_name)
    key = settings.get("whatsapp_tick")
    if key and any(t["id"] == key and t["agreed"] for t in ticks):  # their own yes to WhatsApp, on the tick box the manager named
        found["whatsapp_ok"] = f'Ticked "{key}" on the Facebook form "{form_name or form_id}"'
    if via == "import":
        await _keep_old(bot, found, came)
        async with async_session() as db:
            await db.execute(update(MetaEvent).where(MetaEvent.id == event_id).values(status="done", claimed_at=None, error=None).execution_options(synchronize_session=False))
            await db.commit()
        return
    async with async_session() as db:
        intake_row = LeadIntake(user_id=owner_id, bot_id=bot.bot_id, channel="meta", ref=f"meta:{leadgen_id}", source=found["portal"][:40], status="new",
                                raw=json.dumps(data.get("field_data") or [], ensure_ascii=False)[:8000], found=found, origin=came, consents=ticks or None)
        db.add(intake_row)
        try:
            await db.flush()
        except IntegrityError:  # handed over before, by a process that stopped before marking this done
            await db.rollback()
            intake_row = (await db.execute(select(LeadIntake).where(LeadIntake.bot_id == bot.bot_id, LeadIntake.ref == f"meta:{leadgen_id}"))).scalars().first()
        event = await db.get(MetaEvent, event_id)
        event.status, event.intake_id, event.claimed_at, event.error = "done", intake_row.id if intake_row else None, None, None
        stamp = now()
        await db.execute(update(MetaPage).where(MetaPage.page_id == page_id).values(last_lead_at=stamp, status="active", error=None).execution_options(synchronize_session=False))
        await db.execute(update(MetaForm).where(MetaForm.page_id == page_id, MetaForm.form_id == form_id).values(last_lead_at=stamp).execution_options(synchronize_session=False))
        await db.commit()
        intake_id = intake_row.id if intake_row else None
    if intake_id:
        from mail import intake
        await intake.process(intake_id, email=settings["email"], call=settings["call"])


async def _keep_old(bot: Bot, found: dict, came: Optional[dict]) -> None:
    """A lead from before the form was connected: in All leads with its answers, and nobody contacted (an old enquiry gives no days to call)."""
    from leads import core as leads
    from mail import intake
    from phone import to_e164
    e164 = to_e164(found.get("phone") or "")
    address = (found.get("email") or "").strip()
    if not (e164 or address):
        return
    async with async_session() as db:
        contact = await intake._contact(db, bot, e164, address, found)
        fresh = contact.id is None
        await db.flush()
        if fresh:
            contact.quality, contact.origin = "old", came
            db.add(leads.event(contact, "imported", f"From {found.get('portal') or 'lead ads'}, before it was connected"))
        await db.commit()


async def _retry_waiting(owner_id: str) -> None:
    """After a repair: leads that waited for it try now."""
    async with async_session() as db:
        await db.execute(update(MetaEvent).where(MetaEvent.user_id == owner_id, MetaEvent.status == "new").values(retry_at=None).execution_options(synchronize_session=False))
        await db.commit()


# ─── catching up ─────────────────────────────────────────────────
async def catch_up_form(form_id: str, page_id: str, since: Optional[datetime] = None, via: str = "catch_up") -> list[str]:
    """A form's leads since what it last saw (less an overlap), a page at a time. What's kept already is left alone; what's new is kept like a webhook's.
    The form moves on only past what was really read, so a pass cut short goes on next time."""
    async with async_session() as db:
        form = (await db.execute(select(MetaForm).where(MetaForm.form_id == form_id, MetaForm.page_id == page_id))).scalars().first()
        page = (await db.execute(select(MetaPage).where(MetaPage.page_id == page_id))).scalars().first()
        if form is None or page is None or not page.subscribed or page.status != "active":
            return []
        started = datetime.now(timezone.utc)
        start = since or (_utc(form.checked_through) or started) - OVERLAP
        token, row_id = page.token, form.id
    kept, after, complete = [], None, False
    try:
        for _ in range(CATCH_UP_PAGES):
            rows, after = await graph.leads_since(form_id, token, int(_utc(start).timestamp()), after)
            kept += await _keep([(_id(r.get("id")), page_id, form_id) for r in rows if _id(r.get("id"))], via)
            if not after:
                complete = True
                break
    except graph.GraphError as e:
        await _fail(page_id, e)
        return kept
    if complete and via == "catch_up":  # everything up to when it began is in; the overlap covers leads Meta shows a few minutes late
        async with async_session() as db:
            await db.execute(update(MetaForm).where(MetaForm.id == row_id).values(checked_through=started.replace(tzinfo=None)).execution_options(synchronize_session=False))
            await db.commit()
    return kept


async def import_past(owner_id: str, form_id: str, days: int = IMPORT_DAYS) -> int:
    """A form's leads from before it was connected (Meta keeps the answers 90 days): kept, and nobody contacted. How many came in."""
    async with async_session() as db:
        form = (await db.execute(select(MetaForm).where(MetaForm.form_id == form_id, MetaForm.user_id == owner_id))).scalars().first()
        if form is None or not form.bot_id:
            raise LookupError(form_id)
        page_id = form.page_id
    kept = await catch_up_form(form_id, page_id, since=datetime.now(timezone.utc) - timedelta(days=min(max(days, 1), IMPORT_DAYS)), via="import")
    for event_id in kept:
        await process(event_id)
    return len(kept)


# ─── the scheduler ───────────────────────────────────────────────
async def tick(at: Optional[datetime] = None) -> None:
    """Leads kept but not handled (a process went down, Meta was busy, a repair was waited for), and every 15 minutes the catch-up. Each one is claimed, so
    the four processes share them."""
    global _last_pass, _last_catch_up
    at = at or now()
    if _last_pass and at - _last_pass < PASS_EVERY:
        return
    _last_pass = at
    async with async_session() as db:
        due = (await db.execute(select(MetaEvent.id).where(
            MetaEvent.status.in_(("new", "working")), MetaEvent.created_at < at - timedelta(seconds=20), or_(MetaEvent.retry_at.is_(None), MetaEvent.retry_at <= at),
            or_(MetaEvent.claimed_at.is_(None), MetaEvent.claimed_at < at - STUCK)).order_by(MetaEvent.created_at).limit(25))).scalars().all()
        forms = (await db.execute(select(MetaForm.form_id, MetaForm.page_id).join(MetaPage, MetaPage.page_id == MetaForm.page_id).where(
            MetaForm.bot_id.isnot(None), MetaPage.subscribed.is_(True), MetaPage.status == "active"))).all() if not _last_catch_up or at - _last_catch_up >= CATCH_UP_EVERY else None
    for event_id in due:
        await process(event_id, at)
    if forms is not None:
        _last_catch_up = at
        for form_id, page_id in forms:
            for event_id in await catch_up_form(form_id, page_id):
                await process(event_id, at)


# ─── Meta's callbacks about people ───────────────────────────────
def read_signed_request(value: str) -> Optional[dict]:
    """Meta's signed_request: the payload, if the app secret signed it."""
    _, secret = graph.app()
    try:
        signature, payload = (value or "").split(".", 1)
        sent = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, TypeError):
        return None
    if not secret or not hmac.compare_digest(sent, expected) or str(data.get("algorithm") or "").upper() != "HMAC-SHA256":
        return None
    return data


async def forget_person(meta_user: str) -> int:
    """Someone removed Nimmi's app, or asked Meta to delete their data: their sign-ins, and the Pages and forms that came with them, go. How many."""
    async with async_session() as db:
        rows = (await db.execute(select(MetaConnection).where(MetaConnection.meta_user == str(meta_user)))).scalars().all()
        for row in rows:
            await db.delete(row)
        await db.commit()
    return len(rows)


async def waiting(owner_id: str) -> dict:
    """What waits: leads for forms with no assistant, and leads that couldn't be fetched yet, by form."""
    from sqlalchemy import func
    async with async_session() as db:
        rows = (await db.execute(select(MetaEvent.form_id, MetaEvent.status, func.count()).where(MetaEvent.user_id == owner_id, MetaEvent.status.in_(("waiting", "new", "failed")))
                                 .group_by(MetaEvent.form_id, MetaEvent.status))).all()
    out: dict = {}
    for form_id, status, count in rows:
        out.setdefault(form_id or "", {})[status] = count
    return out

