"""Email > Reports match the raw events they're made from (mail plan, phase 6)."""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.future import select

from backend.models import (Contact, EmailBroadcast, EmailClick, EmailDomain, EmailJob, EmailThread, EmailUnsubscribe, Journey, JourneyRun, Meeting, ThreadMessage)
from database import async_session
from mail import address, reports


def _job(user, bot, to, sent, **k):
    return EmailJob(user_id=user, bot_id=bot, kind=k.pop("kind", f"chat_lead#{uuid.uuid4().hex[:6]}"), ref_id=k.pop("ref_id", uuid.uuid4().hex), to_email=to,
                    automation=k.pop("automation", "chat_lead"), step=1, subject="s", body="b", status=k.pop("status", "sent"), send_at=sent, sent_at=sent, **k)


@pytest.fixture
def seeded(make_user, run):
    owner, member = make_user("Karthik"), make_user("Priya Team")
    bot = owner.bot()
    now = datetime.utcnow()
    d = lambda days, hours=0, minutes=0: now - timedelta(days=days) + timedelta(hours=hours, minutes=minutes)

    async def go():
        async with async_session() as db:
            journey = Journey(user_id=owner.id, bot_id=bot, name="Welcome series", trigger="new_lead", steps=[{"type": "wait", "days": 1}], enabled=True)
            send = EmailBroadcast(user_id=owner.id, bot_id=bot, subject="Diwali offer", body="x", status="sent")
            db.add_all([journey, send])
            await db.flush()
            r1 = JourneyRun(journey_id=journey.id, user_id=owner.id, bot_id=bot, contact_id=None, slot="r1", status="done", step=1, history=[])
            r2 = JourneyRun(journey_id=journey.id, user_id=owner.id, bot_id=bot, contact_id=None, slot="r2", status="done", step=1, history=[])
            db.add_all([r1, r2])
            await db.flush()
            jobs = [
                _job(owner.id, bot, "a@x.in", d(10), delivered_at=d(10), clicked_at=d(10, 1)),
                _job(owner.id, bot, "b@x.in", d(9), bounced_at=d(9)),
                _job(owner.id, bot, "c@x.in", d(8), delivered_at=d(8), complained_at=d(8, 2)),
                _job(owner.id, bot, "d@x.in", d(8), status="failed"),
                _job(owner.id, bot, "e@x.in", d(5), automation="journey", kind="journey#0", ref_id=r1.id, delivered_at=d(5)),
                _job(owner.id, bot, "f@x.in", d(4), automation="journey", kind="journey#0", ref_id=r2.id, delivered_at=d(4)),
                _job(owner.id, bot, "g@x.in", d(3), automation="broadcast", kind=f"broadcast:{send.id}", broadcast_id=send.id, delivered_at=d(3)),
                _job(owner.id, bot, "h@x.in", d(3), automation="broadcast", kind=f"broadcast:{send.id}#2", broadcast_id=send.id, delivered_at=d(3), clicked_at=d(3, 4)),
                _job(owner.id, bot, "old@x.in", d(40), delivered_at=d(40)),
            ]
            db.add_all(jobs)
            await db.flush()
            db.add(EmailClick(user_id=owner.id, token=uuid.uuid4().hex[:22], job_id=jobs[6].id, kind="link", at=d(3), person=False, settled_at=d(3)))
            te = EmailThread(user_id=owner.id, bot_id=bot, code=uuid.uuid4().hex[:16], email="e@x.in")
            th = EmailThread(user_id=owner.id, bot_id=bot, code=uuid.uuid4().hex[:16], email="h@x.in")
            ta = EmailThread(user_id=owner.id, bot_id=bot, code=uuid.uuid4().hex[:16], email="a@x.in")
            tg = EmailThread(user_id=owner.id, bot_id=bot, code=uuid.uuid4().hex[:16], email="g@x.in")
            db.add_all([te, th, ta, tg])
            await db.flush()
            db.add_all([
                ThreadMessage(thread_id=te.id, user_id=owner.id, direction="in", who="customer", status="received", sender="e@x.in", text="Yes", created_at=d(5, 1)),
                ThreadMessage(thread_id=te.id, user_id=owner.id, direction="out", who="team", status="sent", by=owner.id, text="Great", created_at=d(5, 1, 30)),
                ThreadMessage(thread_id=te.id, user_id=owner.id, direction="in", who="customer", status="received", sender="e@x.in", text="Thanks", created_at=d(5, 4)),
                ThreadMessage(thread_id=th.id, user_id=owner.id, direction="in", who="customer", status="received", sender="h@x.in", text="Price?", created_at=d(2)),
                ThreadMessage(thread_id=th.id, user_id=owner.id, direction="out", who="team", status="sent", by=member.id, text="Rs 45 lakh", created_at=d(2, 1, 30)),
                ThreadMessage(thread_id=ta.id, user_id=owner.id, direction="in", who="customer", status="received", sender="a@x.in", text="Late", created_at=d(1)),
                ThreadMessage(thread_id=ta.id, user_id=owner.id, direction="in", who="customer", status="received", sender="a@x.in", text="OOO", created_at=d(1), automatic=True),
                ThreadMessage(thread_id=tg.id, user_id=owner.id, direction="in", who="customer", status="received", sender="g@x.in", text="Out of office", created_at=d(3, 2),
                              automatic=True),
                EmailUnsubscribe(user_id=owner.id, email="f@x.in", reason="unsubscribed", scope="all", created_at=d(2)),
                Contact(user_id=owner.id, bot_id=bot, e164="+919800000001", email="a@x.in", details={}, calls=0, created_at=d(10)),
                Contact(user_id=owner.id, bot_id=bot, e164="+919800000005", email="e@x.in", details={}, calls=0, created_at=d(6)),
                Contact(user_id=owner.id, bot_id=bot, e164="+919800000007", email="g@x.in", details={}, calls=0, created_at=d(3), stage="customer"),
                Contact(user_id=owner.id, bot_id=bot, e164="+919800000026", email="z@x.in", details={}, calls=0, created_at=d(1)),
                Contact(user_id=owner.id, bot_id=bot, e164="+919800000099", email="past@x.in", details={}, calls=0, created_at=d(60)),
                Meeting(user_id=owner.id, bot_id=bot, e164="+919800000005", starts_at=now + timedelta(days=2), status="confirmed", created_at=d(4)),
            ])
            await db.commit()
    run(go)
    return owner, member, bot


