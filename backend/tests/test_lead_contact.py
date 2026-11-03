"""
First response and one set of stop rules (instagram_plan.md, phase 4): nothing automatic reaches a lead without a cause and their word for that channel; every
blocker reads as a sentence; an Indian number not declared for automated calls never dials by itself; a call that may have gone through isn't dialled again;
two submissions at once make one first contact; a reply, a takeover, a meeting, an opt-out or a closed lead stops everything waiting, in every channel; a
meeting request is never spoken of as booked; the WhatsApp template for a new lead and the salesperson's WhatsApp alert go only when allowed.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.future import select

from backend.models import (Bot, CallbackJob, ChannelPermission, Contact, Conversation, DncEntry, EmailJob, Journey, JourneyRun, LeadEvent, LeadIntake, LeadTask,
                            Meeting, PhoneNumber, User, WhatsAppChat, WhatsAppNumber)
from database import async_session
from leads import contact as reach, core
from mail import agent as email_agent, intake, journeys
from notify import channels
from tests.test_lead_sources import _settled, business, fired, on, sent  # noqa: F401  (fixtures)
from tests.test_leads import joined  # noqa: F401  (a fixture)
from tests.test_voice_schedule import _save
from voice import accounts, metering, scheduler, schedule, twilio

NOW = datetime.now(timezone.utc)


def _number() -> str:
    return f"+9198{uuid.uuid4().int % 100_000_000:08d}"


async def _add(*rows):
    async with async_session() as db:
        db.add_all(rows)
        await db.commit()
    return rows[0]


async def _get(model, key):
    async with async_session() as db:
        return await db.get(model, key)


async def _person(user_id, bot_id, **values) -> Contact:
    base = dict(user_id=user_id, bot_id=bot_id, e164=_number(), email=f"{uuid.uuid4().hex[:8]}@buyers.in", name="Kavya Rao", details={}, calls=0,
                last_enquiry_at=NOW - timedelta(hours=1))
    return await _add(Contact(**{**base, **values}))


async def _verdict(contact_id, channel, purpose="service", **more):
    async with async_session() as db:
        return await reach.can_contact(db, await db.get(Contact, contact_id), channel, purpose, hours=False, **more)


async def _record(contact_id, channel, state, source, words=None):
    async with async_session() as db:
        await reach.record(db, await db.get(Contact, contact_id), channel, state, source, words)
        await db.commit()


@pytest.fixture
def daytime(monkeypatch):
    """The lead page's answers include the business's hours (calls 9 am to 9 pm, messages 9 am to 8 pm, India): a test that reads them has its clock at
    the next 11 am India time when it runs in the evening or at night (they failed after 9 pm on 3 Nov 2026). At most a day later, so enquiries keep
    their 7 days."""
    ist = timezone(timedelta(hours=5, minutes=30))
    local = NOW.astimezone(ist)
    if 10 <= local.hour < 19:
        return NOW
    day = local.date() + (timedelta(days=1) if local.hour >= 19 else timedelta())
    pinned = datetime(day.year, day.month, day.day, 11, 0, tzinfo=ist).astimezone(timezone.utc)
    monkeypatch.setattr(reach, "_now", lambda: pinned)
    return pinned


@pytest.fixture(autouse=True)
def _no_calls_left(run):
    """Calls these tests leave due would be dialled by a later test's dialler pass (it reads every workspace): end them."""
    yield

    async def end():
        async with async_session() as db:
            await db.execute(update(CallbackJob).where(CallbackJob.status.in_(("queued", "calling", "review"))).values(status="cancelled"))
            await db.commit()
    run(end)


@pytest.fixture
def desk(make_user):
    u = make_user("Owner")
    u.desk = u.bot("Sunrise")
    return u


@pytest.fixture
def templates(monkeypatch):
    """WhatsApp templates that would have gone to Meta."""
    out = []

    async def send(to_e164, template, language, body_params, phone_number_id=None, token=None):
        out.append({"to": to_e164, "template": template, "language": language, "params": body_params})
    monkeypatch.setattr(channels, "send_whatsapp_template", send)
    return out


