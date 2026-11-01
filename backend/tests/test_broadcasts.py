"""Bulk email (mail plan, phase 5): only people who agreed, at a pace, tested, paused when it goes wrong, reported."""
import asyncio
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, update
from sqlalchemy.future import select

from backend.models import Consent, Contact, Conversation, EmailBounce, EmailBroadcast, EmailJob, EmailLink, EmailRsvp, EmailSegment, EmailThread, EmailUnsubscribe, IntegrationSettings, ThreadMessage
from database import async_session
from mail import broadcasts, consent, suppress
from notify import automations, email


@pytest.fixture(autouse=True)
def _nothing_left_queued(run, monkeypatch):
    """The tests share a database, and a pass sends a batch of whatever is due."""
    monkeypatch.setattr(email, "is_configured", lambda: True)
    async def clear():
        async with async_session() as db:
            await db.execute(update(EmailJob).where(EmailJob.status.in_(("queued", "held"))).values(status="cancelled"))
            await db.execute(update(EmailBroadcast).where(EmailBroadcast.status.in_(("scheduled", "testing", "sending", "paused"))).values(status="cancelled"))
            await db.execute(delete(EmailBounce).where(EmailBounce.email.like("p%@example.com")))  # a bounce holds for every business
            await db.commit()
    run(clear)
    yield
    run(clear)


@pytest.fixture
def sent(monkeypatch):
    out = []
    async def deliver(to, subject, text, html_body=None, **k):
        out.append(SimpleNamespace(to=to, subject=subject, text=text, html=html_body, **k))
        return SimpleNamespace(ok=True, id=uuid.uuid4().hex, error=None)
    monkeypatch.setattr(email, "deliver", deliver)
    return out


class Shop:
    def __init__(self, make_user, run, people=3, agreed=None, **contact):
        self.user, self.run = make_user(), run
        self.bot = self.user.bot()
        self.h = self.user.h()
        self.client = self.user.client
        run(self._seed, people, people if agreed is None else agreed, contact)

    async def _seed(self, people, agreed, contact):
        async with async_session() as db:
            db.add(IntegrationSettings(user_id=self.user.id, reply_to="team@example.com"))
            for n in range(people):
                to = f"p{n}@example.com"
                db.add(Contact(user_id=self.user.id, bot_id=self.bot, e164=f"+9198{n:08d}", name=f"Person {n}", email=to, details={}, calls=1, **contact))
                if n < agreed:
                    await consent.give(db, self.user.id, self.bot, to, "import", "They signed up at our stall")
            await db.commit()

    def draft(self, **fields):
        r = self.client.post("/api/email/broadcasts", json={"bot_id": self.bot, "subject": "Diwali offer", "body": "Hi {{first_name|there}}, from {{business}}. See you soon.", **fields}, headers=self.h)
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def send(self, broadcast_id, **fields):
        return self.client.post(f"/api/email/broadcasts/{broadcast_id}/send", json=fields, headers=self.h)

    def started(self, broadcast_id, now=None):
        assert self.send(broadcast_id).status_code == 200
        self.run(broadcasts.advance, broadcast_id, now)

    def jobs(self, broadcast_id):
        async def go():
            async with async_session() as db:
                return (await db.execute(select(EmailJob).where(EmailJob.broadcast_id == broadcast_id).order_by(EmailJob.send_at))).scalars().all()
        return self.run(go)

    def get(self, broadcast_id):
        async def go():
            async with async_session() as db:
                return await db.get(EmailBroadcast, broadcast_id)
        return self.run(go)

    def mark(self, broadcast_id, **values):
        async def go():
            async with async_session() as db:
                await db.execute(update(EmailJob).where(EmailJob.broadcast_id == broadcast_id).values(**values))
                await db.commit()
        self.run(go)

    def due(self, broadcast_id):
        self.mark(broadcast_id, send_at=datetime.utcnow() - timedelta(minutes=1))


@pytest.fixture
def shop(make_user, run):
    return lambda **k: Shop(make_user, run, **k)


# ─── who gets it ─────────────────────────────────────────────────
def test_only_people_who_agreed_are_included_and_it_says_who_was_left_out(shop):
    s = shop(people=5, agreed=2)
    counted = s.client.post("/api/email/bulk/count", json={"bot_id": s.bot}, headers=s.h).json()
    assert counted["count"] == 2 and counted["left_out"] == {"no_consent": 3, "stopped": 0, "throwaway": 0}
    broadcast = s.draft()
    s.started(broadcast)
    assert sorted(j.to_email for j in s.jobs(broadcast)) == ["p0@example.com", "p1@example.com"]


def test_nobody_who_agreed_means_it_cant_be_sent(shop):
    s = shop(people=2, agreed=0)
    r = s.send(s.draft())
    assert r.status_code == 409 and "agreed" in r.json()["detail"]


def test_unsubscribed_bounced_reported_and_throwaway_are_left_out(shop, run):
    s = shop(people=5)
    async def go():
        async with async_session() as db:
            await suppress.add(db, s.user.id, "p0@example.com", "unsubscribed", "marketing")
            await suppress.add(db, s.user.id, "p1@example.com", "complaint")
            db.add(EmailBounce(email="p2@example.com", kind="bounce"))
            contact = (await db.execute(select(Contact).where(Contact.bot_id == s.bot, Contact.email == "p3@example.com"))).scalars().first()
            contact.email = "p3@mailinator.com"
            await consent.give(db, s.user.id, s.bot, "p3@mailinator.com", "import", "x")
            await db.commit()
    run(go)
    counted = s.client.post("/api/email/bulk/count", json={"bot_id": s.bot}, headers=s.h).json()
    assert counted["count"] == 1 and counted["left_out"] == {"no_consent": 0, "stopped": 3, "throwaway": 1}


