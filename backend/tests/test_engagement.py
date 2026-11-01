"""What people do with a business's emails: the score, Hot now, the team's alert, the fast call (mail plan, phase 6)."""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.future import select

from backend.models import CallbackJob, Contact, EmailClick, EmailJob, EmailLink, EmailThread, IntegrationSettings, Meeting, ThreadMessage
from database import async_session
from mail import clicks, engagement

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
NOW = datetime(2026, 11, 3, 6, 30)


def test_the_score_follows_the_design():
    now = NOW
    s = lambda *kinds, days=0: engagement.score([(k, now - timedelta(days=days)) for k in kinds], now)
    assert s("reply") > s("book") == s("call") > s("pricing") > s("file") > s("link") > s()
    assert (s("reply"), s("book"), s("pricing"), s("file"), s("link")) == (40, 30, 20, 15, 5)
    assert s("reply", days=10) == 20, "the week before counts half"
    assert s("reply", days=15) == 0, "after two weeks it's gone"
    assert s("reply", "reply", "book", "call", "pricing") == 100, "never over 100"


@pytest.mark.parametrize("kind,label,target,expected", [("book", "Book a time", "https://x.in/book", "book"), ("call", "Call me", "https://x.in/call", "call"),
                                                        ("link", "Our prices", "https://x.in/p", "pricing"), ("link", "See more", "https://x.in/plans", "pricing"),
                                                        ("file", "Price list.pdf", "file:1", "pricing"), ("file", "Brochure.pdf", "file:2", "file"),
                                                        ("link", "Our blog", "https://x.in/blog", "link")])
def test_what_a_link_is(kind, label, target, expected):
    assert engagement.kind_of(EmailLink(kind=kind, label=label, target=target)) == expected


@pytest.fixture(autouse=True)
def _nothing_waiting(run):
    async def go():
        async with async_session() as db:
            await db.execute(update(EmailClick).where(EmailClick.settled_at.is_(None)).values(settled_at=datetime.utcnow()))
            await db.commit()
    run(go)


class Lead:
    def __init__(self, user, run, email="asha@example.com", e164="+919876543210", **contact):
        self.user, self.run = user, run
        self.bot = user.bot()
        self.email = email
        self.contact_id = run(self._seed, email, e164, contact)

    async def _seed(self, email, e164, contact):
        async with async_session() as db:
            db.add(IntegrationSettings(user_id=self.user.id, reply_to="team@example.com"))
            c = Contact(user_id=self.user.id, bot_id=self.bot, e164=e164, name="Asha Rao", email=email, details={}, calls=1, **contact)
            db.add(c)
            await db.commit()
            return c.id

    def email_with(self, *links, sent=None):
        sent = sent or datetime.utcnow() - timedelta(hours=1)
        async def go():
            async with async_session() as db:
                job = EmailJob(user_id=self.user.id, bot_id=self.bot, kind=f"chat_lead#{uuid.uuid4().hex[:6]}", ref_id=uuid.uuid4().hex, to_email=self.email,
                               automation="chat_lead", step=1, subject="Your enquiry", body="x", status="sent", send_at=sent, sent_at=sent)
                db.add(job)
                await db.flush()
                tokens = []
                for kind, label in links:
                    token = uuid.uuid4().hex[:22]
                    db.add(EmailLink(token=token, user_id=self.user.id, job_id=job.id, kind=kind, target=f"https://x.in/{uuid.uuid4().hex[:6]}", label=label, clicks=0))
                    tokens.append(token)
                await db.commit()
                return job, tokens
        return self.run(go)

    def click(self, token, at, agent=CHROME):
        async def go():
            async with async_session() as db:
                clicks.record(db, await db.get(EmailLink, token), f"2001:db8::{uuid.uuid4().hex[:4]}", agent, True, now=at)
                await db.commit()
            return await clicks.settle_due(at + timedelta(minutes=1))
        return self.run(go)

    def contact(self):
        async def go():
            async with async_session() as db:
                return await db.get(Contact, self.contact_id)
        return self.run(go)


@pytest.fixture
def lead(make_user, run, monkeypatch):
    sent = []
    async def team(to, subject, text, owner=None):
        sent.append(subject)
    from notify import events
    monkeypatch.setattr(events, "_email_team", team)
    def made(**k):
        one = Lead(make_user(), run, **k)
        one.alerts = sent
        return one
    return made