# ─── a cause and their word ──────────────────────────────────────
def test_a_call_needs_their_enquiry_in_the_last_7_days_or_their_yes(client, desk, run, daytime):
    fresh = run(_person, desk.id, desk.desk)
    ok = run(_verdict, fresh.id, "call")
    assert ok.ok and "allows calls until" in ok.cause
    never = run(_person, desk.id, desk.desk, last_enquiry_at=None)
    old = run(_person, desk.id, desk.desk, last_enquiry_at=NOW - timedelta(days=8))
    for c in (never, old):
        v = run(_verdict, c.id, "call")
        assert (v.ok, v.code, v.reason) == (False, "window", "Their enquiry is more than 7 days old and they haven't agreed to a call")
    # They said yes on the phone: the team writes it down, with how; it lasts seven days, as TRAI's consent does.
    r = client.post(f"/api/crm/leads/{old.id}/permissions", json={"channel": "call", "state": "granted"}, headers=desk.h())
    assert r.status_code == 400 and "how they agreed" in r.json()["detail"]
    r = client.post(f"/api/crm/leads/{old.id}/permissions", json={"channel": "call", "state": "granted", "words": "Said yes on the phone on 3 Nov"}, headers=desk.h())
    assert r.status_code == 200 and r.json()["reach"]["call"]["ok"] is True and "Said yes on the phone" in r.json()["reach"]["call"]["cause"]
    [kept] = r.json()["permissions"]
    assert (kept["channel"], kept["state"], kept["source"]) == ("call", "granted", "team") and kept["expires_at"]

    async def lapse():
        async with async_session() as db:
            await db.execute(update(ChannelPermission).where(ChannelPermission.contact_id == old.id).values(expires_at=datetime.utcnow() - timedelta(minutes=1)))
            await db.commit()
    run(lapse)
    assert run(_verdict, old.id, "call").code == "window"


def test_a_form_is_no_yes_to_whatsapp_but_their_tick_or_message_is(desk, run):
    c = run(_person, desk.id, desk.desk)
    v = run(_verdict, c.id, "whatsapp")
    assert (v.ok, v.code) == (False, "permission") and "a form submission isn't an opt-in" in v.reason
    run(_record, c.id, "whatsapp", "granted", "form", "Ticked on the website form")
    v = run(_verdict, c.id, "whatsapp")
    assert v.ok and v.cause == "They agreed to WhatsApp (Ticked on the website form)"
    # Someone who wrote on WhatsApp in the last day can be answered there.
    wrote = run(_person, desk.id, desk.desk)
    n = run(_add, WhatsAppNumber(user_id=desk.id, phone_number_id=uuid.uuid4().hex[:12], display_number="+91 90000 00000", status="active"))
    run(_add, WhatsAppChat(number_id=n.id, user_id=desk.id, wa_user=wrote.e164.lstrip("+"), wa_id=wrote.e164.lstrip("+"), last_inbound_at=datetime.utcnow() - timedelta(hours=2)))
    assert run(_verdict, wrote.id, "whatsapp").cause == "They wrote on WhatsApp in the last 24 hours"


def test_email_answers_the_enquiry_for_a_month_and_offers_need_their_agreement(desk, run):
    from mail import consent
    recent = run(_person, desk.id, desk.desk, last_enquiry_at=NOW - timedelta(days=10))
    assert run(_verdict, recent.id, "email").cause == "About the enquiry they made"
    old = run(_person, desk.id, desk.desk, last_enquiry_at=NOW - timedelta(days=40))
    assert run(_verdict, old.id, "email").reason == "Their enquiry is over a month old, and they haven't agreed to offers and news"
    assert run(_verdict, recent.id, "email", "marketing").code == "permission"

    async def agree():
        async with async_session() as db:
            await consent.give(db, desk.id, desk.desk, old.email, "form", "Ticked on the website form")
            await db.commit()
    run(agree)
    assert run(_verdict, old.id, "email", "marketing").ok


