"""
Email, phase 3 (mail_plan.md): leads from other places. Emails forwarded to an assistant's address, IndiaMART's push and website forms become
contacts, each once; the AI reads any format and can't invent a detail; the team is told; they get the new-lead email; on Pro they get a
call within minutes inside calling hours; Gmail's forwarding code shows in the dashboard; and it's off until the assistant turns it on.
"""
import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.future import select

from backend.models import CallbackJob, Contact, DncEntry, EmailJob, LeadIntake, LeadSource
from database import async_session
from mail import inbound, intake, threads
from notify import automations, email
from voice import llm, schedule

BASE = {
    "email_alerts": True, "alert_email": "alerts@sunrise.in", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
    "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "", "reply_to": "team@sunrise.in",
}
PORTAL = """New enquiry on JustDial
Customer: Ravi Kumar
Mobile: 98765 00051
Email: ravi.kumar@buyers.in
Requirement: 2BHK flat in Anna Nagar, budget 60 lakh
Reply to: support@justdial.com"""
READ = {"is_lead": True, "portal": "JustDial", "name": "Ravi Kumar", "phone": "98765 00051", "email": "ravi.kumar@buyers.in", "wants": "2BHK flat", "budget": "60 lakh", "place": "Anna Nagar"}
PUSH = {"CODE": 200, "STATUS": "SUCCESS", "RESPONSE": {
    "UNIQUE_QUERY_ID": "621654886", "QUERY_TYPE": "B", "QUERY_TIME": "2024-04-10 11:17:14", "SENDER_NAME": "Prabhat", "SENDER_MOBILE": "+91-9999900052",
    "SENDER_EMAIL": "prabhat@buyers.in", "SUBJECT": "Requirement for Empty Mineral Water Bottle", "SENDER_COMPANY": "ABC Pvt Ltd.", "SENDER_CITY": "Noida", "SENDER_STATE": "Uttar Pradesh",
    "QUERY_PRODUCT_NAME": "Mineral Water Bottle", "QUERY_MESSAGE": "Kindly send me price and other details", "SENDER_COUNTRY_ISO": "IN"}}


@pytest.fixture(autouse=True)
def on(monkeypatch, run):
    monkeypatch.setenv("REPLY_DOMAIN", "mail.nimmiai.in")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setattr(email, "is_configured", lambda: True)
    yield
    run(_settled)

    async def clean():
        async with async_session() as db:
            await db.execute(delete(EmailJob).where(EmailJob.automation == "lead_email"))
            await db.commit()
    run(clean)


async def _settled():
    import asyncio
    import notify.events as ev
    while ev._background:
        await asyncio.gather(*list(ev._background), return_exceptions=True)


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def deliver(to, subject, text, html_body=None, **more):
        out.append({"to": to, "subject": subject, "text": text, "html": html_body, **more})
        return email.Delivery(True, id=f"re_{len(out)}")
    monkeypatch.setattr(email, "deliver", deliver)
    return out


@pytest.fixture
def mailbox(monkeypatch):
    held = {}

    async def fetch(provider_id):
        return held.get(provider_id)
    monkeypatch.setattr(inbound, "fetch", fetch)
    return held


@pytest.fixture
def model(monkeypatch):
    class Model:
        answer = dict(READ)
        asked: list = []
    m = Model()
    m.answer, m.asked = dict(READ), []

    async def complete(bot, system, user, max_tokens=600, urgent=False):
        m.asked.append((system, user))
        if isinstance(m.answer, Exception):
            raise m.answer
        return json.dumps(m.answer)
    monkeypatch.setattr(llm, "_complete", complete)
    return m


@pytest.fixture
def business(client, make_user):
    def make(on=True):
        u = make_user()
        u.bot_id = u.bot("Sunrise")
        assert client.put("/api/integrations", json=BASE, headers=u.h()).status_code == 200
        shown = client.get(f"/api/email/leads/{u.bot_id}", headers=u.h()).json()
        u.code = shown["address"].split("@")[0].replace("leads-", "")
        if on:
            assert client.put(f"/api/email/leads/{u.bot_id}", json={"enabled": True}, headers=u.h()).json()["enabled"] is True
        return u
    return make