def test_a_persons_click_raises_the_score_and_a_scanners_doesnt(lead):
    l = lead()
    job, (price, brochure) = l.email_with(("link", "Our prices"), ("file", "Brochure.pdf"))
    l.click(brochure, datetime.utcnow() - timedelta(minutes=30), agent="python-requests/2.31.0")
    assert not l.contact().engagement
    l.click(price, datetime.utcnow() - timedelta(minutes=20))
    c = l.contact()
    assert c.engagement == 20 and c.engaged_by[0]["what"] == "looked at prices Our prices"


def test_one_link_counts_once_however_often_its_opened(lead):
    l = lead()
    job, (brochure,) = l.email_with(("file", "Brochure.pdf"))
    for minutes in (40, 30, 20):
        l.click(brochure, datetime.utcnow() - timedelta(minutes=minutes))
    assert l.contact().engagement == 15


def test_a_reply_counts_most(lead, run):
    from mail import inbound
    l = lead()
    async def reply():
        async with async_session() as db:
            thread = EmailThread(user_id=l.user.id, bot_id=l.bot, code=uuid.uuid4().hex[:16], email=l.email)
            db.add(thread)
            await db.flush()
            row = ThreadMessage(thread_id=thread.id, user_id=l.user.id, direction="in", who="customer", status="working", sender=l.email, text="Is parking included?")
            db.add(row)
            await db.flush()
            await inbound._their_reply(db, row, thread)
            await db.commit()
    run(reply)
    c = l.contact()
    assert c.engagement == 40 and c.engaged_by[0]["kind"] == "reply"


def test_hot_now_is_the_last_two_days(lead, run):
    l = lead()
    job, (book,) = l.email_with(("book", "Book a time"))
    l.click(book, datetime.utcnow() - timedelta(minutes=5))
    async def hot(now):
        async with async_session() as db:
            return await engagement.hot(db, l.bot, now)
    found = run(hot, datetime.utcnow())
    assert [h["name"] for h in found] == ["Asha Rao"] and found[0]["did"][0]["what"] == "opened Book a time"
    assert run(hot, datetime.utcnow() + timedelta(days=3)) == []


def test_scores_fall_when_people_go_quiet(lead, run):
    l = lead()
    job, (book,) = l.email_with(("book", "Book a time"), sent=datetime.utcnow() - timedelta(days=12))
    l.click(book, datetime.utcnow() - timedelta(days=10))
    assert l.contact().engagement == 30
    run(engagement.decay)
    assert l.contact().engagement == 15
    run(engagement.decay, datetime.utcnow() + timedelta(days=5))
    assert l.contact().engagement == 0


def test_the_team_hears_once_a_day_and_only_about_people(lead):
    l = lead()
    job, (brochure, blog) = l.email_with(("file", "Brochure.pdf"), ("link", "Our blog"))
    l.click(brochure, datetime.utcnow() - timedelta(minutes=30), agent="Mimecast URL Protect")
    assert l.alerts == [], "a scanner's click tells nobody anything"
    l.click(brochure, datetime.utcnow() - timedelta(minutes=20))
    l.click(brochure, datetime.utcnow() - timedelta(minutes=10))
    l.click(blog, datetime.utcnow() - timedelta(minutes=5))
    assert l.alerts == ["Asha Rao just downloaded Brochure.pdf"], "once, and not for a blog post"


def test_the_team_can_turn_the_alert_off(lead, run):
    l = lead()
    async def off():
        async with async_session() as db:
            (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == l.user.id))).scalars().first().alert_engaged = False
            await db.commit()
    run(off)
    job, (book,) = l.email_with(("book", "Book a time"))
    l.click(book, datetime.utcnow() - timedelta(minutes=5))
    assert l.alerts == []


