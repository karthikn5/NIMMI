"""
Email > Bulk email (/api/email/bulk, /api/email/segments, /api/email/broadcasts, /api/email/contacts/import, /api/email/consent): groups, drafts, a test to yourself, sending,
reports, and who agreed. The engine is mail/broadcasts.py.
"""
import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, rate_limit, require_manager
from backend.models import Bot, Contact, Consent, EmailBroadcast, EmailSegment, User
from database import get_db
from mail import address as mail_address, broadcasts, compose, consent, journeys, render, senders, setup, suppress
from notify import automations, email
from phone import to_e164

router = APIRouter(prefix="/api/email", tags=["email"])

IMPORT_ROWS = 5000
IMPORT_BYTES = 3_000_000
NAME_HEADERS = ("name", "full name", "fullname", "customer name", "contact name")
EMAIL_HEADERS = ("email", "e-mail", "email address", "mail", "email id")
PHONE_HEADERS = ("phone", "mobile", "number", "phone number", "mobile number", "contact number", "whatsapp")
TAG_HEADERS = ("tags", "tag", "labels")


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


async def _own_bot(bot_id: str, ctx: AuthContext, db: AsyncSession) -> Bot:
    bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id, Bot.user_id == ctx.owner_id))).scalars().first()
    if bot is None:
        raise HTTPException(status_code=404, detail="Assistant not found")
    return bot


async def _own(broadcast_id: str, ctx: AuthContext, db: AsyncSession) -> EmailBroadcast:
    b = (await db.execute(select(EmailBroadcast).where(EmailBroadcast.id == broadcast_id, EmailBroadcast.user_id == ctx.owner_id))).scalars().first()
    if b is None:
        raise HTTPException(status_code=404, detail="Bulk email not found")
    return b


def _segment_json(s: EmailSegment) -> dict:
    return {"id": s.id, "name": s.name, "rules": s.rules or {}}


def _broadcast_json(b: EmailBroadcast) -> dict:
    return {"id": b.id, "bot_id": b.bot_id, "status": b.status or "sent", "subject": b.subject, "subject_b": b.subject_b, "body": b.body, "rules": b.rules or {}, "event": b.event or None,
            "recipients": b.recipients or 0, "winner": b.winner, "send_at": _iso(b.send_at), "usual_hour": bool(b.usual_hour), "per_minute": b.per_minute or broadcasts.PACE,
            "test_ends_at": _iso(b.test_ends_at), "started_at": _iso(b.started_at), "finished_at": _iso(b.finished_at), "paused_why": b.paused_why, "created_at": _iso(b.created_at)}