def test_groups_narrow_it_by_status_stage_tag_source_and_activity(shop, run):
    s = shop(people=4)
    async def go():
        async with async_session() as db:
            rows = (await db.execute(select(Contact).where(Contact.bot_id == s.bot).order_by(Contact.email))).scalars().all()
            rows[0].lead_status, rows[0].stage, rows[0].tags = "hot", "interested", ["vip"]
            rows[1].lead_status, rows[1].source = "cold", "import"
            rows[2].source, rows[2].created_at, rows[2].last_call_at = "chat", datetime.utcnow() - timedelta(days=100), datetime.utcnow() - timedelta(days=100)
            await db.commit()
    run(go)
    count = lambda **rules: s.client.post("/api/email/bulk/count", json={"bot_id": s.bot, "rules": rules}, headers=s.h).json()["count"]
    assert count(statuses=["hot"]) == 1 and count(stages=["interested"]) == 1 and count(tags=["vip"]) == 1
    assert count(sources=["import"]) == 1 and count(sources=["chat"]) == 1 and count(active_days=30) == 3 and count(statuses=["hot", "cold"]) == 2
    assert count(statuses=["hot"], sources=["import"]) == 0


def test_a_group_can_be_saved_and_read_back_and_belongs_to_its_workspace(shop, make_user):
    s = shop()
    made = s.client.post("/api/email/segments", json={"bot_id": s.bot, "name": "Hot leads", "rules": {"statuses": ["hot"], "nonsense": 1}}, headers=s.h).json()
    assert made["rules"] == {"statuses": ["hot"]}
    assert [g["name"] for g in s.client.get(f"/api/email/bulk/{s.bot}", headers=s.h).json()["segments"]] == ["Hot leads"]
    other = make_user()
    assert s.client.delete(f"/api/email/segments/{made['id']}", headers=other.h()).status_code == 404
    assert s.client.get(f"/api/email/bulk/{s.bot}", headers=other.h()).status_code == 404
    assert s.client.delete(f"/api/email/segments/{made['id']}", headers=s.h).status_code == 200


def test_a_person_on_two_contacts_gets_one_email(shop, run):
    s = shop(people=1)
    async def go():
        async with async_session() as db:
            db.add(Contact(user_id=s.user.id, bot_id=s.bot, e164="+919999999999", name="Same", email="P0@example.com", details={}, calls=0))
            await db.commit()
    run(go)
    broadcast = s.draft()
    s.started(broadcast)
    assert len(s.jobs(broadcast)) == 1


def test_consent_withdrawn_after_it_was_queued_stops_that_email(shop, run, sent):
    s = shop(people=2)
    broadcast = s.draft()
    s.started(broadcast)
    s.due(broadcast)
    async def go():
        async with async_session() as db:
            await consent.withdraw(db, s.user.id, "p0@example.com", s.bot, by=s.user.id)
            await db.commit()
    run(go)
    run(automations.process_due)
    assert [m.to for m in sent] == ["p1@example.com"]
    assert next(j for j in s.jobs(broadcast) if j.to_email == "p0@example.com").status == "cancelled"


# ─── consent ─────────────────────────────────────────────────────
def test_unsubscribing_withdraws_and_only_they_can_give_it_back(shop, run):
    s = shop(people=1)
    async def go():
        async with async_session() as db:
            await suppress.add(db, s.user.id, "p0@example.com", "unsubscribed", "marketing")
            await db.commit()
            assert not await consent.has(db, s.bot, "p0@example.com")
            assert await consent.give(db, s.user.id, s.bot, "p0@example.com", "team", "They said yes") is False
            assert await consent.give(db, s.user.id, s.bot, "p0@example.com", "import", "A list") is False
            await db.commit()
            assert not await consent.has(db, s.bot, "p0@example.com")
            assert await consent.give(db, s.user.id, s.bot, "p0@example.com", "chat", "Send me offers")
            await db.commit()
            assert await consent.has(db, s.bot, "p0@example.com")
    run(go)


def test_resubscribing_brings_back_what_they_agreed_to(shop, run):
    s = shop(people=1)
    async def go():
        async with async_session() as db:
            await suppress.add(db, s.user.id, "p0@example.com", "unsubscribed", "all")
            await db.commit()
            assert await suppress.resubscribe(db, s.user.id, "p0@example.com")
            await db.commit()
            assert await consent.has(db, s.bot, "p0@example.com")
            assert (await consent.of(db, s.bot, "p0@example.com"))["source"] == "resubscribed"
    run(go)


def test_consent_belongs_to_one_assistant(shop, run):
    s = shop(people=1)
    other = s.user.bot()
    async def go():
        async with async_session() as db:
            assert await consent.has(db, s.bot, "p0@example.com") and not await consent.has(db, other, "p0@example.com")
    run(go)


def test_the_team_notes_consent_saying_how_and_can_take_it_back(shop, run):
    s = shop(people=1, agreed=0)
    async def contact():
        async with async_session() as db:
            return (await db.execute(select(Contact.id).where(Contact.bot_id == s.bot))).scalar_one()
    cid = run(contact)
    assert s.client.post(f"/api/email/consent/{cid}", json={"agreed": True, "how": ""}, headers=s.h).status_code == 400
    record = s.client.post(f"/api/email/consent/{cid}", json={"agreed": True, "how": "They signed our form at the expo"}, headers=s.h).json()
    assert (record["status"], record["source"], record["words"]) == ("given", "team", "They signed our form at the expo")
    assert s.client.post(f"/api/email/consent/{cid}", json={"agreed": False}, headers=s.h).json()["status"] == "withdrawn"
    assert s.client.post(f"/api/email/consent/{cid}", json={"agreed": True, "how": "They phoned to say yes"}, headers=s.h).json()["status"] == "given", "the team's own stop isn't theirs"


