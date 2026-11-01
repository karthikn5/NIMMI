"""
Email, phase 1 (mail_plan.md): the phone agent's send_email function. It's on per assistant and with Growth; it goes at once, to the
address on file, which the agent is never told, or one given on the call; a file goes as a tracked download; a test call sends
nothing; bounced addresses are skipped while someone who unsubscribed still gets what they just asked for; and numbers the agent
can't back up don't reach the email.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.future import select

from backend.models import Bot, Contact, EmailBounce, EmailJob, EmailLink, EmailUnsubscribe, WhatsAppFile
from database import async_session
from mail import address, during_call, setup
from notify import email
from voice import functions, schedule

BASE = {
    "email_alerts": False, "alert_email": "", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
    "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "", "reply_to": "team@sunrise.in",
}
E164 = "+919876500010"


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
    def make(on=True, address_on_file="priya@buyers.in"):
        u = make_user()
        u.bot_id = u.bot("Sunrise")
        client.put("/api/integrations", json=BASE, headers=u.h())
        if on:
            assert client.put(f"/api/email/setup/{u.bot_id}", json={"settings": {"during_call": {"enabled": True}}}, headers=u.h()).status_code == 200

        async def fill():
            async with async_session() as db:
                db.add(Contact(user_id=u.id, bot_id=u.bot_id, e164=E164, name="Priya Sharma", email=address_on_file, details={}, calls=1))
                db.add(WhatsAppFile(user_id=u.id, name="Price list", when_to_send="when they ask about prices", kind="document", filename="prices.pdf",
                                    mime="application/pdf", stored="x", size=2_000_000))
                (await db.get(Bot, u.bot_id)).knowledge_base = "Homes from 45 lakh."
                await db.commit()
        run(fill)
        return u
    return make


def tools(run, u, test=False):
    return run(schedule.tools_for, u.id, u.bot_id, None if test else E164, None, name="Priya Sharma", call_id=lambda: str(uuid.uuid4()), test=test)


def test_it_is_off_until_the_assistant_switches_it_on(business, run):
    assert run(schedule.tools_for, business(on=False).id, business(on=False).bot_id, E164, None) is None
    u = business()
    t = tools(run, u)
    assert t.has("send_email") and "send_email" in functions.RESERVED


def test_the_agent_knows_there_is_an_address_but_never_what_it_is(business, run):
    t = tools(run, business())
    spec = next(s for s in t.specs() if s["name"] == "send_email")
    assert "Price list" in spec["description"] and "on file" in spec["description"]
    assert "priya@buyers.in" not in str(t.specs()) and "priya@buyers.in" not in t.rules()
    assert "Never read out the email address" in t.rules()


def test_without_an_address_it_asks_and_spells_it_back(business, run, sent):
    u = business(address_on_file=None)
    t = tools(run, u)
    assert "spell it back" in next(s for s in t.specs() if s["name"] == "send_email")["description"]
    assert "spell their email back" in t.rules()
    told = run(t.run, "send_email", {"file": "Price list"})
    assert "don't have an address" in told and sent == []
    told = run(t.run, "send_email", {"file": "Price list", "address": "priya.new@buyers.in"})
    assert told.startswith("Sent") and sent[0]["to"] == "priya.new@buyers.in"

    async def kept():
        async with async_session() as db:
            return (await db.execute(select(Contact.email).where(Contact.bot_id == u.bot_id))).scalar()
    assert run(kept) == "priya.new@buyers.in"


def test_a_file_goes_at_once_as_a_tracked_download_and_shows_in_history(client, business, run, sent):
    u = business()
    told = run(tools(run, u).run, "send_email", {"file": "price list", "note": "Here's the price list you asked for."})
    assert told.startswith("Sent") and "read the address out" in told
    m = sent[0]
    assert m["to"] == "priya@buyers.in" and m["subject"] == "As promised on our call" and "Hi Priya," in m["text"] and "Price list" in m["html"]
    assert m["reply_to"] == "team@sunrise.in" and m["unsubscribe_url"] and m["tags"]["kind"] == "customer"

    async def rows():
        async with async_session() as db:
            return (await db.execute(select(EmailLink).where(EmailLink.user_id == u.id, EmailLink.kind == "file"))).scalars().all()
    assert len(run(rows)) == 1
    item = client.get("/api/integrations/email/history", headers=u.h()).json()["items"][0]
    assert item["status"] == "sent" and item["label"] == "Sent during a call"


def test_a_test_call_sends_nothing(business, run, sent):
    assert "no email goes" in run(tools(run, business(), test=True).run, "send_email", {"file": "Price list"}) and sent == []


def test_a_file_that_is_not_there_is_not_made_up(business, run, sent):
    assert "isn't in the list" in run(tools(run, business()).run, "send_email", {"file": "Floor plans"}) and sent == []


def test_a_number_it_cant_back_up_stays_out_of_the_email(business, run, sent):
    run(tools(run, business()).run, "send_email", {"note": "Homes start at 45 lakh. There's a 20% discount for you."})
    assert "45 lakh" in sent[0]["text"] and "20%" not in sent[0]["text"]


def test_unsubscribed_people_still_get_what_they_asked_for_but_bounced_addresses_dont(business, run, sent):
    u = business()

    async def stopped():
        async with async_session() as db:
            db.add(EmailUnsubscribe(user_id=u.id, email="priya@buyers.in", reason="unsubscribed", scope="all"))
            await db.commit()
    run(stopped)
    assert run(tools(run, u).run, "send_email", {"file": "Price list"}).startswith("Sent")

    u2 = business(address_on_file=f"gone-{uuid.uuid4().hex[:6]}@buyers.in")

    async def bounced():
        async with async_session() as db:
            contact = (await db.execute(select(Contact).where(Contact.bot_id == u2.bot_id))).scalars().first()
            db.add(EmailBounce(email=contact.email, kind="bounce"))
            await db.commit()
    run(bounced)
    before = len(sent)
    assert "can't be emailed" in run(tools(run, u2).run, "send_email", {"file": "Price list"}) and len(sent) == before


def test_a_bad_address_is_refused_and_a_slow_check_doesnt_hold_up_the_call(business, run, sent, monkeypatch):
    u = business(address_on_file=None)

    async def dead(domain):
        return False
    monkeypatch.setattr(address, "_lookup", dead)
    address._cache.clear()
    assert "doesn't look right" in run(tools(run, u).run, "send_email", {"address": "priya@nowhere.in"}) and sent == []

    async def slow(domain):
        import asyncio
        await asyncio.sleep(5)
        return False
    monkeypatch.setattr(address, "_lookup", slow)
    monkeypatch.setattr(during_call, "ADDRESS_SECONDS", 0.05)
    address._cache.clear()
    assert run(tools(run, u).run, "send_email", {"address": "priya@slow.in"}).startswith("Sent")


def test_three_on_a_call_is_enough(business, run, sent):
    t = tools(run, business())
    for _ in range(3):
        assert run(t.run, "send_email", {"note": "Here it is."}).startswith("Sent")
    assert "enough" in run(t.run, "send_email", {"note": "One more."}) and len(sent) == 3


def test_it_comes_with_growth(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot("Sunrise")
    client.put("/api/integrations", json=BASE, headers=u.h())
    monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")
    assert client.put(f"/api/email/setup/{bot}", json={"settings": {"during_call": {"enabled": True}}}, headers=u.h()).status_code == 402