# ─── the page ────────────────────────────────────────────────────
@router.get("/bulk/{bot_id}")
async def bulk_page(bot_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    from voice import schedule
    bot = await _own_bot(bot_id, ctx, db)
    sender = await senders.sender_for(db, ctx.owner_id, bot.bot_id)
    segments = (await db.execute(select(EmailSegment).where(EmailSegment.bot_id == bot.bot_id).order_by(EmailSegment.created_at))).scalars().all()
    sends = (await db.execute(select(EmailBroadcast).where(EmailBroadcast.bot_id == bot.bot_id).order_by(EmailBroadcast.created_at.desc()).limit(50))).scalars().all()
    earlier = (await db.execute(select(EmailBroadcast).where(EmailBroadcast.user_id == ctx.owner_id, EmailBroadcast.bot_id.is_(None)).order_by(EmailBroadcast.created_at.desc()).limit(50))).scalars().all()
    tags = (await db.execute(select(Contact.tags).where(Contact.bot_id == bot.bot_id, Contact.tags.isnot(None)).limit(5000))).scalars().all()
    return {"broadcasts": [{**_broadcast_json(b), **await broadcasts.report(db, b)} for b in [*sends, *earlier]], "segments": [_segment_json(s) for s in segments],
            "agreed": len(await consent.agreed(db, bot.bot_id)), "with_email": (await db.execute(select(func.count()).select_from(Contact).where(Contact.bot_id == bot.bot_id, Contact.email.isnot(None)))).scalar_one(),
            "ask_in_chat": (await setup.settings_for(db, bot.bot_id))["consent"], "sender": {"name": sender.name, "address": broadcasts.bulk_address(sender), "domain": sender.domain, "reply_to": sender.reply_to},
            "room_today": await broadcasts.room_today(db, ctx.owner_id, sender), "max_recipients": broadcasts.MAX_RECIPIENTS, "paces": broadcasts.PACES, "test_min": broadcasts.TEST_MIN,
            "tags": sorted({t for row in tags for t in (row or [])})[:100], "sources": broadcasts.SOURCES, "statuses": schedule.LEAD_LABELS, "stages": journeys.STAGES,
            "spam_rate": await broadcasts.complaint_rate(db, ctx.owner_id)}


class CountIn(BaseModel):
    bot_id: str = Field(..., max_length=36)
    rules: Optional[dict] = None


@router.post("/bulk/count")
async def count_people(data: CountIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Who it would reach, and who it leaves out and why. Sends nothing."""
    bot = await _own_bot(data.bot_id, ctx, db)
    people, left = await broadcasts.people(db, ctx.owner_id, bot.bot_id, broadcasts.clean_rules(data.rules))
    return {"count": len(people), "left_out": left, "sample": [{"name": p["name"], "email": p["email"]} for p in people[:8]]}


class SegmentIn(BaseModel):
    bot_id: str = Field(..., max_length=36)
    name: str = Field(..., min_length=1, max_length=120)
    rules: dict


@router.post("/segments")
async def save_segment(data: SegmentIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await _own_bot(data.bot_id, ctx, db)
    segment = EmailSegment(user_id=ctx.owner_id, bot_id=bot.bot_id, name=data.name.strip(), rules=broadcasts.clean_rules(data.rules))
    db.add(segment)
    await db.commit()
    return _segment_json(segment)


@router.delete("/segments/{segment_id}")
async def delete_segment(segment_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    segment = (await db.execute(select(EmailSegment).where(EmailSegment.id == segment_id, EmailSegment.user_id == ctx.owner_id))).scalars().first()
    if segment is None:
        raise HTTPException(status_code=404, detail="Group not found")
    await db.delete(segment)
    await db.commit()
    return {"status": "deleted"}


# ─── a bulk email ────────────────────────────────────────────────
class BroadcastIn(BaseModel):
    subject: str = Field("", max_length=200)
    subject_b: Optional[str] = Field(None, max_length=200)
    body: str = Field("", max_length=10000)
    rules: Optional[dict] = None
    event: Optional[dict] = None
    per_minute: Optional[int] = None


def _apply(b: EmailBroadcast, data: BroadcastIn) -> None:
    event = data.event if isinstance(data.event, dict) and str(data.event.get("title") or "").strip() else None
    if event:
        try:
            at = datetime.fromisoformat(str(event.get("at") or "").replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Say when the event is")
        event = {"title": str(event["title"]).strip()[:200], "at": at.astimezone(timezone.utc).isoformat(), "where": str(event.get("where") or "").strip()[:300]}
    if data.per_minute is not None and data.per_minute not in broadcasts.PACES:
        raise HTTPException(status_code=400, detail="Choose how fast it goes")
    b.subject, b.body, b.subject_b = data.subject.strip(), data.body.strip(), (data.subject_b or "").strip() or None
    b.rules, b.event, b.per_minute = broadcasts.clean_rules(data.rules), event, data.per_minute or b.per_minute or broadcasts.PACE


class NewBroadcast(BroadcastIn):
    bot_id: str = Field(..., max_length=36)


@router.post("/broadcasts")
async def create_broadcast(data: NewBroadcast, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await _own_bot(data.bot_id, ctx, db)
    b = EmailBroadcast(user_id=ctx.owner_id, bot_id=bot.bot_id, status="draft", subject="", body="", audience={})
    _apply(b, data)
    db.add(b)
    await db.commit()
    return _broadcast_json(b)


@router.get("/broadcasts/{broadcast_id}")
async def get_broadcast(broadcast_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    b = await _own(broadcast_id, ctx, db)
    return {**_broadcast_json(b), **await broadcasts.report(db, b), "notes": broadcasts.check_words(b.subject, b.body, b.subject_b)}


def _draft(b: EmailBroadcast) -> None:
    if b.status not in broadcasts.EDITABLE:
        raise HTTPException(status_code=409, detail="This one has been sent or scheduled, so it can't be changed")


@router.put("/broadcasts/{broadcast_id}")
async def save_broadcast(broadcast_id: str, data: BroadcastIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    b = await _own(broadcast_id, ctx, db)
    _draft(b)
    _apply(b, data)
    await db.commit()
    return {**_broadcast_json(b), "notes": broadcasts.check_words(b.subject, b.body, b.subject_b)}


@router.delete("/broadcasts/{broadcast_id}")
async def delete_broadcast(broadcast_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    b = await _own(broadcast_id, ctx, db)
    _draft(b)
    await db.delete(b)
    await db.commit()
    return {"status": "deleted"}


class TestIn(BaseModel):
    to: Optional[str] = Field(None, max_length=200)


@router.post("/broadcasts/{broadcast_id}/test")
async def test_send(broadcast_id: str, data: TestIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """One copy to the team, as a person would get it, marked as a test."""
    b = await _own(broadcast_id, ctx, db)
    if not (b.subject and b.body):
        raise HTTPException(status_code=400, detail="Add a subject and a message")
    rate_limit(f"broadcast-test:{ctx.owner_id}", 10, 3600)
    sender = await senders.sender_for(db, ctx.owner_id, b.bot_id)
    me = (await db.execute(select(User.email, User.name).where(User.id == ctx.user_id))).first()
    to = (data.to or "").strip() or (me.email if me else "")
    if not automations.EMAIL_RE.fullmatch(to):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    values = {"name": (me.name if me else "") or "", "first_name": compose._first_name(me.name if me else "") or "", "email": to, "business": sender.name}
    body = render.fill(b.body, values)
    await db.commit()
    sent = await email.deliver(to, f"[Test] {render.fill(b.subject, values)}"[:200], f"{body}\n\n--\n{sender.name}", automations.html_email(body, sender.name, None), reply_to=sender.reply_to,
                               from_name=sender.name, from_address=broadcasts.bulk_address(sender), api_key=sender.api_key, tags={"ws": ctx.owner_id, "kind": "test"})
    if not sent.ok:
        raise HTTPException(status_code=502, detail=sent.error or "The email didn't go")
    return {"status": "sent", "to": to}


class SendIn(BaseModel):
    at: Optional[str] = Field(None, max_length=40)  # now, if it isn't given
    usual_hour: bool = False


@router.post("/broadcasts/{broadcast_id}/send")
async def send_broadcast(broadcast_id: str, data: SendIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    from voice import schedule
    b = await _own(broadcast_id, ctx, db)
    _draft(b)
    now = datetime.utcnow()
    at = now
    if data.at:
        try:
            at = schedule.stored(datetime.fromisoformat(data.at.replace("Z", "+00:00")).astimezone(timezone.utc))
        except ValueError:
            raise HTTPException(status_code=400, detail="That time isn't one we can read")
        if at < now - timedelta(minutes=5) or at > now + broadcasts.AHEAD:
            raise HTTPException(status_code=400, detail="Choose a time in the next 60 days")
    await plans.require_feature(db, b.bot_id, "email_alerts")
    rate_limit(f"broadcast:{ctx.owner_id}", 3, 600)
    people, _ = await broadcasts.people(db, ctx.owner_id, b.bot_id, b.rules or {})
    stop = await broadcasts.problem(db, b, len(people))
    if stop:
        raise HTTPException(status_code=409, detail=stop)
    b.status, b.send_at, b.usual_hour, b.recipients = "scheduled", at, data.usual_hour, len(people)
    b.audience = {"people": len(people)}
    await db.commit()
    return _broadcast_json(b)


@router.post("/broadcasts/{broadcast_id}/{action}")
async def broadcast_action(broadcast_id: str, action: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    b = await _own(broadcast_id, ctx, db)
    if action not in ("pause", "resume", "cancel"):
        raise HTTPException(status_code=404, detail="Unknown action")
    if action == "pause":
        if b.status not in ("scheduled", "testing", "sending"):
            raise HTTPException(status_code=409, detail="This one isn't going out")
        await broadcasts.pause(db, b, "Paused by your team")
    elif action == "resume":
        if b.status != "paused":
            raise HTTPException(status_code=409, detail="This one isn't paused")
        await broadcasts.resume(db, b, datetime.utcnow())
    else:
        if b.status not in broadcasts.OPEN:
            raise HTTPException(status_code=409, detail="This one has finished")
        await broadcasts.cancel(db, b)
    await db.commit()
    return _broadcast_json(b)


# ─── who agreed ──────────────────────────────────────────────────
class ConsentIn(BaseModel):
    agreed: bool
    how: str = Field("", max_length=500)


@router.post("/consent/{contact_id}")
async def set_consent(contact_id: str, data: ConsentIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """The team notes that someone agreed, and how; or that they've stopped."""
    c = (await db.execute(select(Contact).where(Contact.id == contact_id, Contact.user_id == ctx.owner_id))).scalars().first()
    if c is None or not c.email:
        raise HTTPException(status_code=404, detail="This lead has no email")
    if data.agreed:
        if len(data.how.strip()) < 5:
            raise HTTPException(status_code=400, detail="Say how they agreed")
        if not await consent.give(db, ctx.owner_id, c.bot_id, c.email, "team", data.how.strip(), by=ctx.user_id):
            raise HTTPException(status_code=409, detail="They stopped these emails themselves, so only they can turn them back on")
    else:
        await consent.withdraw(db, ctx.owner_id, c.email, c.bot_id, by=ctx.user_id)
    record = await consent.of(db, c.bot_id, c.email)
    await db.commit()
    return record


class ImportIn(BaseModel):
    bot_id: str = Field(..., max_length=36)
    csv: str = Field(..., min_length=1, max_length=IMPORT_BYTES)
    how: str = Field(..., min_length=10, max_length=500)  # how these people agreed
    confirmed: bool = False


def _rows(text: str) -> list[dict]:
    text = text.lstrip("﻿")
    first = text.split("\n", 1)[0]
    delimiter = max(",;\t", key=first.count)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return [{str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k} for row in reader]


def _pick(row: dict, names: tuple) -> str:
    return next((row[n] for n in names if row.get(n)), "")


@router.post("/contacts/import")
async def import_contacts(data: ImportIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """A list the business already has. How they agreed is required, and kept with each person; a bought list isn't consent."""
    bot = await _own_bot(data.bot_id, ctx, db)
    await plans.require_feature(db, bot.bot_id, "email_alerts")
    if not data.confirmed:
        raise HTTPException(status_code=400, detail="Confirm these people agreed to hear from you")
    rate_limit(f"contacts-import:{ctx.owner_id}", 10, 3600)
    try:
        rows = _rows(data.csv)
    except csv.Error:
        raise HTTPException(status_code=400, detail="That file couldn't be read as a CSV")
    if len(rows) > IMPORT_ROWS:
        raise HTTPException(status_code=400, detail=f"That's {len(rows)} rows. Import up to {IMPORT_ROWS} at a time.")
    if rows and not any(n in rows[0] for n in (*EMAIL_HEADERS, *PHONE_HEADERS)):
        raise HTTPException(status_code=400, detail="The first line must name the columns, with one called email or phone")
    how = f"Imported: {data.how.strip()}"
    added, updated, agreed, skipped = 0, 0, 0, []
    for line, row in enumerate(rows, 2):
        given = _pick(row, EMAIL_HEADERS).lower()
        mail = given if automations.EMAIL_RE.fullmatch(given) else ""
        e164 = to_e164(_pick(row, PHONE_HEADERS)) or None
        if not (mail or e164):
            skipped.append({"line": line, "why": "No valid email or phone"})
            continue
        if mail and mail_address.throwaway(mail_address.domain_of(mail)):
            skipped.append({"line": line, "why": "A throwaway address"})
            continue
        contact = await journeys.find_contact(db, bot.bot_id, e164, mail)
        if contact is None:
            contact = Contact(user_id=ctx.owner_id, bot_id=bot.bot_id, e164=e164, email=mail or None, details={}, calls=0, source="import")
            db.add(contact)
            added += 1
        else:
            updated += 1
            contact.email = contact.email or mail or None
            contact.e164 = contact.e164 or e164
        name = _pick(row, NAME_HEADERS)
        contact.name = contact.name or name[:80] or None
        tags = [t.strip()[:40] for t in _pick(row, TAG_HEADERS).replace(";", ",").split(",") if t.strip()]
        if tags:
            contact.tags = sorted({*(contact.tags or []), *tags})
        known = {*NAME_HEADERS, *EMAIL_HEADERS, *PHONE_HEADERS, *TAG_HEADERS}
        contact.details = {**(contact.details or {}), **{k[:60]: v[:200] for k, v in row.items() if k not in known and v}}
        if mail:
            await db.flush()
            if await suppress.why_blocked(db, ctx.owner_id, mail, marketing=True):
                skipped.append({"line": line, "why": "They stopped your emails"})
            elif await consent.give(db, ctx.owner_id, bot.bot_id, mail, "import", how, by=ctx.user_id):
                agreed += 1
        if line % 200 == 0:
            await db.commit()
    await db.commit()
    return {"rows": len(rows), "added": added, "updated": updated, "agreed": agreed, "skipped": skipped[:20], "skipped_count": len(skipped)}