def test_every_blocker_says_why_in_words(client, desk, joined, run, monkeypatch):
    seller = joined(desk, "agent", "Meena")

    def why(contact_id, channel="call", **more):
        v = run(_verdict, contact_id, channel, **more)
        assert not v.ok and v.reason and "None" not in v.reason and "{" not in v.reason
        return v
    assert why(run(_person, desk.id, desk.desk, quality="junk").id).reason == "Marked as junk"
    assert why(run(_person, desk.id, desk.desk, quality="wrong_number").id).reason == "Their number was wrong"
    assert why(run(_person, desk.id, desk.desk, e164=None).id).reason == "No phone number for them"
    dnc = run(_person, desk.id, desk.desk)
    run(_add, DncEntry(user_id=desk.id, e164=dnc.e164, reason="manual"))
    assert why(dnc.id).reason == "Their number is on your do-not-call list"
    said_no = run(_person, desk.id, desk.desk)
    run(_record, said_no.id, "call", "refused", "call", "Please don't call me")
    assert why(said_no.id).reason == "They asked not to be contacted by phone"
    lost = run(_person, desk.id, desk.desk, lead_status="not_interested")
    assert why(lost.id).reason == "They said they're not interested"
    # Someone on the team working them: a chat taken over, a try today, their own task for the next day.
    chat = run(_person, desk.id, desk.desk)
    run(_add, Conversation(bot_id=desk.desk, visitor_session_id="widget-session-human-x", contact_id=chat.id, handoff_status="human", agent_id=seller.id))
    assert why(chat.id).reason == "Meena took over their chat, so nothing automatic goes meanwhile"
    planned = run(_person, desk.id, desk.desk)
    run(_add, LeadTask(user_id=desk.id, bot_id=desk.desk, contact_id=planned.id, title="Send the brochure", kind="email", due_at=datetime.utcnow() + timedelta(hours=3),
                       origin="team", created_by=seller.id))
    assert why(planned.id).reason == "Meena plans to: Send the brochure, so nothing automatic goes meanwhile"
    # The team handling their WhatsApp chat (on one of two numbers: the other chat, never paused, mustn't hide it).
    handled = run(_person, desk.id, desk.desk)
    for paused in (None, datetime.utcnow() + timedelta(hours=5)):
        n = run(_add, WhatsAppNumber(user_id=desk.id, phone_number_id=uuid.uuid4().hex[:12], display_number="+91 90000 00009", status="active"))
        run(_add, WhatsAppChat(number_id=n.id, user_id=desk.id, wa_user=handled.e164.lstrip("+"), wa_id=handled.e164.lstrip("+"), ai_paused_until=paused))
    assert why(handled.id).reason == "Your team is handling their WhatsApp chat, so nothing automatic goes meanwhile"
    tried = run(_person, desk.id, desk.desk)
    assert client.post(f"/api/crm/leads/{tried.id}/result", json={"result": "no_answer"}, headers=desk.h()).status_code == 200
    assert why(tried.id).reason == "Owner tried them today, so nothing automatic goes meanwhile"
    # A meeting request isn't a booking until the team approves it.
    asked = run(_person, desk.id, desk.desk)
    run(_add, Meeting(user_id=desk.id, bot_id=desk.desk, e164=asked.e164, status="requested", starts_at=datetime.utcnow() + timedelta(days=2), history=[]))
    v = why(asked.id)
    assert v.code == "meeting" and v.reason.startswith("They have a meeting request waiting for your answer for ") and "booked" not in v.reason
    run(_add, Meeting(user_id=desk.id, bot_id=desk.desk, e164=chat.e164, status="confirmed", starts_at=datetime.utcnow() + timedelta(days=2), history=[]))
    assert why(chat.id).reason.startswith("They have a meeting booked for ")
    # What they asked for themselves goes ahead of a closed lead or a person on it, never past their own no.
    assert run(_verdict, lost.id, "call", cause="They asked for a call-back").ok
    assert run(_verdict, said_no.id, "call", cause="They asked for a call-back").code == "refused"
    monkeypatch.setattr(metering, "enough_for_a_call", lambda credits, per_minute: False)
    assert why(run(_person, desk.id, desk.desk).id).reason == "No voice credits left: buy credits in Billing"


# ─── the number calls go from ────────────────────────────────────
def test_an_undeclared_indian_number_never_dials_by_itself(client, desk, run, monkeypatch):
    monkeypatch.setenv("A2P_GATE", "on")
    placed = []

    async def place(to, frm, job_id, **_):
        placed.append((to, frm))
        return f"CA-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(twilio, "place_call", place)
    _save(run, desk.id, desk.desk)
    ours = run(_add, PhoneNumber(user_id=desk.id, number="+91 44 4000 1000", e164="+914440001000", status="active", provider="twilio", bot_id=desk.desk))
    us = run(_add, PhoneNumber(user_id=desk.id, number="+1 484 328 5015", e164="+14843285015", status="active", provider="twilio"))
    assert reach.a2p_blocked(us) is None
    who = run(_person, desk.id, desk.desk)
    job = run(_add, CallbackJob(user_id=desk.id, bot_id=desk.desk, e164=who.e164, kind="callback", status="queued", consent_source="Asked on a call",
                                next_attempt_at=datetime.utcnow() - timedelta(minutes=1), from_number_id=ours.id))
    run(scheduler.dispatch_due_callbacks)
    stopped = run(_get, CallbackJob, job.id)
    assert placed == [] and stopped.status == "failed" and "+91 44 4000 1000 isn't declared for automated calls" in stopped.last_error and "Voice > Numbers" in stopped.last_error
    shown = next(n for n in client.get("/api/voice/numbers", headers=desk.h()).json() if n["id"] == ours.id)
    assert shown["a2p"] == {"needed": True, "declared_at": None, "proof": None}
    assert client.put(f"/api/voice/numbers/{ours.id}/a2p", json={"declared": True}, headers=desk.h()).status_code == 400  # what shows it is required
    r = client.put(f"/api/voice/numbers/{ours.id}/a2p", json={"declared": True, "proof": "Exotel ticket 4411, 3 Nov"}, headers=desk.h())
    assert r.status_code == 200 and r.json()["a2p"]["declared_at"] and r.json()["a2p"]["proof"] == "Exotel ticket 4411, 3 Nov"

    async def again():
        async with async_session() as db:
            await db.execute(update(CallbackJob).where(CallbackJob.id == job.id).values(status="queued", last_error=None))
            await db.commit()
    run(again)
    run(scheduler.dispatch_due_callbacks)
    assert placed == [(who.e164, "+914440001000")]


