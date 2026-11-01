"""
Email, phase 1 (mail_plan.md): the smaller emails, each off until an assistant turns it on, and the owner's daily summary.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete
from sqlalchemy.future import select

from backend.models import CallLog, Contact, Conversation, EmailJob, IntegrationSettings, KnowledgeGap, Meeting, Message, NotificationLog
from database import async_session
from mail import small
from notify import automations, digest, email, events
from voice import schedule

BASE = {
    "email_alerts": False, "alert_email": "", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
    "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "", "reply_to": "team@sunrise.in",
}
E164 = "+919876500030"
TO = "priya@buyers.in"


@pytest.fixture(autouse=True)
def tidy(run):
    yield

    async def clean():
        async with async_session() as db:
            await db.execute(delete(EmailJob).where(EmailJob.automation.in_(small.KINDS)))
            await db.commit()
    run(clean)


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def deliver(to, subject, text, html_body=None, **more):
        out.append({"to": to, "subject": subject, "text": text, "html": html_body, **more})
        return email.Delivery(True, id=f"re_{len(out)}")
    monkeypatch.setattr(email, "deliver", deliver)
    monkeypatch.setattr(email, "is_configured", lambda: True)
    return out


@pytest.fixture
def business(client, make_user, run):
    def make(*kinds, minutes=None):
        u = make_user()
        u.bot_id = u.bot("Sunrise")
        client.put("/api/integrations", json=BASE, headers=u.h())
        settings = {k: {"enabled": True} for k in kinds}
        if minutes:
            settings["missed_chat"]["minutes"] = minutes
        if settings:
            assert client.put(f"/api/email/setup/{u.bot_id}", json={"settings": settings}, headers=u.h()).status_code == 200

        async def contact():
            async with async_session() as db:
                db.add(Contact(user_id=u.id, bot_id=u.bot_id, e164=E164, name="Priya Sharma", email=TO, details={}, calls=1))
                await db.commit()
        run(contact)
        return u
    return make


async def _settled():
    import asyncio
    import notify.events as ev
    while ev._background:
        await asyncio.gather(*list(ev._background), return_exceptions=True)


def book(run, u, hours=30):
    async def go():
        tz = schedule.zone_of("Asia/Kolkata")
        await schedule.book_callback(owner_id=u.id, bot_id=u.bot_id, e164=E164, at=schedule.now_utc() + timedelta(hours=hours), about="Fees", name="Priya Sharma",
                                     source_call_id=None, number_id=None, tz=tz)
        await _settled()
    run(go)


def test_call_back_booked_tells_them_when_and_again_if_it_moves(business, run, sent):
    u = business("callback_booked")
    book(run, u)
    run(automations.process_due)
    assert len(sent) == 1 and sent[0]["to"] == TO and sent[0]["subject"].startswith("We'll call you ") and "+91 98765 00030" in sent[0]["text"]
    assert " at " in sent[0]["subject"] and "today" not in sent[0]["subject"]  # an email is read later
    book(run, u, hours=50)
    run(automations.process_due)
    assert len(sent) == 2


def test_it_is_off_until_turned_on(business, run, sent):
    u = business()
    book(run, u)
    run(automations.process_due)
    assert sent == []


def test_a_voicemail_left_gets_an_email(business, run, sent):
    u = business("voicemail")

    async def call():
        async with async_session() as db:
            c = CallLog(user_id=u.id, bot_id=u.bot_id, channel="phone", direction="outbound", caller_e164=E164, outcome="voicemail", transcript=[])
            db.add(c)
            await db.commit()
            return c.id
    run(events.call_completed, run(call))
    run(automations.process_due)
    assert sent[0]["subject"] == "We tried to call you" and "left a voicemail" in sent[0]["text"]


def chat(run, u, minutes_ago, status="pending", session="s1", captured=None):
    async def go():
        async with async_session() as db:
            c = Conversation(bot_id=u.bot_id, visitor_session_id=f"{session}-{uuid.uuid4().hex[:6]}", captured_data=captured if captured is not None else {"Name": "Priya", "Email": TO},
                             handoff_requested=True, handoff_status=status, handoff_at=datetime.utcnow() - timedelta(minutes=minutes_ago))
            db.add(c)
            await db.commit()
            return c.conversation_id
    return run(go)


def test_a_person_who_waited_too_long_hears_from_you_once(business, run, sent):
    u = business("missed_chat", minutes=5)
    chat(run, u, 2)  # not yet
    run(small.missed_chats)
    run(automations.process_due)
    assert sent == []
    chat(run, u, 6)
    run(small.missed_chats)
    run(small.missed_chats)
    run(automations.process_due)
    assert len(sent) == 1 and sent[0]["subject"] == "Sorry we missed you"


def test_not_if_someone_came_or_it_was_on_whatsapp(business, run, sent):
    u = business("missed_chat", minutes=5)
    chat(run, u, 6, status="human")
    chat(run, u, 6, session="wa:919876500030")
    run(small.missed_chats)
    run(automations.process_due)
    assert sent == []


def test_a_copy_of_the_chat_goes_only_to_the_address_given_in_it(client, business, run, sent):
    u = business("chat_copy")
    assert client.get(f"/api/bots/{u.bot_id}/config").json()["email_copy"] is True

    async def start(captured):
        async with async_session() as db:
            c = Conversation(bot_id=u.bot_id, visitor_session_id=f"widget-session-ai-{uuid.uuid4().hex}", captured_data=captured)
            db.add(c)
            await db.flush()
            db.add_all([Message(conversation_id=c.conversation_id, role="user", content="Do you have 2BHK homes?"),
                        Message(conversation_id=c.conversation_id, role="assistant", content="Yes, three are ready."),
                        Message(conversation_id=c.conversation_id, role="note", content="Internal note")])
            await db.commit()
            return c.visitor_session_id
    session = run(start, {"Email": TO})
    r = client.post("/api/chat/email-copy", json={"bot_id": u.bot_id, "visitor_session_id": session})
    assert r.json() == {"status": "sent"}
    run(automations.process_due)
    assert sent[0]["to"] == TO and sent[0]["subject"] == "Your chat with Sunrise"
    assert "Do you have 2BHK homes?" in sent[0]["text"] and "three are ready" in sent[0]["html"] and "Internal note" not in sent[0]["text"]
    none = run(start, {})
    assert client.post("/api/chat/email-copy", json={"bot_id": u.bot_id, "visitor_session_id": none}).json() == {"status": "no_address"}
    assert client.post("/api/chat/email-copy", json={"bot_id": u.bot_id, "visitor_session_id": "nope"}).json() == {"status": "no_address"}


def test_the_chat_button_stays_off_until_asked_for(client, business):
    u = business()
    assert client.get(f"/api/bots/{u.bot_id}/config").json()["email_copy"] is False


# ─── the daily summary ───────────────────────────────────────────

NOON = datetime(2030, 3, 5, 6, 30, tzinfo=timezone.utc)  # noon in India
EARLY = datetime(2030, 3, 5, 1, 0, tzinfo=timezone.utc)


def test_the_days_figures_are_counted_as_the_business_sees_days(business, run):
    u = business()

    async def fill():
        async with async_session() as db:
            db.add(Conversation(bot_id=u.bot_id, visitor_session_id="a", captured_data={"Email": "a@b.co"}, created_at=datetime(2030, 3, 4, 10, 0)))
            db.add(Conversation(bot_id=u.bot_id, visitor_session_id="b", captured_data={}, created_at=datetime(2030, 3, 4, 11, 0)))
            db.add(CallLog(user_id=u.id, bot_id=u.bot_id, channel="phone", caller_e164=E164, outcome="answered", started_at=datetime(2030, 3, 4, 12, 0)))
            db.add(CallLog(user_id=u.id, bot_id=u.bot_id, channel="browser", caller_e164=E164, outcome="answered", started_at=datetime(2030, 3, 4, 12, 0)))
            db.add(Meeting(user_id=u.id, bot_id=u.bot_id, e164=E164, starts_at=datetime(2030, 3, 5, 9, 0), status="confirmed"))
            db.add(Meeting(user_id=u.id, bot_id=u.bot_id, e164=E164, starts_at=datetime(2030, 3, 7, 9, 0), status="confirmed"))
            db.add(KnowledgeGap(bot_id=u.bot_id, question="Pets?", normalized="pets", channel="voice"))
            await db.commit()

    async def figures():
        async with async_session() as db:
            return await digest.figures(db, u.id, NOON)
    run(fill)
    f = run(figures)
    assert (f["leads"], f["calls"], f["meetings"], f["questions"]) == (1, 1, 1, 1)
    lines = digest.lines_of(f)
    assert "- 1 new lead" in lines and "- 1 call" in lines and "- 1 meeting today" in lines and "- 1 question to answer" in lines


def _turn_on(run, u):
    async def go():
        async with async_session() as db:
            s = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == u.id))).scalars().first()
            s.alert_daily = True
            await db.commit()
    run(go)


def _only(sent, u):
    return [m for m in sent if m["subject"] == "Your day on Nimmi" and m.get("tags", {}).get("ws") == u.id]


def test_it_goes_once_a_day_from_nine_and_only_when_turned_on(client, business, run, sent):
    u = business()

    async def gap():
        async with async_session() as db:
            db.add(KnowledgeGap(bot_id=u.bot_id, question="Pets?", normalized="pets", channel="voice"))
            await db.commit()
    run(gap)
    run(digest.maybe_send, NOON)
    assert _only(sent, u) == []  # off
    assert client.put("/api/integrations", json={**BASE, "alert_daily": True}, headers=u.h()).status_code == 200
    assert client.get("/api/integrations", headers=u.h()).json()["alert_daily"] is True
    run(digest.maybe_send, EARLY)
    assert _only(sent, u) == []  # before 9
    run(digest.maybe_send, NOON)
    run(digest.maybe_send, NOON)
    assert len(_only(sent, u)) == 1 and "- 1 question to answer" in _only(sent, u)[0]["text"]


def test_a_day_with_nothing_to_say_sends_nothing(business, run, sent):
    u = business()
    _turn_on(run, u)
    run(digest.maybe_send, NOON)
    assert _only(sent, u) == []