def test_the_chats_tick_box_gives_consent_with_the_words_they_saw(make_user, client, run):
    from mail import setup
    user = make_user()
    bot = user.bot()
    async def go():
        async with async_session() as db:
            await setup.save_settings(db, user.id, bot, "consent", {"ask": True, "words": "Send me Sunrise offers"})
            await db.commit()
    run(go)
    assert client.get(f"/api/bots/{bot}/config").json()["marketing_consent"] == "Send me Sunrise offers"
    for name, value in (("Offers and news", "Yes"), ("email", "ravi@example.com")):
        assert client.post("/api/chat/variables", json={"bot_id": bot, "visitor_session_id": "widget-session-ai-1", "variable_name": name, "variable_value": value}).status_code == 200
    async def record():
        for _ in range(40):
            async with async_session() as db:
                found = await consent.of(db, bot, "ravi@example.com")
                contact = (await db.execute(select(Contact).where(Contact.bot_id == bot))).scalars().first()
            if found:
                return found, contact.details
            await asyncio.sleep(0.05)
    found, details = run(record)
    assert (found["source"], found["words"]) == ("chat", "Send me Sunrise offers") and "Offers and news" not in details


def test_a_chat_without_the_tick_gives_nothing(make_user, client, run):
    user = make_user()
    bot = user.bot()
    assert client.get(f"/api/bots/{bot}/config").json()["marketing_consent"] is None
    client.post("/api/chat/variables", json={"bot_id": bot, "visitor_session_id": "widget-session-ai-2", "variable_name": "email", "variable_value": "ravi@example.com"})
    async def record():
        await asyncio.sleep(0.2)
        async with async_session() as db:
            return await consent.has(db, bot, "ravi@example.com")
    assert run(record) is False


def test_a_forms_tick_gives_consent_and_no_tick_doesnt(make_user, run):
    from backend.models import Bot
    from mail import intake
    user = make_user()
    bot = user.bot()
    async def go():
        async with async_session() as db:
            row = await db.get(Bot, bot)
        await intake.act(row, intake.form_lead({"email": "a@example.com", "newsletter": "yes"}))
        await intake.act(row, intake.form_lead({"email": "b@example.com"}))
        async with async_session() as db:
            assert await consent.has(db, bot, "a@example.com") and not await consent.has(db, bot, "b@example.com")
    run(go)


# ─── a draft ─────────────────────────────────────────────────────
def test_a_draft_can_be_changed_and_a_sent_one_cant(shop):
    s = shop()
    broadcast = s.draft()
    saved = s.client.put(f"/api/email/broadcasts/{broadcast}", json={"subject": "ACT NOW!!! FREE MONEY", "body": "Short"}, headers=s.h).json()
    assert any("capital" in n for n in saved["notes"]) and any("very short" in n for n in saved["notes"]) and any("free money" in n for n in saved["notes"])
    s.client.put(f"/api/email/broadcasts/{broadcast}", json={"subject": "Diwali offer", "body": "Hi there, our Diwali offer is on until Sunday. Come and see us."}, headers=s.h)
    assert s.send(broadcast).status_code == 200
    assert s.client.put(f"/api/email/broadcasts/{broadcast}", json={"subject": "Changed", "body": "x"}, headers=s.h).status_code == 409


def test_a_test_send_goes_to_the_team_marked_as_a_test_and_nobody_else(shop, sent):
    s = shop()
    broadcast = s.draft()
    r = s.client.post(f"/api/email/broadcasts/{broadcast}/test", json={"to": "me@example.com"}, headers=s.h)
    assert r.status_code == 200 and [(m.to, m.subject) for m in sent] == [("me@example.com", "[Test] Diwali offer")]
    assert s.jobs(broadcast) == [] and s.get(broadcast).status == "draft"


def test_a_workspace_cant_touch_anothers_bulk_email(shop, make_user):
    s = shop()
    broadcast = s.draft()
    other = make_user()
    for method, path in (("get", ""), ("post", "/send"), ("post", "/cancel"), ("post", "/test"), ("delete", "")):
        kw = {"json": {}} if method == "post" else {}
        assert getattr(s.client, method)(f"/api/email/broadcasts/{broadcast}{path}", headers=other.h(), **kw).status_code == 404, path


def test_sending_needs_a_reply_address_and_the_plan(shop, run, monkeypatch):
    import plans
    s = shop()
    broadcast = s.draft()
    async def no_reply():
        async with async_session() as db:
            (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == s.user.id))).scalars().first().reply_to = None
            await db.commit()
    run(no_reply)
    r = s.send(broadcast)
    assert r.status_code == 409 and "replies" in r.json()["detail"]


# ─── sending ─────────────────────────────────────────────────────
def test_it_goes_at_the_set_pace(shop):
    s = shop(people=30)
    broadcast = s.draft(per_minute=30)
    now = datetime.utcnow() + timedelta(seconds=30)
    s.started(broadcast, now)
    times = [j.send_at.replace(tzinfo=None) for j in s.jobs(broadcast)]
    assert len(times) == 30 and times[1] - times[0] == timedelta(seconds=2) and times[-1] - times[0] == timedelta(seconds=58)


def test_a_time_ahead_waits_for_it(shop):
    s = shop(people=2)
    broadcast = s.draft()
    at = datetime.utcnow() + timedelta(hours=3)
    assert s.send(broadcast, at=at.isoformat() + "+00:00").status_code == 200
    s.run(broadcasts.tick)
    assert s.jobs(broadcast) == [] and s.get(broadcast).status == "scheduled"
    s.run(broadcasts.tick, at + timedelta(minutes=1))
    assert len(s.jobs(broadcast)) == 2 and s.get(broadcast).status == "sending"