def test_campaigns_and_schedule_calls_each_check_the_declaration(desk, run, monkeypatch):
    """Two places dial: campaigns and old call-backs through the dialler's own check, Schedule's calls through dial_check. Each holds alone."""
    from backend.models import Campaign
    monkeypatch.setenv("A2P_GATE", "on")
    placed = []

    async def place(to, frm, job_id, **_):
        placed.append(job_id)
        return f"CA-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(twilio, "place_call", place)
    _save(run, desk.id, desk.desk)
    ours = run(_add, PhoneNumber(user_id=desk.id, number="+91 44 4000 2000", e164="+914440002000", status="active", provider="twilio", bot_id=desk.desk))
    campaign = run(_add, Campaign(user_id=desk.id, bot_id=desk.desk, name="Diwali", status="running", from_number_id=ours.id, window_start="00:00", window_end="23:59"))
    job = run(_add, CallbackJob(user_id=desk.id, bot_id=desk.desk, e164=_number(), campaign_id=campaign.id, status="queued", consent_source="Their list",
                                next_attempt_at=datetime.utcnow() - timedelta(minutes=1)))
    run(scheduler.dispatch_due_callbacks)
    assert placed == [] and run(_get, Campaign, campaign.id).status == "paused" and "isn't declared for automated calls" in run(_get, CallbackJob, job.id).last_error
    assert run(_get, CallbackJob, job.id).status == "queued"  # it waits for the declaration and a Resume

    follow = run(_add, CallbackJob(user_id=desk.id, bot_id=desk.desk, e164=_number(), kind="callback", status="queued", consent_source="Asked on a call",
                                   next_attempt_at=datetime.utcnow(), from_number_id=ours.id))

    async def check():
        async with async_session() as db:
            return await schedule.dial_check(db, await db.get(CallbackJob, follow.id))
    stop = run(check).stop
    assert stop[0] == "failed" and "+91 44 4000 2000 isn't declared for automated calls" in stop[1]


def test_a_dial_that_may_have_gone_through_waits_for_review(desk, run, monkeypatch):
    _save(run, desk.id, desk.desk)
    run(_add, PhoneNumber(user_id=desk.id, number="+1 484 328 5015", e164="+14843285015", status="active", provider="twilio", bot_id=desk.desk))
    errors = iter([httpx.ReadTimeout("no answer"), httpx.ConnectError("refused")])

    async def dial(db, number, to, job_id, detect_voicemail=False):
        raise next(errors)
    monkeypatch.setattr(accounts, "dial", dial)
    sent_out = run(_add, CallbackJob(user_id=desk.id, bot_id=desk.desk, e164=_number(), kind="callback", status="queued", consent_source="Asked on a call",
                                     next_attempt_at=datetime.utcnow() - timedelta(minutes=1)))
    run(scheduler.dispatch_due_callbacks)
    after = run(_get, CallbackJob, sent_out.id)
    assert after.status == "review" and "may have gone through" in after.last_error                     # not dialled again by itself
    never = run(_add, CallbackJob(user_id=desk.id, bot_id=desk.desk, e164=_number(), kind="callback", status="queued", consent_source="Asked on a call",
                                  next_attempt_at=datetime.utcnow() - timedelta(minutes=1)))
    run(scheduler.dispatch_due_callbacks)
    assert run(_get, CallbackJob, never.id).status == "queued"                                          # never left: tried again later
    assert scheduler.maybe_placed(httpx.RemoteProtocolError("dropped")) and not scheduler.maybe_placed(httpx.PoolTimeout("busy"))


def test_never_two_calls_to_one_person_at_once(desk, run, monkeypatch):
    _save(run, desk.id, desk.desk)
    run(_add, PhoneNumber(user_id=desk.id, number="+1 484 328 5015", e164="+14843285015", status="active", provider="twilio", bot_id=desk.desk))
    placed = []

    async def place(to, frm, job_id, **_):
        placed.append(job_id)
        return f"CA-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(twilio, "place_call", place)
    e164 = _number()
    run(_add, CallbackJob(user_id=desk.id, bot_id=desk.desk, e164=e164, kind=None, status="calling", consent_source="Campaign", next_attempt_at=datetime.utcnow()))
    waiting = run(_add, CallbackJob(user_id=desk.id, bot_id=desk.desk, e164=e164, kind="callback", status="queued", consent_source="Asked on a call",
                                    next_attempt_at=datetime.utcnow() - timedelta(minutes=1)))
    run(scheduler.dispatch_due_callbacks)
    assert placed == [] and run(_get, CallbackJob, waiting.id).status == "queued"