def _by_label(report):
    return {r["label"]: {k: r[k] for k in ("sent", "delivered", "bounced", "complained", "clicked", "replied", "unsubscribed")} for r in report["emails"]}


def test_each_email_s_numbers_match_the_raw_events(seeded, run):
    owner, member, bot = seeded
    async def go():
        async with async_session() as db:
            return await reports.build(db, owner.id, bot, 30)
    report = run(go)
    assert _by_label(report) == {
        "After a chat": {"sent": 3, "delivered": 2, "bounced": 1, "complained": 1, "clicked": 1, "replied": 0, "unsubscribed": 0},
        "Welcome series": {"sent": 2, "delivered": 2, "bounced": 0, "complained": 0, "clicked": 0, "replied": 1, "unsubscribed": 1},
        "Diwali offer": {"sent": 2, "delivered": 2, "bounced": 0, "complained": 0, "clicked": 1, "replied": 1, "unsubscribed": 0},
    }, "h's reply a day on is the Diwali email's; a's late reply (9 days on) and g's out-of-office aren't credited; the scanner's click isn't a click; the failed and the 40-day-old emails aren't in it"
    assert {r["label"]: r["type"] for r in report["emails"]} == {"After a chat": "automatic", "Welcome series": "journey", "Diwali offer": "bulk"}


def test_the_funnel_follows_the_period_s_leads(seeded, run):
    owner, member, bot = seeded
    async def go():
        async with async_session() as db:
            return await reports.build(db, owner.id, bot, 30)
    assert run(go)["funnel"] == {"leads": 4, "emailed": 3, "engaged": 2, "meetings": 1, "customers": 1}


def test_the_team_s_answers_and_how_long_people_waited(seeded, run):
    owner, member, bot = seeded
    async def go():
        async with async_session() as db:
            return await reports.build(db, owner.id, bot, 30)
    team = {r["name"]: (r["answers"], r["median_minutes"]) for r in run(go)["team"]}
    assert team == {"Karthik": (1, 30), "Priya Team": (1, 90)}