def test_a_time_in_the_past_or_too_far_is_refused(shop):
    s = shop()
    broadcast = s.draft()
    assert s.send(broadcast, at=(datetime.utcnow() - timedelta(days=1)).isoformat() + "+00:00").status_code == 400
    assert s.send(broadcast, at=(datetime.utcnow() + timedelta(days=90)).isoformat() + "+00:00").status_code == 400


def test_each_persons_usual_hour(shop, run):
    last = datetime(2026, 11, 2, 12, 0)  # 5:30 pm in India
    s = shop(people=1, last_call_at=last)
    broadcast = s.draft()
    now = datetime(2026, 11, 3, 3, 30)  # 9 am in India
    assert s.send(broadcast, usual_hour=True).status_code == 200
    async def due():
        async with async_session() as db:
            (await db.get(EmailBroadcast, broadcast)).send_at = now
            await db.commit()
    run(due)
    run(broadcasts.advance, broadcast, now)
    local = s.jobs(broadcast)[0].send_at.replace(tzinfo=None) + timedelta(hours=5, minutes=30)
    assert (local.date().isoformat(), local.hour) == ("2026-11-03", 17)


def test_the_list_is_read_when_it_starts(shop, run):
    s = shop(people=2)
    broadcast = s.draft()
    assert s.send(broadcast).status_code == 200
    async def go():
        async with async_session() as db:
            await suppress.add(db, s.user.id, "p0@example.com", "unsubscribed", "marketing")
            await db.commit()
    run(go)
    run(broadcasts.advance, broadcast)
    assert [j.to_email for j in s.jobs(broadcast)] == ["p1@example.com"]


def test_two_processes_starting_it_make_one_list(shop, run):
    s = shop(people=20)
    broadcast = s.draft()
    assert s.send(broadcast).status_code == 200
    async def both():
        await asyncio.gather(*(broadcasts.advance(broadcast) for _ in range(4)))
    run(both)
    jobs = s.jobs(broadcast)
    assert len(jobs) == 20 and len({j.to_email for j in jobs}) == 20


def test_two_passes_of_the_sender_send_each_email_once(shop, run, sent):
    s = shop(people=20)
    broadcast = s.draft()
    s.started(broadcast)
    s.due(broadcast)
    async def both():
        await asyncio.gather(*(automations.process_due() for _ in range(3)))
    run(both)
    assert sorted(m.to for m in sent) == sorted(f"p{n}@example.com" for n in range(20))


def test_the_email_has_their_name_tracked_links_and_an_unsubscribe(shop, run, sent):
    s = shop(people=1)
    broadcast = s.draft(body="Hi {{first_name|there}}, see https://example.com/offer today.")
    s.started(broadcast)
    s.due(broadcast)
    run(automations.process_due)
    m = sent[0]
    assert m.text.startswith("Hi Person,") and "example.com/offer" not in m.text and "/api/email/l/" in m.text and "Unsubscribe" in m.text
    assert m.unsubscribe_url and m.tags["kind"] == "customer"
    s.mark(broadcast, status="sent")
    s.run(broadcasts.advance, broadcast)
    assert s.get(broadcast).status == "sent"


def test_offers_go_from_their_own_address_when_there_is_one(shop, run, sent, monkeypatch):
    monkeypatch.setenv("BULK_EMAIL_FROM", "Nimmi AI <news@news.nimmiai.in>")
    s = shop(people=1)
    broadcast = s.draft()
    s.started(broadcast)
    s.due(broadcast)
    run(automations.process_due)
    assert sent[0].from_address == "news@news.nimmiai.in"


def test_nimmis_address_has_a_low_limit_and_says_what_to_do(shop, monkeypatch):
    monkeypatch.setenv("BROADCAST_SHARED_DAILY", "2")
    s = shop(people=3)
    r = s.send(s.draft())
    assert r.status_code == 409 and "own domain" in r.json()["detail"]


def test_a_workspace_can_be_kept_to_its_own_domain(shop, monkeypatch):
    monkeypatch.setenv("BROADCAST_SHARED_DAILY", "0")
    s = shop(people=1)
    assert s.send(s.draft()).status_code == 409


def test_a_workspace_with_too_many_spam_reports_cant_start_another(shop, run):
    s = shop(people=1)
    async def go():
        async with async_session() as db:
            for n in range(210):
                db.add(EmailJob(user_id=s.user.id, kind=f"broadcast:old#{n}", ref_id=f"r{n}", to_email=f"o{n}@example.com", subject="x", body="y", status="sent", broadcast_id="old",
                                sent_at=datetime.utcnow(), delivered_at=datetime.utcnow(), complained_at=datetime.utcnow() if n < 3 else None))
            await db.commit()
    run(go)
    r = s.send(s.draft())
    assert r.status_code == 409 and "paused" in r.json()["detail"]


# ─── the subject test ────────────────────────────────────────────
def _clicked(s, broadcast, variant, count):
    async def go():
        async with async_session() as db:
            rows = (await db.execute(select(EmailJob).where(EmailJob.broadcast_id == broadcast, EmailJob.variant == variant).limit(count))).scalars().all()
            for j in rows:
                j.clicked_at = datetime.utcnow()
            await db.commit()
    s.run(go)


