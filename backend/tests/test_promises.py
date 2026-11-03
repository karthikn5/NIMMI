"""
Follow-up plans and promises (instagram_plan.md, phase 7). What the business promised a lead (a brochure, a price, a call back, a visit) stays open until a
record shows it was done: never because the AI said so. The AI finds promises in calls and quiet chats and emails, but one whose quote isn't really in what the
business said is dropped. A person closes one only by choosing a record or writing down what they did. Journeys start for Facebook and Instagram lead ads,
Instagram leads and any ad, the most specific first, and every step rechecks permission: won, lost and opt-out stop prospecting. Reports say why leads
were lost, by where they came from.
"""
import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.future import select

from backend.models import (CallLog, Contact, Conversation, DncEntry, EmailThread, Journey, JourneyRun, LeadEvent, LeadPromise, Meeting, Message, ThreadMessage,
                            WhatsAppChat, WhatsAppMessage, WhatsAppNumber)
from database import async_session
from leads import origin, promises
from mail import journeys
from tests.test_instagram import _drain, dm, ig, post, shop  # noqa: F401  (ig and shop are fixtures)
from tests.test_leads import alerts, joined  # noqa: F401  (fixtures)
from voice import schedule

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def desk(make_user):
    u = make_user("Owner")
    u.desk = u.bot("Sunrise")
    return u


@pytest.fixture
def asked(monkeypatch):
    """The model that reads conversations: what it's given, and what it answers (one list per call, in turn)."""
    seen, answers = [], []

    async def ask(lines, made_at, tz):
        seen.append(lines)
        return answers.pop(0) if answers else []
    monkeypatch.setattr(promises, "_ask", ask)
    return seen, answers


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