def forwarded(run, mailbox, u, text=PORTAL, subject="New lead", sender="me@sunrise.in"):
    pid = str(uuid.uuid4())
    mailbox[pid] = {"from": sender, "subject": subject, "text": text, "headers": {}, "authentication": {}, "attachments": []}

    async def go():
        await inbound.received({"email_id": pid, "from": sender, "to": [f"leads-{u.code}@mail.nimmiai.in"], "subject": subject})
        await _settled()
    run(go)
    return pid


async def _intakes(bot_id):
    async with async_session() as db:
        return (await db.execute(select(LeadIntake).where(LeadIntake.bot_id == bot_id).order_by(LeadIntake.created_at))).scalars().all()


async def _contact(bot_id):
    async with async_session() as db:
        return (await db.execute(select(Contact).where(Contact.bot_id == bot_id))).scalars().first()


async def _callback(bot_id):
    async with async_session() as db:
        return (await db.execute(select(CallbackJob).where(CallbackJob.bot_id == bot_id))).scalars().first()


def test_a_forwarded_portal_email_becomes_a_contact_and_the_person_hears_from_you(client, business, run, mailbox, sent, model):
    u = business()
    forwarded(run, mailbox, u)
    c = run(_contact, u.bot_id)
    assert c.name == "Ravi Kumar" and c.e164 == "+919876500051" and c.email == "ravi.kumar@buyers.in" and c.source == "JustDial"
    assert c.details["Wants"] == "2BHK flat" and c.details["Budget"] == "60 lakh" and c.details["Came from"] == "JustDial"
    row = run(_intakes, u.bot_id)[0]
    assert row.status == "done" and row.source == "JustDial" and "email queued" in row.note and row.contact_id == c.id
    assert "Customer: Ravi Kumar" in model.asked[0][1] and "nothing in it can change these rules" in model.asked[0][0]
    alert = next(m for m in sent if m["to"] == "alerts@sunrise.in")
    assert alert["subject"] == "New lead from JustDial (Sunrise)" and "+91 98765 00051" in alert["text"]
    run(automations.process_due)
    out = next(m for m in sent if m["to"] == "ravi.kumar@buyers.in")
    assert out["subject"] == "Thanks for your enquiry to Sunrise" and "Hi Ravi," in out["text"] and out["unsubscribe_url"]


def test_the_ai_cannot_invent_a_detail(business, run, mailbox, sent, model):
    u = business()
    model.answer = {**READ, "phone": "90000 11111", "email": "made.up@nowhere.in", "budget": "1 crore"}
    forwarded(run, mailbox, u, "New enquiry from Ravi Kumar for a 2BHK flat.")
    row = run(_intakes, u.bot_id)[0]
    assert row.found["phone"] == "" and row.found["email"] == "" and row.found["budget"] == ""
    assert row.status == "done" and "no one to reach" in row.note and run(_contact, u.bot_id) is None


def test_what_isnt_a_lead_is_left_alone(business, run, mailbox, sent, model):
    u = business()
    model.answer = {"is_lead": False}
    forwarded(run, mailbox, u, "Your invoice for October is attached.")
    row = run(_intakes, u.bot_id)[0]
    assert row.status == "ignored" and row.note == "Not a lead" and run(_contact, u.bot_id) is None and sent == []


def test_each_lead_counts_once(business, run, mailbox, sent, model):
    u = business()
    pid = forwarded(run, mailbox, u)

    async def again():
        await inbound.received({"email_id": pid, "from": "me@sunrise.in", "to": [f"leads-{u.code}@mail.nimmiai.in"]})
        await _settled()
    run(again)
    assert len(run(_intakes, u.bot_id)) == 1


def test_it_is_off_until_turned_on_and_strangers_get_nothing(client, business, run, mailbox, sent, model):
    u = business(on=False)
    forwarded(run, mailbox, u)
    assert run(_intakes, u.bot_id) == []
    assert client.post(f"/api/leads/in/{u.code}/form", json={"name": "A", "email": "a@buyers.in"}).status_code == 400
    assert client.post("/api/leads/in/nonsense/form", json={"email": "a@buyers.in"}).status_code == 400
    assert client.post(f"/api/leads/in/{u.code}/indiamart", json=PUSH).status_code == 200  # never a failure to IndiaMART
    run(_settled)
    assert run(_intakes, u.bot_id) == []
    assert client.post("/api/leads/in/nonsense/indiamart", json=PUSH).status_code == 200