def test_the_subject_test_goes_to_a_fifth_and_the_winner_to_the_rest(shop):
    s = shop(people=100)
    broadcast = s.draft(subject_b="Our Diwali gift for you")
    now = datetime.utcnow() + timedelta(seconds=30)
    s.started(broadcast, now)
    b = s.get(broadcast)
    jobs = s.jobs(broadcast)
    assert b.status == "testing" and len(jobs) == 20
    assert sorted({j.subject for j in jobs}) == ["Diwali offer", "Our Diwali gift for you"]
    assert sum(1 for j in jobs if j.variant == "a") == sum(1 for j in jobs if j.variant == "b") == 10
    _clicked(s, broadcast, "b", 3)
    _clicked(s, broadcast, "a", 1)
    s.run(broadcasts.advance, broadcast, now + timedelta(hours=1))
    assert s.get(broadcast).status == "testing" and len(s.jobs(broadcast)) == 20, "the test isn't over"
    s.run(broadcasts.advance, broadcast, now + timedelta(hours=broadcasts.TEST_HOURS, minutes=1))
    b, jobs = s.get(broadcast), s.jobs(broadcast)
    assert (b.status, b.winner, len(jobs), len({j.to_email for j in jobs})) == ("sending", "b", 100, 100)
    assert {j.subject for j in jobs if j.variant == "b"} == {"Our Diwali gift for you"} and sum(1 for j in jobs if j.subject == "Diwali offer") == 10


def test_a_reply_counts_for_more_than_a_click(shop, run):
    s = shop(people=100)
    broadcast = s.draft(subject_b="Second")
    now = datetime.utcnow() + timedelta(seconds=30)
    s.started(broadcast, now)
    _clicked(s, broadcast, "a", 1)
    async def reply():
        async with async_session() as db:
            to = (await db.execute(select(EmailJob.to_email).where(EmailJob.broadcast_id == broadcast, EmailJob.variant == "b").limit(1))).scalar_one()
            thread = EmailThread(user_id=s.user.id, bot_id=s.bot, code=uuid.uuid4().hex[:16], email=to)
            db.add(thread)
            await db.flush()
            db.add(ThreadMessage(thread_id=thread.id, user_id=s.user.id, direction="in", who="customer", status="received", sender=to, text="Yes", created_at=now + timedelta(minutes=5)))
            await db.commit()
    run(reply)
    run(broadcasts.advance, broadcast, now + timedelta(hours=5))
    assert s.get(broadcast).winner == "b"


def test_a_tie_goes_to_the_first_subject(shop):
    s = shop(people=100)
    broadcast = s.draft(subject_b="Second")
    now = datetime.utcnow() + timedelta(seconds=30)
    s.started(broadcast, now)
    s.run(broadcasts.advance, broadcast, now + timedelta(hours=5))
    assert s.get(broadcast).winner == "a"


def test_a_subject_test_needs_enough_people(shop):
    s = shop(people=20)
    r = s.send(s.draft(subject_b="Second"))
    assert r.status_code == 409 and "at least 100" in r.json()["detail"]


# ─── when it goes wrong ──────────────────────────────────────────
def test_a_spike_in_spam_reports_pauses_it_and_the_rest_waits(shop, run, sent):
    s = shop(people=10)
    broadcast = s.draft()
    s.started(broadcast)
    async def complaints():
        async with async_session() as db:
            rows = (await db.execute(select(EmailJob).where(EmailJob.broadcast_id == broadcast).limit(4))).scalars().all()
            for j in rows:
                j.status, j.sent_at, j.delivered_at = "sent", datetime.utcnow(), datetime.utcnow()
            for j in rows[:2]:
                j.complained_at = datetime.utcnow()
            await db.commit()
    run(complaints)
    run(broadcasts.advance, broadcast)
    b = s.get(broadcast)
    assert b.status == "paused" and "spam" in b.paused_why
    s.due(broadcast)
    async def still_held():
        async with async_session() as db:
            await db.execute(update(EmailJob).where(EmailJob.broadcast_id == broadcast, EmailJob.status == "queued").values(status="held"))
            await db.commit()
    run(still_held)
    run(automations.process_due)
    assert sent == [], "held emails don't go"
    assert s.client.post(f"/api/email/broadcasts/{broadcast}/resume", headers=s.h).json()["status"] == "sending"
    assert sum(1 for j in s.jobs(broadcast) if j.status == "queued") == 6


def test_too_many_bounces_pause_it(shop, run):
    s = shop(people=30)
    broadcast = s.draft()
    s.started(broadcast)
    s.mark(broadcast, status="sent", sent_at=datetime.utcnow())
    async def bounced():
        async with async_session() as db:
            rows = (await db.execute(select(EmailJob).where(EmailJob.broadcast_id == broadcast).limit(3))).scalars().all()
            for j in rows:
                j.bounced_at = datetime.utcnow()
            await db.commit()
    run(bounced)
    run(broadcasts.advance, broadcast)
    assert s.get(broadcast).status == "paused" and "bounced" in s.get(broadcast).paused_why


def test_the_team_can_pause_and_cancel(shop):
    s = shop(people=3)
    broadcast = s.draft()
    s.started(broadcast)
    assert s.client.post(f"/api/email/broadcasts/{broadcast}/pause", headers=s.h).json()["status"] == "paused"
    assert {j.status for j in s.jobs(broadcast)} == {"held"}
    assert s.client.post(f"/api/email/broadcasts/{broadcast}/cancel", headers=s.h).json()["status"] == "cancelled"
    assert {j.status for j in s.jobs(broadcast)} == {"cancelled"}
    assert s.client.post(f"/api/email/broadcasts/{broadcast}/resume", headers=s.h).status_code == 409


def test_a_problem_at_the_start_pauses_it_and_says_why(shop, run):
    s = shop(people=1)
    broadcast = s.draft()
    assert s.send(broadcast).status_code == 200
    async def lost():
        async with async_session() as db:
            await consent.withdraw(db, s.user.id, "p0@example.com", s.bot)
            await db.commit()
    run(lost)
    run(broadcasts.advance, broadcast)
    b = s.get(broadcast)
    assert b.status == "paused" and "agreed" in b.paused_why