# ─── the first call to an enquiry ────────────────────────────────
def test_the_first_call_stops_for_a_person_on_it_and_after_7_days_but_a_call_back_they_asked_for_doesnt(desk, joined, run):
    seller = joined(desk, "agent", "Meena")

    async def check(job_id):
        async with async_session() as db:
            return await schedule.dial_check(db, await db.get(CallbackJob, job_id))

    def job(person, consent):
        return run(_add, CallbackJob(user_id=desk.id, bot_id=desk.desk, e164=person.e164, kind="callback", status="queued", consent_source=consent,
                                     next_attempt_at=datetime.utcnow()))
    _save(run, desk.id, desk.desk)
    run(_add, PhoneNumber(user_id=desk.id, number="+1 484 328 5015", e164="+14843285015", status="active", provider="twilio", bot_id=desk.desk))
    old = run(_person, desk.id, desk.desk, last_enquiry_at=NOW - timedelta(days=8))
    assert run(check, job(old, f"{schedule.LEAD_CALL} Google lead forms on 26 Oct 2026").id).stop == ("cancelled", "Their enquiry is more than 7 days old")
    taken = run(_person, desk.id, desk.desk)
    run(_add, Conversation(bot_id=desk.desk, visitor_session_id="widget-session-human-y", contact_id=taken.id, handoff_status="human", agent_id=seller.id))
    assert run(check, job(taken, f"{schedule.LEAD_CALL} Website form on 3 Nov 2026").id).stop == ("cancelled", "Meena took over their chat, so nothing automatic goes meanwhile")
    asked = job(taken, "Asked on a call on 3 Nov 2026 at 10:00 to be called back")
    assert run(check, asked.id).stop is None and run(check, asked.id).from_number_id
    run(_record, taken.id, "call", "refused", "call", "Stop calling me")                                   # their no after they asked
    assert run(check, asked.id).stop == ("cancelled", "They asked not to be contacted by phone")
    # A no they gave before asking for the call-back doesn't stop the call they asked for later.
    changed = run(_person, desk.id, desk.desk)
    run(_record, changed.id, "call", "refused", "call", "Not now")
    later = run(_add, CallbackJob(user_id=desk.id, bot_id=desk.desk, e164=changed.e164, kind="callback", status="queued", consent_source="Asked on a call",
                                  next_attempt_at=datetime.utcnow(), created_at=datetime.utcnow() + timedelta(seconds=2)))
    assert run(check, later.id).stop is None


# ─── one first contact, however many submissions ─────────────────
def test_two_submissions_at_once_make_one_first_contact(client, business, run, sent, fired):
    u = business()
    _save(run, u.id, u.bot_id)
    assert client.put(f"/api/email/setup/{u.bot_id}", json={"settings": {"lead_call": {"enabled": True, "minutes": 5}}}, headers=u.h()).status_code == 200

    async def twice():
        async with async_session() as db:
            bot = await db.get(Bot, u.bot_id)
        found = {"name": "Priya", "phone": "98765 00511", "email": "priya@buyers.in", "wants": "A 2BHK", "portal": "Website form"}
        return await asyncio.gather(intake.act(bot, found), intake.act(bot, found))
    notes = sorted(note for note, _ in run(twice))
    run(_settled)
    assert len([j for j in run(_jobs, u.bot_id)]) == 1
    assert len([s for s in sent if s["subject"].startswith("New lead")]) == 1
    assert notes[0].startswith("Another submission from them is being handled at this moment") or notes[1].startswith("Another submission")


async def _jobs(bot_id):
    async with async_session() as db:
        return (await db.execute(select(CallbackJob).where(CallbackJob.bot_id == bot_id))).scalars().all()


# ─── one chase at a time ─────────────────────────────────────────
async def _chasing(user_id, bot_id, contact: Contact):
    """A follow-up call, a journey and the email agent's email, all waiting for them; and a call-back they asked for."""
    async with async_session() as db:
        journey = Journey(user_id=user_id, bot_id=bot_id, name="New leads", trigger="new_lead", steps=[{"type": "wait", "days": 1}], enabled=True)
        db.add(journey)
        await db.flush()
        run_ = JourneyRun(journey_id=journey.id, user_id=user_id, bot_id=bot_id, contact_id=contact.id, status="active", step=0, slot="active",
                          next_at=datetime.utcnow() + timedelta(days=1))
        follow = CallbackJob(user_id=user_id, bot_id=bot_id, e164=contact.e164, kind="follow_up", status="queued", consent_source="t", next_attempt_at=datetime.utcnow() + timedelta(days=1))
        asked = CallbackJob(user_id=user_id, bot_id=bot_id, e164=contact.e164, kind="callback", status="queued", consent_source="Asked on a call", next_attempt_at=datetime.utcnow() + timedelta(days=1))
        mail = EmailJob(user_id=user_id, bot_id=bot_id, kind=f"agent#{uuid.uuid4().hex[:8]}", ref_id=contact.id, to_email=contact.email, automation="agent", step=1,
                        status="queued", send_at=datetime.utcnow() + timedelta(hours=2), subject="Following up", body="Hello")
        db.add_all([run_, follow, asked, mail])
        await db.commit()
        return run_.id, follow.id, asked.id, mail.id


