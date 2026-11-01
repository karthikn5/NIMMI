"""
Email, phase 1 (mail_plan.md): the pages people open from an email, and meeting emails from the design. Opening a link never does
anything, because scanners open links; the buttons do. Links are signed for one meeting or one person. Bookings go through Schedule
and only times that were on offer are accepted. A meeting's email has the right buttons for what's happening, and after it comes a
thank-you, or "sorry we missed you" with a link to book again.
"""
import html
import re
from datetime import datetime, timedelta

import pytest
from sqlalchemy.future import select

from auth import issue_scoped_token
from backend.models import CallbackJob, Contact, Meeting
from database import async_session
from mail import links
from notify import email
from voice import meetings, schedule

BASE = {
    "email_alerts": False, "alert_email": "", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
    "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "", "reply_to": "team@sunrise.in",
}
E164 = "+919876500020"
TO = "priya@buyers.in"


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def deliver(to, subject, text, html_body=None, **more):
        out.append({"to": to, "subject": subject, "text": text, "html": html_body, **more})
        return email.Delivery(True, id=f"re_{len(out)}")
    monkeypatch.setattr(email, "deliver", deliver)
    return out


@pytest.fixture
def business(client, make_user, run):
    def make(approval=False, phone=True):
        u = make_user()
        u.bot_id = u.bot("Sunrise")
        client.put("/api/integrations", json=BASE, headers=u.h())
        s = client.get(f"/api/voice/schedule/settings/{u.bot_id}", headers=u.h()).json()["settings"]
        s["callbacks"]["enabled"] = True
        s["meetings"].update(enabled=True, approval=approval, link="https://meet.google.com/abc", days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
        assert client.put(f"/api/voice/schedule/settings/{u.bot_id}", json=s, headers=u.h()).status_code == 200

        async def contact():
            async with async_session() as db:
                db.add(Contact(user_id=u.id, bot_id=u.bot_id, e164=E164 if phone else None, name="Priya Sharma", email=TO, details={}, calls=1))
                await db.commit()
        run(contact)
        return u
    return make


def meeting_for(run, u, status="confirmed", days=3):
    async def go():
        async with async_session() as db:
            m = Meeting(user_id=u.id, bot_id=u.bot_id, e164=E164, name="Priya Sharma", email=TO, kind="online",
                        starts_at=(datetime.utcnow() + timedelta(days=days)).replace(hour=5, minute=30, second=0, microsecond=0), status=status, minutes=30, history=[])
            db.add(m)
            await db.commit()
            return m.id
    return run(go)


async def _meeting(mid):
    async with async_session() as db:
        return await db.get(Meeting, mid)


def path(url):
    return url[url.index("/api/"):]


def said(response):
    return html.unescape(response.text)


def first_time(html):
    return re.search(r'<option value="([^"]+)"', html).group(1)


def test_opening_a_link_never_changes_anything(client, business, run):
    u = business()
    mid = meeting_for(run, u)
    for view in ("", "change", "cancel"):
        assert client.get(path(links.meeting_url(mid, view))).status_code == 200
    assert run(_meeting, mid).status == "confirmed"


def test_someone_cancels_their_meeting_from_the_email(client, business, run):
    u = business()
    mid = meeting_for(run, u)
    url = path(links.meeting_url(mid, "cancel"))
    assert "Cancel your meeting?" in said(client.get(url))
    done = client.post(url.split("&view")[0], data={"action": "cancel"})
    assert "Your meeting is cancelled" in said(done)
    m = run(_meeting, mid)
    assert m.status == "cancelled" and "the link in an email" in m.history[-1]["what"]
    assert "isn't active" in said(client.get(url))


def test_someone_moves_their_meeting_to_a_free_time(client, business, run):
    u = business()
    mid = meeting_for(run, u)
    url = path(links.meeting_url(mid, "change"))
    page = said(client.get(url))
    assert "Change the time" in page and re.search(r">[A-Z][a-z]+ \d+ [A-Z][a-z]+ at ", page)  # "Monday 2 November at 10 am"
    at = first_time(page)
    done = client.post(url.split("&view")[0], data={"action": "pick", "at": at})
    assert "Your meeting has moved" in said(done)
    m = run(_meeting, mid)
    assert schedule.utc(m.starts_at) == datetime.fromisoformat(at) and "the link in an email" in m.history[-1]["what"]


def test_a_time_that_was_not_on_offer_is_refused(client, business, run):
    u = business()
    mid = meeting_for(run, u)
    before = run(_meeting, mid).starts_at
    url = path(links.meeting_url(mid))
    client.post(url, data={"action": "pick", "at": "2031-01-01T03:00:00+05:30"})
    assert run(_meeting, mid).starts_at == before


def test_with_approval_on_a_move_waits_for_the_team(client, business, run):
    u = business(approval=True)
    mid = meeting_for(run, u, status="confirmed")
    url = path(links.meeting_url(mid, "change"))
    done = client.post(url.split("&view")[0], data={"action": "pick", "at": first_time(said(client.get(url)))})
    assert "The team will confirm it" in said(done) and run(_meeting, mid).status == "requested"


def test_a_link_is_for_its_own_purpose_and_a_forged_one_gets_nothing(client, business, run):
    u = business()
    mid = meeting_for(run, u)
    assert "isn't active" in said(client.get("/api/email/p/meeting?token=nonsense"))
    wrong = issue_scoped_token(mid, "email_unsub", 60)
    assert "isn't active" in said(client.get(f"/api/email/p/meeting?token={wrong}"))
    assert "expired" in said(client.get("/api/email/p/book?token=nonsense"))
    assert "expired" in said(client.get("/api/email/p/call?token=nonsense"))


def test_someone_books_a_time_from_an_email(client, business, run):
    u = business()
    url = path(links.book_url(u.id, u.bot_id, TO))
    page = said(client.get(url))
    assert "Book a time with Sunrise" in page and 'name="phone"' not in page  # their number is on file
    done = client.post(url, data={"action": "pick", "at": first_time(page)})
    assert "It's booked" in said(done)

    async def booked():
        async with async_session() as db:
            return (await db.execute(select(Meeting).where(Meeting.bot_id == u.bot_id))).scalars().first()
    m = run(booked)
    assert m.e164 == E164 and m.email == TO and m.name == "Priya Sharma" and "the link in an email" in m.history[-1]["what"]


def test_without_a_number_on_file_the_page_asks_for_it(client, business, run):
    u = business(phone=False)
    url = path(links.book_url(u.id, u.bot_id, TO))
    page = said(client.get(url))
    assert 'name="phone"' in page
    at = first_time(page)
    assert "didn't work" in said(client.post(url, data={"action": "pick", "at": at, "phone": "12"}))
    assert "It's booked" in said(client.post(url, data={"action": "pick", "at": at, "phone": "98765 00021"}))


def test_someone_asks_for_a_call_from_an_email(client, business, run):
    u = business()
    url = path(links.call_url(u.id, u.bot_id, TO))
    page = said(client.get(url))
    assert "Ask Sunrise to call you" in page
    assert "We'll call you" in said(client.post(url, data={"action": "pick", "at": first_time(page)}))

    async def job():
        async with async_session() as db:
            return (await db.execute(select(CallbackJob).where(CallbackJob.bot_id == u.bot_id))).scalars().first()
    j = run(job)
    assert j.e164 == E164 and "email link" in j.consent_source and j.kind == "callback"


def test_when_schedule_is_off_the_pages_say_so_and_the_buttons_stay_out(client, make_user, run):
    u = make_user()
    bot = u.bot("Sunrise")

    async def actions():
        async with async_session() as db:
            return await links.actions_for(db, u.id, bot, TO)
    assert run(actions) == {}
    assert "No times are free" in client.get(path(links.book_url(u.id, bot, TO))).text
    assert "can't book a call" in said(client.get(path(links.call_url(u.id, bot, TO))))


def test_the_buttons_appear_when_the_assistant_takes_bookings(business, run):
    u = business()

    async def actions():
        async with async_session() as db:
            return await links.actions_for(db, u.id, u.bot_id, TO)
    found = run(actions)
    assert "/api/email/p/book?token=" in found["book"] and "/api/email/p/call?token=" in found["call"]


def test_a_confirmed_meetings_email_comes_from_the_design_with_its_buttons_and_invite(client, business, run, sent):
    u = business()
    mid = meeting_for(run, u)
    assert run(meetings._to_person, mid, "confirmed") is None
    m = sent[-1]
    assert m["to"] == TO and "is confirmed for" in m["text"] and m["from_name"] == "Sunrise" and m["reply_to"] == "team@sunrise.in"
    assert "Join the meeting" in m["html"] and "Change the time" in m["html"] and "Cancel" in m["html"] and "Book another time" not in m["html"]
    assert "/api/email/p/meeting?token=" in m["html"] and "https://meet.google.com/abc" in m["html"]
    assert m["attachments"][0]["filename"] == "meeting.ics"


def test_after_a_meeting_a_thank_you_or_sorry_we_missed_you_goes_once(client, business, run, sent):
    u = business()
    mid = meeting_for(run, u)
    run(meetings.after_meeting, mid, True)
    run(meetings.after_meeting, mid, True)
    thanks = [m for m in sent if m["subject"].startswith("Thanks for meeting")]
    assert len(thanks) == 1 and "Change the time" not in thanks[0]["html"]

    u2 = business()
    mid2 = meeting_for(run, u2)
    run(meetings.after_meeting, mid2, False)
    sorry = next(m for m in sent if m["subject"] == "Sorry we missed you")
    assert "Book another time" in sorry["html"] and "/api/email/p/book?token=" in sorry["html"]


def test_the_team_can_turn_those_off(client, business, run, sent):
    u = business()
    client.put(f"/api/email/setup/{u.bot_id}", json={"settings": {"meeting": {"thanks": False}}}, headers=u.h())
    run(meetings.after_meeting, meeting_for(run, u), True)
    assert sent == []