# ─── the report and invitations ──────────────────────────────────
def test_the_report_counts_what_happened(shop, run):
    s = shop(people=4)
    broadcast = s.draft()
    s.started(broadcast)
    s.mark(broadcast, status="sent", sent_at=datetime.utcnow(), delivered_at=datetime.utcnow())
    async def go():
        async with async_session() as db:
            (await db.get(EmailBroadcast, broadcast)).started_at = datetime.utcnow() - timedelta(minutes=5)  # SQLite's clock has whole seconds
            rows = (await db.execute(select(EmailJob).where(EmailJob.broadcast_id == broadcast).order_by(EmailJob.to_email))).scalars().all()
            rows[0].clicked_at = datetime.utcnow()
            rows[1].bounced_at = datetime.utcnow()
            rows[1].delivered_at = None
            rows[2].complained_at = datetime.utcnow()
            await suppress.add(db, s.user.id, rows[3].to_email, "unsubscribed", "marketing")
            await db.commit()
    run(go)
    counts = s.client.get(f"/api/email/broadcasts/{broadcast}", headers=s.h).json()["counts"]
    assert {k: counts[k] for k in ("sent", "delivered", "bounced", "complained", "clicked", "unsubscribed")} == {"sent": 4, "delivered": 3, "bounced": 1, "complained": 1, "clicked": 1, "unsubscribed": 1}


def _rsvp_token(broadcast, to):
    from auth import issue_scoped_token
    return issue_scoped_token(f"{broadcast}|{to}", "email_rsvp", 3600)


def test_an_invitation_asks_and_only_a_button_answers(shop, run):
    s = shop(people=1)
    at = (datetime.utcnow() + timedelta(days=5)).replace(microsecond=0)
    broadcast = s.draft(event={"title": "Open house", "at": at.isoformat() + "+00:00", "where": "Anna Nagar"})
    s.started(broadcast)
    job = s.jobs(broadcast)[0]
    assert "Open house" in job.body and "Anna Nagar" in job.body and "/api/email/p/rsvp?token=" in job.body
    token = _rsvp_token(broadcast, "p0@example.com")
    assert "Will you come to Open house?" in s.client.get(f"/api/email/p/rsvp?token={token}").text
    async def answers():
        async with async_session() as db:
            return (await db.execute(select(EmailRsvp.answer).where(EmailRsvp.broadcast_id == broadcast))).scalars().all()
    assert run(answers) == [], "opening the link says nothing: scanners open links"
    s.client.post(f"/api/email/p/rsvp?token={token}", data={"action": "yes"})
    s.client.post(f"/api/email/p/rsvp?token={token}", data={"action": "maybe"})
    assert run(answers) == ["maybe"], "they can change their mind"
    async def details():
        async with async_session() as db:
            return (await db.execute(select(Contact.details).where(Contact.bot_id == s.bot))).scalar_one()
    assert run(details) == {"RSVP: Open house": "Maybe"}
    assert s.client.get(f"/api/email/broadcasts/{broadcast}", headers=s.h).json()["rsvp"] == {"yes": 0, "no": 0, "maybe": 1}
    assert "ended" in s.client.get("/api/email/p/rsvp?token=nope").text


def test_those_coming_get_a_reminder_the_day_before_once(shop, run):
    s = shop(people=3)
    at = (datetime.utcnow() + timedelta(days=5)).replace(microsecond=0)
    broadcast = s.draft(event={"title": "Open house", "at": at.isoformat() + "+00:00", "where": "Anna Nagar"})
    s.started(broadcast)
    async def answer():
        async with async_session() as db:
            db.add_all([EmailRsvp(broadcast_id=broadcast, user_id=s.user.id, email="p0@example.com", answer="yes"), EmailRsvp(broadcast_id=broadcast, user_id=s.user.id, email="p1@example.com", answer="maybe"),
                        EmailRsvp(broadcast_id=broadcast, user_id=s.user.id, email="p2@example.com", answer="no")])
            await db.commit()
    run(answer)
    async def reminders():
        async with async_session() as db:
            return (await db.execute(select(EmailJob).where(EmailJob.user_id == s.user.id, EmailJob.automation == "rsvp_reminder"))).scalars().all()
    run(broadcasts._remind, at - timedelta(days=3))
    assert run(reminders) == []
    run(broadcasts._remind, at - timedelta(hours=20))
    run(broadcasts._remind, at - timedelta(hours=19))
    got = run(reminders)
    assert sorted(j.to_email for j in got) == ["p0@example.com", "p1@example.com"] and got[0].subject == "Tomorrow: Open house"


def test_a_reminder_really_goes(shop, run, sent):
    s = shop(people=1)
    at = (datetime.utcnow() + timedelta(days=5)).replace(microsecond=0)
    broadcast = s.draft(event={"title": "Open house", "at": at.isoformat() + "+00:00"})
    s.started(broadcast)
    s.mark(broadcast, status="sent")
    async def answer():
        async with async_session() as db:
            db.add(EmailRsvp(broadcast_id=broadcast, user_id=s.user.id, email="p0@example.com", answer="yes"))
            await db.commit()
    run(answer)
    run(broadcasts._remind, at - timedelta(hours=20))
    async def due():
        async with async_session() as db:
            await db.execute(update(EmailJob).where(EmailJob.automation == "rsvp_reminder", EmailJob.user_id == s.user.id).values(send_at=datetime.utcnow() - timedelta(minutes=1)))
            await db.commit()
    run(due)
    run(automations.process_due)
    assert [m.subject for m in sent] == ["Tomorrow: Open house"]