def _stopped(run, ids, why):
    run_id, follow_id, asked_id, mail_id = ids
    r, f, a, m = run(_get, JourneyRun, run_id), run(_get, CallbackJob, follow_id), run(_get, CallbackJob, asked_id), run(_get, EmailJob, mail_id)
    assert (r.status, f.status, m.status) == ("stopped", "cancelled", "cancelled") and why in r.reason and why in f.last_error
    assert a.status == "queued"  # what they asked for themselves stays


def test_a_takeover_stops_everything_waiting_in_every_channel(client, desk, run):
    c = run(_person, desk.id, desk.desk)
    ids = run(_chasing, desk.id, desk.desk, c)
    conv = run(_add, Conversation(bot_id=desk.desk, visitor_session_id="widget-session-human-z", contact_id=c.id, handoff_status="pending"))
    assert client.post(f"/api/handoffs/{conv.conversation_id}/accept", headers=desk.h()).status_code == 200
    run(_settled)
    _stopped(run, ids, reach.TOOK_OVER)

    async def story():
        async with async_session() as db:
            return [e.text for e in (await db.execute(select(LeadEvent).where(LeadEvent.contact_id == c.id, LeadEvent.kind == "stopped"))).scalars().all()]
    assert run(story) == [f"{reach.TOOK_OVER}: 3 automatic steps stopped"]


def test_their_reply_stops_everything_waiting(desk, run):
    from backend.models import EmailThread
    c = run(_person, desk.id, desk.desk)
    ids = run(_chasing, desk.id, desk.desk, c)

    async def reply():
        async with async_session() as db:
            await journeys.stopped_by_reply(db, EmailThread(user_id=desk.id, bot_id=desk.desk, code="r1", email=c.email))
            await db.commit()
    run(reply)
    _stopped(run, ids, "They replied")
    # On WhatsApp too: their message stops what waits for them.
    w = run(_person, desk.id, desk.desk)
    ids = run(_chasing, desk.id, desk.desk, w)
    conv = run(_add, Conversation(bot_id=desk.desk, visitor_session_id=f"wa:{w.e164.lstrip('+')}"))
    run(reach.stop_for_chat, conv.conversation_id, reach.WROTE)
    _stopped(run, ids, reach.WROTE)


def test_an_opt_out_a_closed_lead_or_a_meeting_stops_it_too(client, desk, run):
    dnc = run(_person, desk.id, desk.desk)
    ids = run(_chasing, desk.id, desk.desk, dnc)
    assert client.post("/api/voice/dnc", json={"number": dnc.e164}, headers=desk.h()).status_code == 200
    r, f, m = run(_get, JourneyRun, ids[0]), run(_get, CallbackJob, ids[1]), run(_get, EmailJob, ids[3])
    assert r.status == "stopped" and m.status == "cancelled" and f is None  # the list removes their waiting calls outright, as before
    lost = run(_person, desk.id, desk.desk)
    ids = run(_chasing, desk.id, desk.desk, lost)
    assert client.post(f"/api/crm/leads/{lost.id}/close", json={"outcome": "lost", "reason": "Bought elsewhere"}, headers=desk.h()).status_code == 200
    _stopped(run, ids, "Lost")
    met = run(_person, desk.id, desk.desk)
    ids = run(_chasing, desk.id, desk.desk, met)
    from voice import meetings
    settings = _save(run, desk.id, desk.desk, meetings={"approval": True, "hours": ["00:00", "23:59"]})
    when = (datetime.now(schedule.zone(settings)) + timedelta(days=2)).replace(hour=11, minute=0, second=0, microsecond=0)
    said, meeting = run(meetings.book, settings, owner_id=desk.id, bot_id=desk.desk, e164=met.e164, args={"date": when.strftime("%Y-%m-%d"), "time": "11:00"},
                        name=met.name, source_call_id=None, test=False)
    assert meeting is not None and meeting.status == "requested"
    assert said.startswith("Requested:") and "confirmed" not in said.split(".")[0] and "Booked" not in said  # a request is never told as a booking
    r, f, m = run(_get, JourneyRun, ids[0]), run(_get, CallbackJob, ids[1]), run(_get, EmailJob, ids[3])
    assert (r.status, f.status, m.status) == ("stopped", "cancelled", "cancelled") and r.reason == "They asked for a meeting"