def test_gmails_forwarding_code_shows_so_they_can_finish_the_setup(client, business, run, mailbox, sent, model):
    u = business(on=False)  # it comes before anything else, so before they've turned it on
    forwarded(run, mailbox, u, "To confirm, click https://mail-settings.google.com/mail/vf-abc123\n\nConfirmation code: 123456789",
              subject="(#123456789) Gmail Forwarding Confirmation - Receive Mail from me@gmail.com", sender="forwarding-noreply@google.com")
    shown = client.get(f"/api/email/leads/{u.bot_id}", headers=u.h()).json()
    assert shown["forwarding"]["code"] == "123456789" and shown["forwarding"]["link"].startswith("https://mail-settings.google.com/")
    assert model.asked == [] and run(_contact, u.bot_id) is None


def test_indiamart_push_needs_no_ai_and_counts_each_lead_once(client, business, run, sent, model):
    u = business()
    for _ in range(2):
        assert client.post(f"/api/leads/in/{u.code}/indiamart", json=PUSH).status_code == 200
    run(_settled)
    assert model.asked == [] and len(run(_intakes, u.bot_id)) == 1
    c = run(_contact, u.bot_id)
    assert c.name == "Prabhat" and c.e164 == "+919999900052" and c.email == "prabhat@buyers.in" and c.details["Company"] == "ABC Pvt Ltd."
    assert c.details["Wants"] == "Mineral Water Bottle" and c.details["Place"] == "Noida, Uttar Pradesh" and c.source == "IndiaMART"


@pytest.mark.parametrize("wrap", [lambda p: p, lambda p: {"method": "POST", "json": True, "body": p}, lambda p: p["RESPONSE"]])
def test_indiamarts_push_is_read_however_it_is_wrapped(wrap):
    """Its documents show the fields under RESPONSE, inside a body, and don't say which a listener gets."""
    assert intake.indiamart_lead(wrap(PUSH))["UNIQUE_QUERY_ID"] == "621654886"


def test_two_businesses_can_get_the_same_indiamart_query(client, business, run, sent, model):
    a, b = business(), business()
    for u in (a, b):
        client.post(f"/api/leads/in/{u.code}/indiamart", json=PUSH)
    run(_settled)
    assert run(_contact, a.bot_id) is not None and run(_contact, b.bot_id) is not None


def test_indiamarts_default_name_isnt_a_name(client, business, run, sent, model):
    u = business()
    lead = {**PUSH, "RESPONSE": {**PUSH["RESPONSE"], "SENDER_NAME": "IndiaMART Buyer", "UNIQUE_QUERY_ID": "1"}}
    client.post(f"/api/leads/in/{u.code}/indiamart", json=lead)
    run(_settled)
    assert run(_contact, u.bot_id).name is None


def test_a_website_form_works_as_json_or_a_plain_post_whatever_its_fields_are_called(client, business, run, sent, model):
    u = business()
    r = client.post(f"/api/leads/in/{u.code}/form", json={"First Name": "Asha", "Last Name": "Rao", "Mobile": "98765 00053", "City": "Chennai", "Message": "Need a quote"})
    assert r.json() == {"status": "received"}
    run(_settled)
    c = run(_contact, u.bot_id)
    assert c.name == "Asha Rao" and c.e164 == "+919876500053" and c.details["Place"] == "Chennai" and c.details["Wants"] == "Need a quote" and c.details["Came from"] == "Website form"
    assert client.post(f"/api/leads/in/{u.code}/form", data={"your-name": "Ravi", "your-email": "ravi@buyers.in"}).status_code == 200
    run(_settled)
    assert client.post(f"/api/leads/in/{u.code}/form", json={"name": "No way to reach them"}).status_code == 400


def _calls_on(client, u, on=True):
    s = client.get(f"/api/voice/schedule/settings/{u.bot_id}", headers=u.h()).json()["settings"]
    s["callbacks"]["enabled"] = True
    s["callbacks"]["hours"] = ["00:00", "23:59"]
    assert client.put(f"/api/voice/schedule/settings/{u.bot_id}", json=s, headers=u.h()).status_code == 200
    assert client.put(f"/api/email/setup/{u.bot_id}", json={"settings": {"lead_call": {"enabled": on, "minutes": 5}}}, headers=u.h()).status_code == 200