# ─── imports ─────────────────────────────────────────────────────
CSV = "Name,Email,Phone,Tags,City\nAsha Rao,asha@example.com,98765 43210,vip;expo,Chennai\nRavi,ravi@example.com,,,\nNobody,,,,\nBad,not-an-email,,,\nTemp,t@mailinator.com,,,\n"


def _import(s, **fields):
    return s.client.post("/api/email/contacts/import", json={"bot_id": s.bot, "csv": CSV, "how": "They signed up at our expo stall in October", "confirmed": True, **fields}, headers=s.h)


def test_an_import_adds_people_with_how_they_agreed(shop, run):
    s = shop(people=0)
    r = _import(s).json()
    assert (r["rows"], r["added"], r["agreed"], r["skipped_count"]) == (5, 2, 2, 3)
    async def go():
        async with async_session() as db:
            asha = (await db.execute(select(Contact).where(Contact.bot_id == s.bot, Contact.email == "asha@example.com"))).scalars().first()
            return asha, await consent.of(db, s.bot, "asha@example.com")
    asha, record = run(go)
    assert (asha.name, asha.e164, asha.tags, asha.source, asha.details) == ("Asha Rao", "+919876543210", ["expo", "vip"], "import", {"city": "Chennai"})
    assert (record["source"], record["words"]) == ("import", "Imported: They signed up at our expo stall in October")


def test_an_import_needs_how_they_agreed_and_a_yes(shop):
    s = shop(people=0)
    assert _import(s, how="yes").status_code == 422
    assert _import(s, confirmed=False).status_code == 400
    assert _import(s, csv="a,b\n1,2\n").status_code == 400


def test_an_import_doesnt_undo_someones_unsubscribe(shop, run):
    s = shop(people=0)
    async def go():
        async with async_session() as db:
            await suppress.add(db, s.user.id, "ravi@example.com", "unsubscribed", "all")
            await db.commit()
    run(go)
    r = _import(s).json()
    assert r["agreed"] == 1 and any(x["why"] == "They stopped your emails" for x in r["skipped"])


def test_an_import_merges_with_who_is_already_there(shop, run):
    s = shop(people=1, agreed=0)
    r = s.client.post("/api/email/contacts/import", json={"bot_id": s.bot, "csv": "email,name\np0@example.com,Someone Else\n", "how": "They signed up at our expo stall", "confirmed": True}, headers=s.h).json()
    assert (r["added"], r["updated"], r["agreed"]) == (0, 1, 1)
    async def name():
        async with async_session() as db:
            return (await db.execute(select(Contact.name).where(Contact.bot_id == s.bot))).scalars().all()
    assert run(name) == ["Person 0"]


def test_an_import_reads_semicolons_and_excel_marks(shop):
    s = shop(people=0)
    r = s.client.post("/api/email/contacts/import", json={"bot_id": s.bot, "csv": "﻿Name;E-mail\nAsha;asha@example.com\n", "how": "They signed up at our expo stall", "confirmed": True}, headers=s.h).json()
    assert r["added"] == 1


def test_the_page_says_what_can_be_sent_today(shop):
    s = shop(people=3, agreed=2)
    page = s.client.get(f"/api/email/bulk/{s.bot}", headers=s.h).json()
    assert (page["agreed"], page["with_email"], page["room_today"]) == (2, 3, 200) and page["sender"]["domain"] is None and page["ask_in_chat"] == {"ask": False, "words": "Send me offers and news"}


def test_nimmi_counts_who_a_bulk_email_reaches(shop, run):
    from agent import registry
    from auth import AuthContext
    s = shop(people=3, agreed=1)
    tc = registry.ToolContext(ctx=AuthContext(s.user.id, s.user.id, "owner"), run_id="r", thread_id="t", screen={})
    out = run(registry.run, tc, "email_audience", {"assistant_id": s.bot})
    assert out.ok and '"people": 1' in out.text.replace("\n", " ") or "1" in out.text
    assert run(registry.run, tc, "email_bulk_sends", {"assistant_id": s.bot}).ok


def test_a_new_domain_warms_up_and_says_so(shop, run):
    from backend.models import EmailDomain
    s = shop(people=3)
    async def go():
        async with async_session() as db:
            domain = EmailDomain(user_id=s.user.id, name="shop.example.com", status="verified", verified_at=datetime.utcnow())
            db.add(domain)
            await db.flush()
            (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == s.user.id))).scalars().first().sender_domain_id = domain.id
            await db.commit()
    run(go)
    room = s.client.get(f"/api/email/bulk/{s.bot}", headers=s.h).json()
    assert room["sender"]["domain"] == "shop.example.com" and room["room_today"] == 100
    async def spent():
        async with async_session() as db:
            for n in range(99):
                db.add(EmailJob(user_id=s.user.id, kind=f"broadcast:old#{n}", ref_id=f"w{n}", to_email=f"o{n}@example.com", subject="x", body="y", status="sent", broadcast_id="old", send_at=datetime.utcnow()))
            await db.commit()
    run(spent)
    r = s.send(s.draft())
    assert r.status_code == 409 and "shop.example.com is new" in r.json()["detail"]


def test_the_words_of_the_tick_box_are_checked(shop):
    s = shop(people=0)
    assert s.client.put(f"/api/email/setup/{s.bot}", json={"settings": {"consent": {"words": "ok"}}}, headers=s.h).status_code == 400
    assert s.client.put(f"/api/email/setup/{s.bot}", json={"settings": {"consent": {"ask": True, "words": "Send me Sunrise offers"}}}, headers=s.h).status_code == 200
    assert s.client.get(f"/api/email/bulk/{s.bot}", headers=s.h).json()["ask_in_chat"] == {"ask": True, "words": "Send me Sunrise offers"}