def _fast_call_on(run, l, monkeypatch, on=True):
    from mail import setup
    from voice import schedule
    real = schedule.settings_for
    async def settings(bot_id, db=None):
        s = await real(bot_id, db)
        s["follow_ups"] = {**s["follow_ups"], "enabled": True, "hours": ["00:00", "23:59"], "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
        return s
    monkeypatch.setattr(schedule, "settings_for", settings)
    async def go():
        async with async_session() as db:
            await setup.save_settings(db, l.user.id, l.bot, "fast_call", {"enabled": on})
            await db.commit()
    run(go)


def _calls(run, l):
    async def go():
        async with async_session() as db:
            return (await db.execute(select(CallbackJob).where(CallbackJob.bot_id == l.bot))).scalars().all()
    return run(go)


def test_opening_the_booking_times_without_booking_gets_a_call_ten_minutes_later(lead, run, monkeypatch):
    from voice import schedule
    l = lead()
    _fast_call_on(run, l, monkeypatch)
    job, (book,) = l.email_with(("book", "Book a time"))
    at = datetime.utcnow() - timedelta(minutes=2)
    l.click(book, at)
    calls = _calls(run, l)
    assert len(calls) == 1 and calls[0].kind == "follow_up" and calls[0].variables["from_email"] == "book"
    assert abs((calls[0].next_attempt_at.replace(tzinfo=None) - (at + timedelta(minutes=10))).total_seconds()) < 60
    async def check():
        async with async_session() as db:
            job = await db.get(CallbackJob, calls[0].id)
            first = await schedule.dial_check(db, job)
            db.add(Meeting(user_id=l.user.id, bot_id=l.bot, e164="+919876543210", starts_at=datetime.utcnow() + timedelta(days=2), status="requested"))
            await db.commit()
            return first, await schedule.dial_check(db, job)
    first, after_booking = run(check)
    assert first.stop is None or first.stop[1] == "No active number to call from", first.stop
    assert after_booking.stop[1] == "They have a meeting booked", "booked meanwhile: no call"
    async def finished():
        async with async_session() as db:
            (await db.get(CallbackJob, calls[0].id)).status = "done"
            await db.execute(update(Meeting).where(Meeting.bot_id == l.bot).values(status="cancelled"))
            await db.commit()
    run(finished)
    l.click(book, at + timedelta(minutes=30))
    assert len(_calls(run, l)) == 1, "once a week, even after the first call is over"


def test_the_fast_call_is_off_unless_turned_on(lead, run, monkeypatch):
    l = lead()
    _fast_call_on(run, l, monkeypatch, on=False)
    job, (book,) = l.email_with(("book", "Book a time"))
    l.click(book, datetime.utcnow() - timedelta(minutes=2))
    assert _calls(run, l) == []


def test_the_fast_call_never_rings_someone_on_the_do_not_call_list(lead, run, monkeypatch):
    from backend.models import DncEntry
    l = lead()
    _fast_call_on(run, l, monkeypatch)
    async def dnc():
        async with async_session() as db:
            db.add(DncEntry(user_id=l.user.id, e164="+919876543210"))
            await db.commit()
    run(dnc)
    job, (book,) = l.email_with(("book", "Book a time"))
    l.click(book, datetime.utcnow() - timedelta(minutes=2))
    assert _calls(run, l) == []


def test_turning_the_fast_call_on_needs_pro(client, make_user, monkeypatch):
    import plans
    user = make_user()
    bot = user.bot()
    client.put("/api/email/senders/" + bot, json={"reply_to": "team@example.com"}, headers=user.h())
    async def no_schedule(db, bot_id, feature):
        if feature == "schedule":
            raise plans.upgrade_error("Calls come with the Pro plan")
    monkeypatch.setattr(plans, "require_feature", no_schedule)
    r = client.put(f"/api/email/setup/{bot}", json={"settings": {"fast_call": {"enabled": True}}}, headers=user.h())
    assert r.status_code == 402


def test_call_me_from_an_email_offers_in_about_five_minutes(client, make_user, run, monkeypatch):
    from auth import issue_scoped_token
    from voice import schedule
    real = schedule.settings_for
    async def settings(bot_id, db=None):
        s = await real(bot_id, db)
        s["callbacks"] = {**s["callbacks"], "enabled": True, "hours": ["00:00", "23:59"]}
        return s
    monkeypatch.setattr(schedule, "settings_for", settings)
    booked = []
    async def book(**k):
        booked.append(k)
        return "ok", None
    monkeypatch.setattr(schedule, "book_callback", book)
    monkeypatch.setattr(schedule, "allowed", lambda *a, **k: True)  # whatever the time the tests run
    user = make_user()
    bot = user.bot()
    token = issue_scoped_token(f"{user.id}|{bot}|asha@example.com", "email_call", 3600)
    assert "In about 5 minutes" in client.get(f"/api/email/p/call?token={token}").text
    client.post(f"/api/email/p/call?token={token}", data={"at": "soon", "phone": "9876543210"})
    assert booked and 4 <= (booked[0]["at"] - datetime.now(booked[0]["at"].tzinfo)).total_seconds() / 60 <= 5.1