def test_a_journey_waits_while_a_person_works_the_lead(desk, joined, run):
    seller = joined(desk, "agent", "Meena")
    c = run(_person, desk.id, desk.desk)
    ids = run(_chasing, desk.id, desk.desk, c)
    run(_add, LeadTask(user_id=desk.id, bot_id=desk.desk, contact_id=c.id, title="Call her back", kind="call", due_at=datetime.utcnow() + timedelta(hours=1),
                       origin="team", created_by=seller.id))

    async def due_now():
        async with async_session() as db:
            await db.execute(update(JourneyRun).where(JourneyRun.id == ids[0]).values(next_at=datetime.utcnow() - timedelta(minutes=1)))
            (await db.get(Journey, (await db.get(JourneyRun, ids[0])).journey_id)).enabled = True
            await db.commit()
    run(due_now)
    run(journeys.advance, ids[0])
    r = run(_get, JourneyRun, ids[0])
    assert r.status == "active" and schedule.utc(r.next_at) > NOW + timedelta(hours=5) and r.history[-1]["what"].startswith("Meena plans to: Call her back")
    run(journeys.advance, ids[0], datetime.utcnow() + timedelta(hours=7))
    assert len([h for h in run(_get, JourneyRun, ids[0]).history if h["what"].startswith("Meena plans")]) == 1  # noted once


def test_the_email_agent_leaves_alone_someone_the_team_is_working(desk, joined, run):
    seller = joined(desk, "agent", "Meena")
    c = run(_person, desk.id, desk.desk, last_enquiry_at=NOW - timedelta(days=5))
    run(_add, Conversation(bot_id=desk.desk, visitor_session_id="widget-session-human-q", contact_id=c.id, handoff_status="human", agent_id=seller.id))

    async def why():
        async with async_session() as db:
            return await email_agent._why_not(db, await db.get(Contact, c.id), datetime.utcnow())
    assert run(why) == "Meena took over their chat, so nothing automatic goes meanwhile"


# ─── their word, on the lead's page ──────────────────────────────
def test_the_lead_page_shows_each_channel_and_keeps_what_they_said(client, desk, run, daytime):
    c = run(_person, desk.id, desk.desk)
    lead = client.get(f"/api/crm/leads/{c.id}", headers=desk.h()).json()
    assert set(lead["reach"]) == {"call", "whatsapp", "email"} and lead["reach"]["call"]["ok"] and not lead["reach"]["whatsapp"]["ok"] and lead["permissions"] == []
    assert client.post(f"/api/crm/leads/{c.id}/permissions", json={"channel": "fax", "state": "granted", "words": "x"}, headers=desk.h()).status_code == 400
    r = client.post(f"/api/crm/leads/{c.id}/permissions", json={"channel": "whatsapp", "state": "refused", "words": "Asked on the phone not to message"}, headers=desk.h())
    assert r.status_code == 200 and r.json()["reach"]["whatsapp"]["code"] == "refused"
    run(_record, c.id, "whatsapp", "refused", "whatsapp", "STOP")  # their own no, in their own words
    r = client.post(f"/api/crm/leads/{c.id}/permissions", json={"channel": "whatsapp", "state": "granted", "words": "I think they'd like it"}, headers=desk.h())
    assert r.status_code == 409 and "Only they can change that" in r.json()["detail"]
    run(_record, c.id, "whatsapp", "granted", "whatsapp", "Yes, send me updates")  # they can
    assert run(_verdict, c.id, "whatsapp").ok
    # A no written down by the team stops what was waiting for them on that channel and the rest of the chase.
    other = run(_person, desk.id, desk.desk)
    ids = run(_chasing, desk.id, desk.desk, other)
    assert client.post(f"/api/crm/leads/{other.id}/permissions", json={"channel": "call", "state": "refused", "words": "Said on WhatsApp: no calls"}, headers=desk.h()).status_code == 200
    _stopped(run, ids, "They asked not to be contacted by phone")


def test_a_stored_time_without_a_zone_is_utc_whatever_the_computers_clock(monkeypatch):
    """SQLite gives times back without a zone; they're UTC. On a computer set to India time, reading them as local put follow-ups and bulk emails 5.5 hours early."""
    import time
    from datetime import date
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    time.tzset()
    try:
        at = schedule._their_hour(date(2026, 11, 3), datetime(2026, 11, 2, 12, 0), ["09:00", "20:00"], schedule.zone_of("Asia/Kolkata"), "x@example.com")
    finally:
        monkeypatch.undo()
        time.tzset()
    assert at.astimezone(schedule.zone_of("Asia/Kolkata")).hour == 17  # 12:00 UTC is 5:30 pm in India