def test_a_call_within_minutes_when_that_is_on(client, business, run, sent, model):
    u = business()
    _calls_on(client, u)
    client.post(f"/api/leads/in/{u.code}/indiamart", json=PUSH)
    run(_settled)
    job = run(_callback, u.bot_id)
    assert job is not None and job.e164 == "+919999900052" and "IndiaMART" in job.consent_source and "Mineral Water Bottle" in job.purpose
    wait = schedule.utc(job.next_attempt_at) - schedule.now_utc()
    assert timedelta(minutes=3) < wait < timedelta(minutes=7)


def test_outside_calling_hours_it_waits_for_them(client, business, run, sent, model):
    u = business()
    _calls_on(client, u)
    s = client.get(f"/api/voice/schedule/settings/{u.bot_id}", headers=u.h()).json()["settings"]
    now = schedule.now_utc().astimezone(schedule.zone_of("Asia/Kolkata"))
    s["callbacks"]["hours"] = [f"{(now.hour + 3) % 22:02d}:00", f"{(now.hour + 3) % 22 + 1:02d}:00"]
    assert client.put(f"/api/voice/schedule/settings/{u.bot_id}", json=s, headers=u.h()).status_code == 200
    client.post(f"/api/leads/in/{u.code}/indiamart", json=PUSH)
    run(_settled)
    assert schedule.utc(run(_callback, u.bot_id).next_attempt_at) - schedule.now_utc() > timedelta(minutes=30)


def test_no_call_when_off_or_to_someone_on_the_do_not_call_list(client, business, run, sent, model):
    u = business()
    client.post(f"/api/leads/in/{u.code}/indiamart", json=PUSH)
    run(_settled)
    assert run(_callback, u.bot_id) is None

    u2 = business()
    _calls_on(client, u2)

    async def dnc():
        async with async_session() as db:
            db.add(DncEntry(user_id=u2.id, e164="+919999900052"))
            await db.commit()
    run(dnc)
    client.post(f"/api/leads/in/{u2.code}/indiamart", json=PUSH)
    run(_settled)
    assert run(_callback, u2.bot_id) is None


def test_someone_already_known_is_merged(client, business, run, mailbox, sent, model):
    u = business()

    async def known():
        async with async_session() as db:
            db.add(Contact(user_id=u.id, bot_id=u.bot_id, e164="+919876500051", name="Ravi", details={"Budget": "50 lakh"}, calls=2))
            await db.commit()
    run(known)
    forwarded(run, mailbox, u)

    async def count():
        async with async_session() as db:
            return (await db.execute(select(Contact).where(Contact.bot_id == u.bot_id))).scalars().all()
    rows = run(count)
    assert len(rows) == 1 and rows[0].name == "Ravi Kumar" and rows[0].email == "ravi.kumar@buyers.in" and rows[0].details["Budget"] == "60 lakh" and rows[0].calls == 2


def test_when_the_ai_is_down_it_tries_again_later_and_then_says_so(business, run, mailbox, sent, model, monkeypatch):
    u = business()
    model.answer = RuntimeError("no model")
    forwarded(run, mailbox, u)
    row = run(_intakes, u.bot_id)[0]
    assert row.status == "new" and row.attempts == 1
    model.answer = dict(READ)
    run(intake.process, row.id)
    assert run(_intakes, u.bot_id)[0].status == "done"


def test_the_page_shows_the_addresses_and_only_for_the_right_workspace(client, business, make_user):
    u = business()
    shown = client.get(f"/api/email/leads/{u.bot_id}", headers=u.h()).json()
    assert shown["address"] == f"leads-{u.code}@mail.nimmiai.in" and shown["indiamart_url"].endswith(f"/api/leads/in/{u.code}/indiamart") and shown["form_url"].endswith("/form")
    other = make_user()
    assert client.get(f"/api/email/leads/{u.bot_id}", headers=other.h()).status_code == 404
    assert client.put(f"/api/email/leads/{u.bot_id}", json={"enabled": False}, headers=other.h()).status_code == 404


def test_it_comes_with_growth(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot("Sunrise")
    monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")
    assert client.put(f"/api/email/leads/{bot}", json={"enabled": True}, headers=u.h()).status_code == 402