def test_deliverability_counts_and_rates(seeded, run, monkeypatch):
    owner, member, bot = seeded
    records = {"example.co.in": "v=DMARC1; p=quarantine; rua=mailto:d@example.co.in", "nodmarc.in": None}
    async def lookup(name):
        return records.get(name)
    monkeypatch.setattr(address, "_dmarc_lookup", lookup)
    address._dmarc_cache.clear()
    async def go():
        async with async_session() as db:
            db.add_all([EmailDomain(user_id=owner.id, name="mail.example.co.in", status="verified"), EmailDomain(user_id=owner.id, name="nodmarc.in", status="verified")])
            await db.commit()
            return await reports.build(db, owner.id, bot, 30)
    d = run(go)["deliverability"]
    assert (d["sent"], d["delivered"], d["bounced"], d["complained"], d["scanner_clicks"]) == (7, 6, 1, 1, 1)
    assert d["bounce_rate"] == pytest.approx(1 / 7) and d["complaint_rate"] == pytest.approx(1 / 6) and (d["bounce_level"], d["complaint_level"]) == ("bad", "bad")
    assert {x["name"]: x["dmarc"] for x in d["domains"]} == {"mail.example.co.in": "quarantine", "nodmarc.in": "missing"}, "a subdomain falls back to its organisation's"


def test_a_shorter_period_has_less_in_it(seeded, run):
    owner, member, bot = seeded
    async def go():
        async with async_session() as db:
            return await reports.build(db, owner.id, bot, 7)
    report = run(go)
    assert set(_by_label(report)) == {"Welcome series", "Diwali offer"} and report["funnel"]["leads"] == 3


def test_the_organisation_of_a_domain():
    assert address.organisation("news.sunrise.co.in") == "sunrise.co.in" and address.organisation("mail.nimmiai.in") == "nimmiai.in"
    assert address.dmarc_policy("v=DMARC1; p=reject; pct=100") == "reject" and address.dmarc_policy("v=DMARC1;") is None


def test_the_reports_page_belongs_to_its_workspace(seeded, client, make_user):
    owner, member, bot = seeded
    assert client.get(f"/api/email/reports?days=30&bot_id={bot}", headers=owner.h()).json()["funnel"]["leads"] == 4
    assert client.get("/api/email/reports?days=15", headers=owner.h()).status_code == 400
    assert client.get(f"/api/email/reports?days=30&bot_id={bot}", headers=make_user().h()).status_code == 404
    everyone = client.get("/api/email/reports?days=30", headers=owner.h()).json()
    assert sum(r["sent"] for r in everyone["emails"]) == 7


def test_hot_now_is_on_the_overview(seeded, client, run):
    owner, member, bot = seeded
    async def hot():
        async with async_session() as db:
            c = (await db.execute(select(Contact).where(Contact.bot_id == bot, Contact.email == "e@x.in"))).scalars().first()
            c.engagement, c.engaged_at, c.engaged_by = 40, datetime.utcnow() - timedelta(hours=3), [{"what": "replied", "kind": "reply", "at": datetime.utcnow().isoformat()}]
            await db.commit()
    run(hot)
    assert [h["email"] for h in client.get("/api/email/overview", headers=owner.h()).json()["hot"]] == ["e@x.in"]


def test_how_far_a_domain_is_from_its_logo_in_gmail():
    from mail.address import bimi_stage
    strict = "v=DMARC1; p=quarantine; rua=mailto:x@y.in"
    assert bimi_stage(None, None) == "needs_dmarc"
    assert bimi_stage("v=DMARC1; p=none;", None) == "needs_dmarc"
    assert bimi_stage("v=DMARC1; p=quarantine; pct=50", None) == "needs_dmarc", "it has to cover all mail"
    assert bimi_stage(strict, None) == "ready" and bimi_stage("v=DMARC1; p=reject; pct=100", None) == "ready"
    assert bimi_stage(strict, "v=BIMI1; l=https://x.in/logo.svg") == "needs_certificate", "Gmail wants a certificate"
    assert bimi_stage(strict, "v=BIMI1; l=https://x.in/logo.svg; a=https://x.in/cert.pem") == "on"