async def _all(model, **where):
    async with async_session() as db:
        q = select(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return (await db.execute(q)).scalars().all()


async def _lead(u, **values) -> Contact:
    return await _add(Contact(**{"user_id": u.id, "bot_id": u.desk, "e164": _number(), "email": f"{uuid.uuid4().hex[:8]}@buyers.in", "name": "Kavya Rao",
                                 "details": {}, "calls": 0, "source": "chat", **values}))


async def _promise(u, contact, kind, what, made_at=None, due_at=None, made_on="team") -> LeadPromise:
    made_at = made_at or datetime.utcnow() - timedelta(hours=1)
    async with async_session() as db:
        c = await db.get(Contact, contact.id)
        item = {"kind": kind, "what": what, "due_at": promises.utc(due_at or made_at + timedelta(days=1)), "due_said": due_at is not None, "words": None}
        [p] = await promises.add(db, c, [item], made_on, None, promises.utc(made_at))
        await db.commit()
        return p


async def _settle(contact_id):
    async with async_session() as db:
        n = await promises.settle_contact(db, await db.get(Contact, contact_id))
        await db.commit()
        return n


def _status(run, p) -> str:
    return run(_get, LeadPromise, p.id).status


# ─── where promises come from ────────────────────────────────────
def test_times_are_read_in_the_businesss_zone_and_never_in_the_past():
    made = datetime(2026, 11, 3, 16, 0, tzinfo=timezone.utc)  # 9:30 pm in India
    assert promises._due("2026-11-04 17:00", made, IST) == (datetime(2026, 11, 4, 17, 0, tzinfo=IST), True)
    assert promises._due("2026-11-04", made, IST) == (datetime(2026, 11, 4, 18, 0, tzinfo=IST), True)  # a day alone: 6 pm
    assert promises._due("2026-11-03", made, IST) == (datetime(2026, 11, 3, 23, 59, tzinfo=IST), True)  # "this evening", said at 9:30 pm
    assert promises._due("2026-11-01 11:00", made, IST) == (made + timedelta(days=1), False)  # a model that put "Sunday" last week
    assert promises._due("2027-03-01", made, IST)[1] is False and promises._due("soon", made, IST)[1] is False
    said = promises.next_days(made.astimezone(IST))
    assert said.startswith("The coming days: Wednesday 4 November is 2026-11-04") and "Tuesday 10 November is 2026-11-10" in said



def test_both_readers_are_told_the_coming_weeks_dates(run, monkeypatch):
    """Real models put "Sunday" in last week (a Tanglish chat, 3 Nov 2026) until the prompt named the coming days' dates."""
    import ai
    from voice import llm
    asked = []
    monkeypatch.setattr(ai, "chat", lambda system, messages, **kw: asked.append(system) or '{"promises": []}')
    assert run(promises._ask, "Business: I'll call you on Saturday.", datetime(2026, 11, 3, 16, 0, tzinfo=timezone.utc), IST) == []
    assert "Saturday 7 November is 2026-11-07" in asked[-1] and "Tuesday 3 November 2026 at 21:30" in asked[-1]

    async def complete(bot, system, user, *a, **kw):
        asked.append(system)
        return "{}"
    monkeypatch.setattr(llm, "_complete", complete)
    run(llm.summarize, None, [{"speaker": "caller", "text": "Call me Saturday"}, {"speaker": "agent", "text": "Sure"}])
    assert "The coming days: " in asked[-1] and '"promises"' in asked[-1]


def test_a_calls_promises_keep_their_words_and_an_invented_one_is_dropped(desk, run):
    c = run(_lead, desk)
    tomorrow = (datetime.now(IST) + timedelta(days=1)).date()
    transcript = [{"speaker": "caller", "text": "Can you send me the floor plan?"},
                  {"speaker": "agent", "text": "Of course. I'll send you the floor plan on WhatsApp by tomorrow evening."},
                  {"speaker": "caller", "text": "And call me tomorrow at 11."}, {"speaker": "agent", "text": "Sure, someone will call you at 11."}]
    found = [{"kind": "send", "what": "Floor plan of the 2BHK", "due": f"{tomorrow} 18:00", "words": "I’ll send you the floor plan on WhatsApp"},  # a curly quote: still found
             {"kind": "price", "what": "Price list", "due": None, "words": "We will email you the full price list tonight"}]  # never said: dropped
    call = run(_add, CallLog(user_id=desk.id, bot_id=desk.desk, direction="inbound", channel="phone", caller_e164=c.e164, outcome="answered", transcript=transcript,
                             ended_at=datetime.utcnow(), next_step={"promises": found, "call_back_at": f"{tomorrow} 11:00"}))
    assert run(promises.from_call, call.id) == 2
    rows = {p.kind: p for p in run(_all, LeadPromise, contact_id=c.id)}
    assert set(rows) == {"send", "callback"}
    send, back = rows["send"], rows["callback"]
    assert (send.made_on, send.ref, send.words, send.due_said) == ("call", call.id, "I’ll send you the floor plan on WhatsApp", True)
    assert promises.utc(send.due_at).astimezone(IST).replace(tzinfo=None) == datetime(tomorrow.year, tomorrow.month, tomorrow.day, 18, 0)
    assert promises.utc(back.due_at).astimezone(IST).hour == 11 and back.what == "Call them back"
    assert run(promises.from_call, call.id) == 0  # the same call again: nothing twice
    # "Call me" from the dashboard is the business trying its agent: no promises, even to a number that is a lead.
    tester = run(_lead, desk)
    test = run(_add, CallLog(user_id=desk.id, bot_id=desk.desk, direction="outbound", channel="phone", caller_e164=tester.e164, outcome="answered", transcript=transcript,
                             consent_source=schedule.TEST_CALL, ended_at=datetime.utcnow(), next_step={"promises": found, "call_back_at": f"{tomorrow} 11:00"}))
    assert run(promises.from_call, test.id) == 0 and run(_all, LeadPromise, contact_id=tester.id) == []
    story = [e.text for e in run(_all, LeadEvent, contact_id=c.id) if e.kind == "promise"]
    assert len(story) == 2 and all(t.startswith("Promised on a phone call:") for t in story)


def test_the_end_of_a_phone_call_keeps_its_promises(desk, run, monkeypatch):
    """The call's own last steps (pipeline._remember_and_plan) keep what the analysis found."""
    from mail import after_call as after_call_email
    from tests.test_pipeline import FakeStt, FakeTransport, _setup, fake_summary, fake_tts, replier_saying
    from voice import memory, pipeline

    async def nothing(*_a):
        return None
    for module, name in ((memory, "remember_call"), (schedule, "after_call"), (after_call_email, "queue")):
        monkeypatch.setattr(module, name, nothing)
    c = run(_lead, desk)
    call = run(_add, CallLog(user_id=desk.id, bot_id=desk.desk, direction="inbound", channel="phone", caller_e164=c.e164, outcome="answered", ended_at=datetime.utcnow(),
                             transcript=[{"speaker": "agent", "text": "I'll email you the brochure after this call."}],
                             next_step={"promises": [{"kind": "send", "what": "Brochure", "due": None, "words": "I'll email you the brochure"}]}))

    async def finish():
        session = pipeline.CallSession(await _setup(desk.id, desk.desk), FakeTransport(), stt_factory=lambda *a: FakeStt([]), tts=fake_tts,
                                       replier=replier_saying("x"), summarizer=fake_summary)
        session.call_id = call.id
        await session._remember_and_plan()
    run(finish)
    [p] = run(_all, LeadPromise, contact_id=c.id)
    assert (p.kind, p.what, p.made_on, p.ref) == ("send", "Brochure", "call", call.id)


def test_quiet_chats_are_read_once_and_only_the_businesss_own_words_count(desk, run, asked):
    seen, answers = asked
    c = run(_lead, desk)
    conv = run(_add, Conversation(bot_id=desk.desk, visitor_session_id=f"wa:{c.e164.lstrip('+')}", contact_id=c.id))
    early = datetime.utcnow() - timedelta(minutes=40)
    run(_add, Message(conversation_id=conv.conversation_id, role="user", content="Can you send the brochure?", timestamp=early))
    run(_add, Message(conversation_id=conv.conversation_id, role="assistant", content="Sure! I'll send you the brochure here on WhatsApp today.",
                      timestamp=early + timedelta(seconds=5)))
    assert promises.utc(run(_get, Conversation, conv.conversation_id).last_message_at) == promises.utc(early + timedelta(seconds=5))  # every new message marks it
    answers.append([{"kind": "send", "what": "Brochure", "due": None, "words": "I'll send you the brochure here on WhatsApp today"},
                    {"kind": "price", "what": "Price", "due": None, "words": "Can you send the brochure?"}])  # the customer's words: not a promise of the business

    async def twice():  # two server processes at once
        await asyncio.gather(promises.scan(), promises.scan())
    run(twice)
    assert len(seen) == 1 and "Business: Sure! I'll send you the brochure" in seen[0] and "Customer: Can you send the brochure?" in seen[0]
    [p] = run(_all, LeadPromise, contact_id=c.id)
    assert (p.kind, p.made_on, p.ref, p.due_said) == ("send", "whatsapp", conv.conversation_id, False)
    assert promises.utc(p.due_at) - promises.utc(early + timedelta(seconds=5)) == timedelta(days=1)  # no time said: expected within a day
    run(promises.scan)
    assert len(seen) == 1  # read already
    # Later the team writes again: only what's new is read, and the promise is theirs.
    later = datetime.utcnow() - timedelta(minutes=31)
    run(_add, Message(conversation_id=conv.conversation_id, role="assistant", content="I'll call you tomorrow at 11 about the site visit.", timestamp=later, author_id=desk.id))
    answers.append([{"kind": "callback", "what": "Call about the site visit", "due": None, "words": "I'll call you tomorrow at 11"}])
    run(promises.scan)
    assert len(seen) == 2 and "brochure" not in seen[1] and "tomorrow at 11" in seen[1]
    back = next(p for p in run(_all, LeadPromise, contact_id=c.id) if p.kind == "callback")
    assert back.made_by == desk.id
    # A chat that isn't quiet yet, and one with nobody behind it (not a lead), aren't read.
    run(_add, Message(conversation_id=conv.conversation_id, role="assistant", content="I'll send photos now.", timestamp=datetime.utcnow() - timedelta(minutes=5)))
    stranger = run(_add, Conversation(bot_id=desk.desk, visitor_session_id="widget-session-ai-x"))
    run(_add, Message(conversation_id=stranger.conversation_id, role="assistant", content="I'll email you the details.", timestamp=early))
    run(promises.scan)
    assert len(seen) == 2


def test_a_chat_is_read_only_on_a_plan(desk, run, asked, monkeypatch):
    seen, _ = asked
    c = run(_lead, desk)
    conv = run(_add, Conversation(bot_id=desk.desk, visitor_session_id="widget-session-ai-y", contact_id=c.id))
    run(_add, Message(conversation_id=conv.conversation_id, role="assistant", content="Our team will call you back today.", timestamp=datetime.utcnow() - timedelta(hours=1)))
    monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")  # the assistant has no plan: reading chats with AI comes with one
    run(promises.scan)
    assert seen == [] and run(_all, LeadPromise, contact_id=c.id) == []


def test_email_conversations_are_read_and_a_draft_sent_later_still_counts(desk, run, asked):
    seen, answers = asked
    c = run(_lead, desk)
    hour_ago = datetime.utcnow() - timedelta(hours=1)
    thread = run(_add, EmailThread(user_id=desk.id, bot_id=desk.desk, code=uuid.uuid4().hex[:16], email=c.email.lower(), subject="2BHK", last_at=hour_ago))
    run(_add, ThreadMessage(thread_id=thread.id, user_id=desk.id, direction="in", who="customer", status="received", text="Is parking included?", created_at=hour_ago))
    run(_add, ThreadMessage(thread_id=thread.id, user_id=desk.id, direction="out", who="ai", status="sent", text="Yes. We will send you the quotation by Friday.",
                            created_at=hour_ago + timedelta(seconds=30)))
    draft = run(_add, ThreadMessage(thread_id=thread.id, user_id=desk.id, direction="out", who="team", status="draft", text="I'll courier the agreement copy.",
                                    created_at=hour_ago + timedelta(seconds=40), by=desk.id))
    answers.append([{"kind": "price", "what": "Quotation", "due": None, "words": "We will send you the quotation by Friday"}])
    run(promises.scan)
    assert len(seen) == 1 and "agreement" not in seen[0]  # a draft hasn't gone
    [p] = run(_all, LeadPromise, contact_id=c.id)
    assert (p.kind, p.made_on, p.ref) == ("price", "email", thread.id)
    # The draft is sent long after it was written: it's read then, and only it.
    async def sent_now():
        async with async_session() as db:
            await db.execute(update(ThreadMessage).where(ThreadMessage.id == draft.id).values(status="sent"))
            await db.execute(update(EmailThread).where(EmailThread.id == thread.id).values(last_at=datetime.utcnow() - timedelta(minutes=31)))
            await db.commit()
    run(sent_now)
    # The earlier email comes along as context, and the model names its promise again in other words: only the new email's words count.
    answers.append([{"kind": "price", "what": "Price quote by Friday", "due": None, "words": "We will send you the quotation by Friday"},
                    {"kind": "send", "what": "Agreement copy", "due": None, "words": "I'll courier the agreement copy"}])
    run(promises.scan)
    assert len(seen) == 2
    rows = run(_all, LeadPromise, contact_id=c.id)
    assert sorted(p.kind for p in rows) == ["price", "send"] and next(p for p in rows if p.kind == "send").made_by == desk.id


# ─── what closes a promise ───────────────────────────────────────
def test_a_promise_closes_only_on_a_record_that_shows_it(desk, run):
    c = run(_lead, desk)
    made = datetime.utcnow() - timedelta(hours=2)
    number = run(_add, WhatsAppNumber(user_id=desk.id, phone_number_id=uuid.uuid4().hex))
    chat = run(_add, WhatsAppChat(number_id=number.id, user_id=desk.id, bot_id=desk.desk, wa_user=c.e164.lstrip("+"), wa_id=c.e164.lstrip("+")))
    # A file sent before the promise doesn't keep it.
    run(_add, WhatsAppMessage(chat_id=chat.id, direction="out", kind="document", sent_by="ai", media={"filename": "old.pdf"}, status="sent", created_at=made - timedelta(hours=1)))
    send, price, back, visit, other = (run(_promise, desk, c, k, w, made_at=made) for k, w in (
        ("send", "Floor plan"), ("price", "Price of the 3BHK"), ("callback", "Call them back"), ("visit", "Site visit"), ("other", "Ask the builder about parking")))
    conv = run(_add, Conversation(bot_id=desk.desk, visitor_session_id=f"wa:{c.e164.lstrip('+')}", contact_id=c.id))
    run(_add, Message(conversation_id=conv.conversation_id, role="assistant", content="We'll share the details soon.", timestamp=made + timedelta(minutes=5)))
    run(_add, CallLog(user_id=desk.id, bot_id=desk.desk, direction="inbound", channel="phone", caller_e164=c.e164, outcome="answered",
                      transcript=[{"speaker": "caller", "text": "Hello?"}], started_at=made + timedelta(minutes=10)))  # they rang: not the business calling back
    run(_add, CallLog(user_id=desk.id, bot_id=desk.desk, direction="outbound", channel="phone", caller_e164=c.e164, outcome="no_answer", transcript=[],
                      started_at=made + timedelta(minutes=20)))  # nobody picked up
    run(_add, Meeting(user_id=desk.id, bot_id=desk.desk, e164=c.e164, starts_at=datetime.utcnow() + timedelta(days=2), status="requested"))  # asked, not confirmed
    assert run(_settle, c.id) == 0
    assert {_status(run, p) for p in (send, price, back, visit, other)} == {"open"}
    # The records that do show it.
    run(_add, WhatsAppMessage(chat_id=chat.id, direction="out", kind="document", sent_by="ai", media={"filename": "floor-plan.pdf"}, status="delivered",
                              created_at=made + timedelta(minutes=30)))
    run(_add, Message(conversation_id=conv.conversation_id, role="assistant", content="The 3BHK is Rs 62 lakh, all inclusive.", timestamp=made + timedelta(minutes=31)))
    talked = run(_add, CallLog(user_id=desk.id, bot_id=desk.desk, direction="outbound", channel="phone", caller_e164=c.e164, outcome="answered",
                               transcript=[{"speaker": "agent", "text": "Hi Kavya"}, {"speaker": "caller", "text": "Yes, tell me"}], started_at=made + timedelta(minutes=40)))

    async def confirm():
        async with async_session() as db:
            await db.execute(update(Meeting).where(Meeting.e164 == c.e164).values(status="confirmed", decided_at=datetime.utcnow()))
            await db.commit()
    run(confirm)
    assert run(_settle, c.id) == 4
    done = {p.kind: run(_get, LeadPromise, p.id) for p in (send, price, back, visit)}
    assert all(p.status == "done" and p.done_by is None for p in done.values())
    assert done["send"].evidence["text"] == "File sent on WhatsApp: floor-plan.pdf" and done["send"].evidence["kind"] == "whatsapp_file"
    assert done["price"].evidence["kind"] == "message" and "Rs 62 lakh" in done["price"].evidence["text"]
    assert (done["callback"].evidence["kind"], done["callback"].evidence["id"]) == ("call", talked.id)
    assert done["visit"].evidence["kind"] == "meeting"
    assert _status(run, other) == "open"  # nothing in the records can show it: a person says what did it
    kept = [e.text for e in run(_all, LeadEvent, contact_id=c.id) if e.kind == "promise_kept"]
    assert len(kept) == 4 and any("floor-plan.pdf" in t for t in kept)


def test_the_teams_spoke_to_them_keeps_a_call_back_and_the_scheduler_finds_it_once(desk, client, run):
    c = run(_lead, desk)
    back = run(_promise, desk, c, "callback", "Call them back")
    r = client.post(f"/api/crm/leads/{c.id}/result", json={"result": "no_answer"}, headers=desk.h())
    assert r.status_code == 200
    promises._last_pass = None
    run(promises.settle)
    assert _status(run, back) == "open"  # no answer isn't a call-back
    run(_add, LeadEvent(user_id=desk.id, bot_id=desk.desk, contact_id=c.id, kind="result", text="Spoke to them: wants a Sunday visit", by=desk.id))

    async def due_again():  # the pass looks again after CHECK_EVERY
        async with async_session() as db:
            await db.execute(update(LeadPromise).where(LeadPromise.id == back.id).values(checked_at=datetime.utcnow() - timedelta(minutes=3)))
            await db.commit()
    run(due_again)

    async def two_passes():
        await asyncio.gather(promises.settle(), promises.settle())
    run(two_passes)
    p = run(_get, LeadPromise, back.id)
    assert p.status == "done" and p.evidence["kind"] == "result" and "Spoke to them" in p.evidence["text"]
    assert len([e for e in run(_all, LeadEvent, contact_id=c.id) if e.kind == "promise_kept"]) == 1


def test_the_team_closes_a_promise_only_with_evidence_or_their_own_words(desk, client, run, joined):
    c, other = run(_lead, desk), run(_lead, desk)
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = client.post(f"/api/crm/leads/{c.id}/promises", json={"kind": "other", "what": "Send the site plan by courier", "due_at": due}, headers=desk.h())
    assert r.status_code == 200 and r.json()["status"] == "open" and r.json()["due_said"] and r.json()["made_on"] == "team"
    pid = r.json()["id"]
    assert client.post(f"/api/crm/leads/{c.id}/promises", json={"kind": "other", "what": "Send the site plan by courier"}, headers=desk.h()).status_code == 409
    assert client.post(f"/api/crm/leads/{c.id}/promises", json={"kind": "gift", "what": "x"}, headers=desk.h()).status_code == 400
    # Never just "done".
    assert client.post(f"/api/crm/promises/{pid}/done", json={}, headers=desk.h()).status_code == 400
    assert client.post(f"/api/crm/promises/{pid}/done", json={"how": "other", "note": "  "}, headers=desk.h()).status_code == 400
    # A record of someone else, or from before the promise, isn't evidence.
    conv = run(_add, Conversation(bot_id=desk.desk, visitor_session_id="widget-session-ai-z", contact_id=other.id))
    elsewhere = run(_add, Message(conversation_id=conv.conversation_id, role="assistant", content="Here is the plan.", timestamp=datetime.utcnow()))
    assert client.post(f"/api/crm/promises/{pid}/done", json={"kind": "message", "id": elsewhere.id}, headers=desk.h()).status_code == 400
    mine = run(_add, Conversation(bot_id=desk.desk, visitor_session_id="widget-session-ai-w", contact_id=c.id))
    before = run(_add, Message(conversation_id=mine.conversation_id, role="assistant", content="An old message", timestamp=datetime.utcnow() - timedelta(days=1)))
    assert client.post(f"/api/crm/promises/{pid}/done", json={"kind": "message", "id": before.id}, headers=desk.h()).status_code == 400
    # What was done since: the person chooses it.
    sent = run(_add, Message(conversation_id=mine.conversation_id, role="assistant", content="Couriered the site plan today, tracking DTDC 552.",
                             timestamp=datetime.utcnow() + timedelta(seconds=1)))
    shown = client.get(f"/api/crm/promises/{pid}/evidence", headers=desk.h()).json()
    assert [(a["kind"], a["id"]) for a in shown] == [("message", sent.id)]
    r = client.post(f"/api/crm/promises/{pid}/done", json={"kind": "message", "id": sent.id}, headers=desk.h())
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["done_by"] == "Owner" and "DTDC 552" in r.json()["evidence"]["text"]
    assert client.post(f"/api/crm/promises/{pid}/done", json={"kind": "message", "id": sent.id}, headers=desk.h()).status_code == 409  # once

    async def again():  # the records pass getting there at the same moment as the person: still once
        async with async_session() as db:
            p = await db.get(LeadPromise, pid)
            return await promises.keep(db, p, await db.get(Contact, c.id), {"kind": "message", "id": sent.id, "at": None, "text": "x"}, None)
    assert run(again) is False
    # Done outside Nimmi: in their own words, under their name.
    pid2 = client.post(f"/api/crm/leads/{c.id}/promises", json={"kind": "send", "what": "Brochure"}, headers=desk.h()).json()["id"]
    r = client.post(f"/api/crm/promises/{pid2}/done", json={"how": "whatsapp", "note": "Sent from my own phone"}, headers=desk.h())
    assert r.status_code == 200 and r.json()["evidence"] == {**r.json()["evidence"], "kind": "record", "text": "On WhatsApp: Sent from my own phone"}
    # Cancelled, with why.
    pid3 = client.post(f"/api/crm/leads/{c.id}/promises", json={"kind": "visit", "what": "Site visit"}, headers=desk.h()).json()["id"]
    assert client.post(f"/api/crm/promises/{pid3}/cancel", json={"why": ""}, headers=desk.h()).status_code == 422
    r = client.post(f"/api/crm/promises/{pid3}/cancel", json={"why": "They bought elsewhere"}, headers=desk.h())
    assert r.status_code == 200 and (r.json()["status"], r.json()["cancelled_why"]) == ("cancelled", "They bought elsewhere")
    lead = client.get(f"/api/crm/leads/{c.id}", headers=desk.h()).json()
    assert [p["status"] for p in lead["promises"]] == ["done", "done", "cancelled"] and "send" in lead["promise_kinds"]
    # A salesperson reaches only the promises of leads given to them.
    seller = joined(desk, "agent", "Meena")
    pid4 = client.post(f"/api/crm/leads/{c.id}/promises", json={"kind": "price", "what": "Price"}, headers=desk.h()).json()["id"]
    assert client.get(f"/api/crm/promises/{pid4}/evidence", headers=seller.h(desk.id)).status_code == 404
    assert client.post(f"/api/crm/promises/{pid4}/cancel", json={"why": "x"}, headers=seller.h(desk.id)).status_code == 404
    assert client.put(f"/api/crm/leads/{c.id}", json={"assigned_to": seller.id}, headers=desk.h()).status_code == 200
    assert client.post(f"/api/crm/promises/{pid4}/cancel", json={"why": "Not needed"}, headers=seller.h(desk.id)).status_code == 200


# ─── stop rules, reminders, Needs attention, reports ─────────────
def test_lost_cancels_whats_promised_a_customer_keeps_it_and_do_not_call_ends_a_call_back(desk, client, run):
    lost, won, dnc = run(_lead, desk), run(_lead, desk), run(_lead, desk)
    p_lost, p_won = run(_promise, desk, lost, "send", "Brochure"), run(_promise, desk, won, "send", "Invoice")
    assert client.post(f"/api/crm/leads/{lost.id}/close", json={"outcome": "lost", "reason": "Too expensive"}, headers=desk.h()).status_code == 200
    assert client.post(f"/api/crm/leads/{won.id}/close", json={"outcome": "won", "amount": 4500000}, headers=desk.h()).status_code == 200
    p = run(_get, LeadPromise, p_lost.id)
    assert (p.status, p.cancelled_why) == ("cancelled", "The lead was closed as lost")
    assert _status(run, p_won) == "open"  # a customer still gets what they were promised
    back = run(_promise, desk, dnc, "callback", "Call them back")
    run(_add, DncEntry(user_id=desk.id, e164=dnc.e164, reason="caller_request"))
    promises._last_pass = None
    run(promises.settle)
    p = run(_get, LeadPromise, back.id)
    assert (p.status, p.cancelled_why) == ("cancelled", "They asked not to be called")


def test_a_promise_come_due_is_told_once_and_shows_on_needs_attention(desk, client, run, alerts, joined):
    seller = joined(desk, "agent", "Meena")
    c = run(_lead, desk, assigned_to=seller.id)
    mine = run(_lead, desk)
    late = run(_promise, desk, c, "send", "Floor plan", made_at=datetime.utcnow() - timedelta(days=2), due_at=datetime.utcnow() - timedelta(hours=2))
    run(_promise, desk, mine, "price", "Price", made_at=datetime.utcnow() - timedelta(days=2), due_at=datetime.utcnow() - timedelta(hours=1))
    run(_promise, desk, c, "visit", "Visit", due_at=datetime.utcnow() + timedelta(days=5))  # not due yet

    async def twice():
        await asyncio.gather(promises.remind(), promises.remind())
    run(twice)
    told = [a for a in alerts if a[2].startswith("Promised, not done yet")]
    assert {(a[1], a[2]) for a in told} == {(seller.id, "Promised, not done yet: Floor plan"), (None, "Promised, not done yet: Price")}  # nobody has that lead: the owner
    run(promises.remind)
    assert len([a for a in alerts if a[2].startswith("Promised, not done yet")]) == 2  # once each
    owner_view = client.get("/api/crm/queues", headers=desk.h()).json()["promises"]
    assert {p["what"] for p in owner_view} == {"Floor plan", "Price"} and all(p["late"] for p in owner_view)
    seller_view = client.get("/api/crm/queues", headers=seller.h(desk.id)).json()["promises"]
    assert [p["id"] for p in seller_view] == [late.id] and seller_view[0]["lead"]["id"] == c.id


def test_reports_say_why_leads_were_lost_by_source_and_how_promises_went(desk, client, run):
    a, b, d = run(_lead, desk, source="instagram"), run(_lead, desk, source="instagram"), run(_lead, desk, source="chat")
    for lead, reason in ((a, "Too expensive"), (b, "Too expensive"), (d, "Not interested")):
        assert client.post(f"/api/crm/leads/{lead.id}/close", json={"outcome": "lost", "reason": reason}, headers=desk.h()).status_code == 200
    kept = run(_lead, desk)
    on_time = run(_promise, desk, kept, "other", "Brochure by courier", due_at=datetime.utcnow() + timedelta(days=1))
    run(_promise, desk, kept, "price", "Price", due_at=datetime.utcnow() - timedelta(hours=1))  # late, still open
    r = client.post(f"/api/crm/promises/{on_time.id}/done", json={"how": "other", "note": "Couriered"}, headers=desk.h())
    assert r.status_code == 200
    report = client.get("/api/crm/reports?days=30", headers=desk.h()).json()
    by = {row["source"]: row for row in report["lost_by_source"]}
    assert by["instagram"]["lost"] == 2 and by["instagram"]["reasons"] == [{"reason": "Too expensive", "count": 2}]
    assert by["chat"]["reasons"] == [{"reason": "Not interested", "count": 1}]
    assert {k: report["promises"][k] for k in ("made", "kept", "on_time", "late", "cancelled")} == {"made": 2, "kept": 1, "on_time": 1, "late": 1, "cancelled": 0}


# ─── journeys for the new sources ────────────────────────────────
def test_a_lead_from_an_ad_is_told_apart(run):
    assert origin.from_ad({"channel": "meta_ads"}) and origin.from_ad({"channel": "website", "gclid": "Cj0"}) and origin.from_ad({"utm_medium": "CPC"})
    assert origin.from_ad({"channel": "instagram_ad", "ad_id": "1"}) and origin.from_ad({"ctwa_clid": "x"})
    assert not origin.from_ad({"channel": "website", "fbclid": "IwAR"})  # Facebook adds it to every link, ads or not
    assert not origin.from_ad({"channel": "website", "utm_medium": "email"}) and not origin.from_ad(None)


def _journey(u, value, name, steps=None) -> str:
    async def make():
        async with async_session() as db:
            j = Journey(user_id=u.id, bot_id=u.desk, name=name, trigger="new_lead", trigger_value=value, enabled=True,
                        steps=steps or [{"type": "wait", "days": 1}, {"type": "notify", "text": "Follow up"}])
            db.add(j)
            await db.commit()
            return j.id
    return make


def test_the_most_specific_journey_starts_for_a_lead_ad_and_any_ad_catches_the_rest(desk, run):
    anyone, any_ad, meta = run(_journey(desk, None, "Any lead")), run(_journey(desk, "any_ad", "Any ad")), run(_journey(desk, "meta", "Lead ads"))
    c1, c2, c3 = run(_lead, desk), run(_lead, desk), run(_lead, desk)
    assert run(journeys.fire, desk.id, desk.desk, "new_lead", c1.id, ("meta", "ads", "any_ad")) == 1
    assert run(journeys.fire, desk.id, desk.desk, "new_lead", c2.id, ("chat", "any_ad")) == 1
    assert run(journeys.fire, desk.id, desk.desk, "new_lead", c3.id, ("chat",)) == 1
    started = {r.contact_id: r.journey_id for r in run(_all, JourneyRun, bot_id=desk.desk) if r.status == "active"}
    assert started == {c1.id: meta, c2.id: any_ad, c3.id: anyone}
    # One follow-up plan per lead: asking again from another place doesn't start a second chase while the first runs.
    assert run(journeys.fire, desk.id, desk.desk, "new_lead", c1.id, ("chat",)) == 0


def test_an_instagram_lead_starts_its_journey_when_they_first_write(client, shop, ig, run):
    u = shop()

    async def journey():
        async with async_session() as db:
            j = Journey(user_id=u.id, bot_id=u.bot_id, name="Instagram leads", trigger="new_lead", trigger_value="instagram", enabled=True,
                        steps=[{"type": "notify", "text": "New Instagram lead"}])
            db.add(j)
            await db.commit()
            return j.id
    jid = run(journey)
    igsid = str(10 ** 16 + uuid.uuid4().int % 10 ** 16)
    post(client, dm(u.ig_id, igsid, "Hi, is the 2BHK available?"))
    run(_drain)
    [contact] = run(_all, Contact, bot_id=u.bot_id)
    assert contact.instagram_id == igsid and [r.journey_id for r in run(_all, JourneyRun, contact_id=contact.id)] == [jid]  # no number or email needed


def test_won_lost_and_opt_out_stop_a_lead_ad_journey_at_its_next_step(desk, client, run):
    jid = run(_journey(desk, "meta", "Lead ads", steps=[{"type": "wait", "days": 1}, {"type": "email", "subject": "Your enquiry", "body": "Hi {{first_name|there}}"}]))
    won, lost, refused, kept = (run(_lead, desk) for _ in range(4))
    for c in (won, lost, refused, kept):
        assert run(journeys.fire, desk.id, desk.desk, "new_lead", c.id, ("meta", "ads", "any_ad")) == 1
    assert client.post(f"/api/crm/leads/{won.id}/close", json={"outcome": "won", "amount": 1}, headers=desk.h()).status_code == 200
    assert client.post(f"/api/crm/leads/{lost.id}/close", json={"outcome": "lost", "reason": "Not interested"}, headers=desk.h()).status_code == 200
    run(_add, DncEntry(user_id=desk.id, e164=refused.e164, reason="caller_request"))

    async def unsubscribed():
        from mail import suppress
        async with async_session() as db:
            await suppress.add(db, desk.id, refused.email, "unsubscribed", "all")
            await db.commit()
    run(unsubscribed)

    async def due_now():
        async with async_session() as db:
            await db.execute(update(JourneyRun).where(JourneyRun.journey_id == jid, JourneyRun.status == "active").values(next_at=datetime.utcnow() - timedelta(seconds=1)))
            await db.commit()
    run(due_now)
    for r in run(_all, JourneyRun, journey_id=jid):
        run(journeys.advance, r.id)
    runs = {r.contact_id: r for r in run(_all, JourneyRun, journey_id=jid)}
    assert runs[won.id].status != "active" and runs[lost.id].status != "active"
    assert runs[refused.id].status == "stopped" and runs[refused.id].reason in ("They can't be emailed any more", "They're on the do-not-call list")
    assert runs[kept.id].status == "active"  # the one nobody stopped goes on to its wait