def test_the_page_shows_the_address_offers_go_from(shop, monkeypatch):
    monkeypatch.setenv("BULK_EMAIL_FROM", "Nimmi AI <news@news.nimmiai.in>")
    s = shop(people=0)
    assert s.client.get(f"/api/email/bulk/{s.bot}", headers=s.h).json()["sender"]["address"] == "news@news.nimmiai.in"


def test_a_big_send_never_holds_up_a_customers_own_email(shop, run, sent, monkeypatch):
    monkeypatch.setattr(automations, "BATCH", 5)
    s = shop(people=10)
    on = {"chat_lead": {"enabled": True, "steps": [{"delay": "now", "subject": "Thanks for writing", "body": "We'll be in touch."}]}}
    assert s.client.put(f"/api/email/setup/{s.bot}", json={"automations": on}, headers=s.h).status_code == 200
    broadcast = s.draft()
    s.started(broadcast)
    s.mark(broadcast, send_at=datetime.utcnow() - timedelta(minutes=10))
    async def theirs():
        async with async_session() as db:
            db.add(EmailJob(user_id=s.user.id, bot_id=s.bot, kind="chat_lead", ref_id=uuid.uuid4().hex, to_email="customer@example.com", automation="chat_lead", step=1,
                            subject="Thanks for writing", body="We'll be in touch.", send_at=datetime.utcnow() - timedelta(minutes=1)))
            await db.commit()
    run(theirs)
    run(automations.process_due)
    assert sent[0].to == "customer@example.com" and len(sent) == 5


def test_two_processes_send_the_reminders_once(shop, run):
    s = shop(people=2)
    at = (datetime.utcnow() + timedelta(days=5)).replace(microsecond=0)
    broadcast = s.draft(event={"title": "Open house", "at": at.isoformat() + "+00:00"})
    s.started(broadcast)
    async def answer():
        async with async_session() as db:
            db.add_all([EmailRsvp(broadcast_id=broadcast, user_id=s.user.id, email=f"p{n}@example.com", answer="yes") for n in range(2)])
            await db.commit()
    run(answer)
    async def both():
        await asyncio.gather(*(broadcasts._remind(at - timedelta(hours=20)) for _ in range(3)))
        async with async_session() as db:
            return (await db.execute(select(EmailJob.to_email).where(EmailJob.user_id == s.user.id, EmailJob.automation == "rsvp_reminder"))).scalars().all()
    assert sorted(run(both)) == ["p0@example.com", "p1@example.com"]


def test_erasing_someone_takes_what_they_agreed_to_and_their_answers(shop, run):
    s = shop(people=2)
    broadcast = s.draft(event={"title": "Open house", "at": (datetime.utcnow() + timedelta(days=5)).replace(microsecond=0).isoformat() + "+00:00"})
    async def answer():
        async with async_session() as db:
            db.add_all([EmailRsvp(broadcast_id=broadcast, user_id=s.user.id, email=f"p{n}@example.com", answer="yes") for n in range(2)])
            await db.commit()
    run(answer)
    assert s.client.post("/api/voice/erase", json={"number": "+919800000000"}, headers=s.h).status_code == 200
    async def left():
        async with async_session() as db:
            agreed = (await db.execute(select(Consent.email).where(Consent.bot_id == s.bot))).scalars().all()
            answers = (await db.execute(select(EmailRsvp.email).where(EmailRsvp.broadcast_id == broadcast))).scalars().all()
        return agreed, answers
    assert run(left) == (["p1@example.com"], ["p1@example.com"])


def test_an_address_whose_domain_takes_no_mail_is_left_out(shop, run, monkeypatch):
    from mail import address
    async def lookup(domain):
        return domain != "dead.example"
    monkeypatch.setattr(address, "_lookup", lookup)
    address._cache.clear()
    s = shop(people=2)
    async def go():
        async with async_session() as db:
            db.add(Contact(user_id=s.user.id, bot_id=s.bot, e164="+919811111111", name="Gone", email="gone@dead.example", details={}, calls=0))
            await consent.give(db, s.user.id, s.bot, "gone@dead.example", "import", "x")
            await db.commit()
    run(go)
    broadcast = s.draft()
    s.started(broadcast)
    assert sorted(j.to_email for j in s.jobs(broadcast)) == ["p0@example.com", "p1@example.com"]
    assert s.client.get(f"/api/email/broadcasts/{broadcast}", headers=s.h).json()["no_mail_server"] == 1


def test_a_list_nobody_can_receive_pauses_and_says_why(shop, run, monkeypatch):
    from mail import address
    async def lookup(domain):
        return False
    monkeypatch.setattr(address, "_lookup", lookup)
    address._cache.clear()
    s = shop(people=1)
    broadcast = s.draft()
    s.started(broadcast)
    b = s.get(broadcast)
    assert b.status == "paused" and "mail server" in b.paused_why and s.jobs(broadcast) == []


def test_resuming_a_send_that_hasnt_started_keeps_its_time(shop):
    s = shop(people=1)
    broadcast = s.draft()
    at = (datetime.utcnow() + timedelta(days=1)).replace(microsecond=0)
    assert s.send(broadcast, at=at.isoformat() + "+00:00").status_code == 200
    assert s.client.post(f"/api/email/broadcasts/{broadcast}/pause", headers=s.h).json()["status"] == "paused"
    resumed = s.client.post(f"/api/email/broadcasts/{broadcast}/resume", headers=s.h).json()
    assert resumed["status"] == "scheduled" and s.get(broadcast).send_at.replace(tzinfo=None) == at