# ─── WhatsApp: a new lead's first message, the salesperson's alert ─
def test_a_new_lead_who_said_yes_gets_the_whatsapp_template_and_nobody_else_does(client, business, run, sent, fired, templates):
    u = business()
    run(_add, WhatsAppNumber(user_id=u.id, phone_number_id=uuid.uuid4().hex[:12], display_number="+91 90000 00001", status="active", access_token="tok"))
    base = client.get(f"/api/crm/settings/{u.bot_id}", headers=u.h()).json()["settings"]
    assert base["whatsapp_first"] is None and base["alert_template"] is None
    bad = client.put(f"/api/crm/settings/{u.bot_id}", json={"assign": "off", "whatsapp_first": "Hello World"}, headers=u.h())
    assert bad.status_code == 400 and "small letters" in bad.json()["detail"]
    assert client.put(f"/api/crm/settings/{u.bot_id}", json={"assign": "off", "whatsapp_first": "new_lead_hello", "whatsapp_language": "en_US"}, headers=u.h()).status_code == 200
    old_page = client.put(f"/api/crm/settings/{u.bot_id}", json={"assign": "off", "people": [], "backup": None, "first_task": True, "respond_minutes": 20}, headers=u.h())
    assert old_page.json()["settings"]["whatsapp_first"] == "new_lead_hello"  # a page that doesn't know the field keeps it
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Kavya Rao", "phone": "98765 00611", "email": "kavya@buyers.in", "whatsapp_ok": "yes"})
    run(_settled)
    assert templates == [{"to": "+919876500611", "template": "new_lead_hello", "language": "en_US", "params": ["Kavya", "Sunrise"]}]
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Ravi", "phone": "98765 00612", "email": "ravi@buyers.in"})
    run(_settled)
    assert len(templates) == 1

    async def notes():
        async with async_session() as db:
            return [r.note for r in (await db.execute(select(LeadIntake).where(LeadIntake.bot_id == u.bot_id).order_by(LeadIntake.created_at))).scalars().all()]
    first, second = run(notes)
    assert "WhatsApp sent" in first and "no WhatsApp: They haven't agreed to WhatsApp messages" in second

    async def kept():
        async with async_session() as db:
            return (await db.execute(select(ChannelPermission).where(ChannelPermission.bot_id == u.bot_id))).scalars().all()
    [p] = run(kept)
    assert (p.channel, p.state, p.source, p.words) == ("whatsapp", "granted", "form", "Ticked on the website form")
    # Lost, then asking again a day later with the box ticked: a new enquiry, so they hear back.
    lead = run(_by_phone, u.bot_id, "+919876500611")
    assert client.post(f"/api/crm/leads/{lead.id}/close", json={"outcome": "lost", "reason": "Bought elsewhere"}, headers=u.h()).status_code == 200

    async def a_day_later():
        async with async_session() as db:
            await db.execute(update(Contact).where(Contact.id == lead.id).values(last_enquiry_at=datetime.utcnow() - timedelta(hours=25)))
            await db.commit()
    run(a_day_later)
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Kavya Rao", "phone": "98765 00611", "email": "kavya@buyers.in", "whatsapp_ok": "yes", "message": "Is it still there?"})
    run(_settled)
    assert len(templates) == 2 and templates[1]["to"] == "+919876500611"


def test_the_salesperson_hears_of_a_new_lead_on_whatsapp(client, business, run, sent, fired, templates):
    u = business()
    run(_add, WhatsAppNumber(user_id=u.id, phone_number_id=uuid.uuid4().hex[:12], display_number="+91 90000 00002", status="active", access_token="tok"))
    assert client.patch("/api/auth/profile", json={"whatsapp": "12345"}, headers=u.h()).status_code == 400
    r = client.patch("/api/auth/profile", json={"whatsapp": "98765 43210"}, headers=u.h())
    assert r.status_code == 200 and r.json()["whatsapp"] == "+919876543210" and client.get("/api/auth/profile", headers=u.h()).json()["whatsapp"] == "+919876543210"
    assert client.put(f"/api/crm/settings/{u.bot_id}", json={"assign": "one", "people": [u.id], "alert_template": "lead_alert"}, headers=u.h()).status_code == 200
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Kavya Rao", "phone": "98765 00711", "email": "kavya2@buyers.in"})
    run(_settled)
    [alert] = templates
    lead = run(_by_phone, u.bot_id, "+919876500711")
    assert alert["to"] == "+919876543210" and alert["template"] == "lead_alert" and alert["params"][0].startswith("New lead: Call Kavya Rao")
    assert alert["params"][1].endswith(f"/dashboard/leads/{lead.id}")


async def _by_phone(bot_id, e164):
    async with async_session() as db:
        return (await db.execute(select(Contact).where(Contact.bot_id == bot_id, Contact.e164 == e164))).scalars().first()
