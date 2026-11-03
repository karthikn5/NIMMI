"""
Leads from ads and from the website, with where each came from (instagram_plan.md, phase 2): Google lead forms checked by their key, each lead once, test leads kept
apart; Facebook and Instagram lead ads by Zapier, Make or Pabbly; the website's first touch; the WhatsApp ad someone tapped, which the assistant is told about; junk
kept, marked and told to nobody, which a manager can overrule; the same person twice in a day told to nobody twice; and old leads imported with nobody contacted.
"""
import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.future import select

from backend.models import CallbackJob, Consent, Contact, Conversation, EmailJob, IntegrationSettings, LeadEvent, LeadIntake, LeadTask, NotificationLog
from database import async_session
from leads import origin as lead_origin, quality
from mail import journeys
from notify import email
from tests.test_leads import joined  # noqa: F401  (a fixture)
from tests.test_whatsapp import _pid, _sender, body, connect, meta, post, text_msg, wait_for  # noqa: F401  (meta is a fixture)

BASE = {"email_alerts": True, "alert_email": "alerts@sunrise.in", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
        "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "", "reply_to": "team@sunrise.in"}


@pytest.fixture(autouse=True)
def on(monkeypatch, run):
    """Email on, and never sent anywhere: every test's emails stop here (the `sent` fixture keeps them to look at)."""
    async def nowhere(to, subject, text, html_body=None, **more):
        return email.Delivery(True, id="re_test")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setattr(email, "is_configured", lambda: True)
    monkeypatch.setattr(email, "deliver", nowhere)
    yield
    run(_settled)


async def _settled():
    import notify.events as ev
    while ev._background:
        await asyncio.gather(*list(ev._background), return_exceptions=True)


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def deliver(to, subject, text, html_body=None, **more):
        out.append({"to": to, "subject": subject, "text": text})
        return email.Delivery(True, id=f"re_{len(out)}")
    monkeypatch.setattr(email, "deliver", deliver)
    return out


@pytest.fixture
def fired(monkeypatch):
    """Which new-lead journeys a lead would start."""
    out = []

    async def fire(owner_id, bot_id, trigger, contact_id, value=None):
        out.append((trigger, value))
    monkeypatch.setattr(journeys, "fire", fire)
    return out


@pytest.fixture
def business(client, make_user):
    def make(on=True):
        u = make_user()
        u.bot_id = u.bot("Sunrise")
        assert client.put("/api/integrations", json=BASE, headers=u.h()).status_code == 200
        shown = client.get(f"/api/email/leads/{u.bot_id}", headers=u.h()).json()
        u.code, u.key = shown["form_url"].rsplit("/", 2)[1], shown["google_key"]
        assert shown["google_url"].endswith(f"/api/leads/in/{u.code}/google") and shown["connect_url"].endswith(f"/api/leads/in/{u.code}/connect")
        if on:
            assert client.put(f"/api/email/leads/{u.bot_id}", json={"enabled": True}, headers=u.h()).json()["enabled"] is True
        return u
    return make


COLUMNS = [{"column_name": "Full Name", "string_value": "Kavya Rao", "column_id": "FULL_NAME"},
           {"column_name": "User Phone", "string_value": "+919876500201", "column_id": "PHONE_NUMBER"},
           {"column_name": "User Email", "string_value": "kavya@buyers.in", "column_id": "EMAIL"},
           {"column_name": "City", "string_value": "Coimbatore", "column_id": "CITY"},
           {"string_value": "30-40 lakh", "column_id": "PRICE_RANGE"},
           {"column_name": "Which project interests you?", "string_value": "Sunrise Towers", "column_id": "which_project"}]


def google(u, lead_id=None, key=None, test=False, columns=None, **more) -> dict:
    """A lead as Google sends it (developers.google.com/google-ads/webhook/docs/implementation)."""
    return {"lead_id": uuid.uuid4().hex if lead_id is None else lead_id, "api_version": "1.0", "form_id": 4021, "campaign_id": 9011, "google_key": u.key if key is None else key,
            **({"is_test": True} if test else {}), "gcl_id": "Cj0KCQ-test", "adgroup_id": 0, "creative_id": 0, "user_column_data": columns or COLUMNS, **more}


async def _all(model, bot_id):
    async with async_session() as db:
        return (await db.execute(select(model).where(model.bot_id == bot_id).order_by(model.created_at))).scalars().all()


async def _events(contact_id):
    async with async_session() as db:
        return (await db.execute(select(LeadEvent).where(LeadEvent.contact_id == contact_id).order_by(LeadEvent.at))).scalars().all()


def alerts(sent):
    return [s for s in sent if s["subject"].startswith("New lead")]


# ─── Google lead forms ───────────────────────────────────────────
def test_a_google_lead_comes_in_with_where_it_came_from(client, business, run, sent, fired):
    u = business()
    r = client.post(f"/api/leads/in/{u.code}/google", json=google(u))
    assert r.status_code == 200 and r.json() == {}
    run(_settled)
    [c] = run(_all, Contact, u.bot_id)
    assert (c.name, c.e164, c.email, c.source) == ("Kavya Rao", "+919876500201", "kavya@buyers.in", "Google lead form")
    assert c.details["Place"] == "Coimbatore" and c.details["Budget"] == "30-40 lakh" and c.details["Wants"] == "Which project interests you?: Sunrise Towers"
    assert c.origin == {"channel": "google_ads", "campaign_id": "9011", "form_id": "4021", "gclid": "Cj0KCQ-test"}   # Google's 0s for a form's missing ids are left out
    [row] = run(_all, LeadIntake, u.bot_id)
    assert row.channel == "google" and u.key not in (row.raw or "") and "Sunrise Towers" in row.raw                    # the key is never kept
    assert [a["subject"] for a in alerts(sent)] == ["New lead from Google lead form (Sunrise)"]
    assert ("new_lead", ("google", "ads", "any_ad")) in fired  # journeys for Google's forms, then any ad's lead form, then any ad (phase 7)
    lead = client.get(f"/api/crm/leads/{c.id}", headers=u.h()).json()
    assert lead["origin"]["channel"] == "google_ads" and len(lead["tasks"]) == 1 and lead["enquiry_days_left"] == 7


def test_the_same_google_lead_twice_is_one_lead(client, business, run, sent):
    u = business()
    lead = google(u)
    assert client.post(f"/api/leads/in/{u.code}/google", json=lead).status_code == 200
    assert client.post(f"/api/leads/in/{u.code}/google", json=lead).status_code == 200      # Google may send a lead twice: it hears 200 again
    run(_settled)
    assert len(run(_all, LeadIntake, u.bot_id)) == 1 and len(run(_all, Contact, u.bot_id)) == 1 and len(alerts(sent)) == 1


def test_a_wrong_google_key_is_refused_and_leaves_nothing(client, business, run, sent):
    u = business()
    for key in ("not-the-key", ""):
        r = client.post(f"/api/leads/in/{u.code}/google", json=google(u, key=key))
        assert r.status_code == 403 and "key" in r.json()["message"]                        # a 4xx: Google never retries it
    assert client.post(f"/api/leads/in/{'0' * 16}/google", json=google(u)).status_code == 404
    assert client.post(f"/api/leads/in/{u.code}/google", json=google(u, lead_id="")).status_code == 400
    run(_settled)
    assert run(_all, LeadIntake, u.bot_id) == [] and run(_all, Contact, u.bot_id) == [] and sent == []
    spelt = google(u)
    spelt["Google_key"] = spelt.pop("google_key")                                             # two of Google's own samples spell it so
    assert client.post(f"/api/leads/in/{u.code}/google", json=spelt).status_code == 200


def test_a_busy_moment_asks_google_to_try_again(client, business, monkeypatch):
    from fastapi import HTTPException
    from mail import leads_api
    u = business()

    def busy(*a):
        raise HTTPException(status_code=429, detail="Too many")
    monkeypatch.setattr(leads_api, "rate_limit", busy)
    r = client.post(f"/api/leads/in/{u.code}/google", json=google(u))
    assert r.status_code == 503 and r.json()["message"]                                      # a 5xx: Google sends it again later; a 429 it would drop


def test_a_real_lead_while_lead_sources_are_off_is_refused(client, business, run):
    u = business(on=False)
    r = client.post(f"/api/leads/in/{u.code}/google", json=google(u))
    assert r.status_code == 403 and "turned off" in r.json()["message"]
    run(_settled)
    assert run(_all, LeadIntake, u.bot_id) == []


def test_google_test_leads_reach_nobody(client, business, run, sent, fired):
    u = business()
    assert client.post(f"/api/leads/in/{u.code}/google", json=google(u, test=True)).status_code == 200
    assert client.post(f"/api/leads/in/{u.code}/google", json=google(u, test=True, key="testkey")).status_code == 200   # whichever key Google's button sends
    run(_settled)
    rows = run(_all, LeadIntake, u.bot_id)
    assert [r.test for r in rows] == [True, True] and [r.status for r in rows] == ["done", "done"]
    assert rows[0].note == "A test lead: nobody was told or contacted" and "another key" in rows[1].note
    assert run(_all, Contact, u.bot_id) == [] and sent == [] and fired == []
    shown = client.get(f"/api/email/leads/{u.bot_id}", headers=u.h()).json()["recent"]
    assert [r["test"] for r in shown] == [True, True]
    off = business(on=False)
    assert client.post(f"/api/leads/in/{off.code}/google", json=google(off, test=True)).status_code == 200
    run(_settled)
    assert "Turn on" in run(_all, LeadIntake, off.bot_id)[0].note                              # it works, and says real leads need the switch


def test_google_columns_are_read_by_their_id(client, business, run):
    u = business()
    columns = [{"string_value": "Arun", "column_id": "FIRST_NAME"}, {"string_value": "Kumar", "column_id": "LAST_NAME"},
               {"string_value": "arun@works.in", "column_id": "WORK_EMAIL"}, {"string_value": "true", "column_id": "PHONE_NUMBER_VERIFIED"},
               {"string_value": "+919876500202", "column_id": "PHONE_NUMBER"}, {"string_value": "Acme", "column_id": "COMPANY_NAME"}]
    client.post(f"/api/leads/in/{u.code}/google", json=google(u, columns=columns))
    run(_settled)
    [c] = run(_all, Contact, u.bot_id)
    assert (c.name, c.email, c.e164, c.details["Company"], c.details["Phone checked by Google"]) == ("Arun Kumar", "arun@works.in", "+919876500202", "Acme", "Yes")


# ─── lead ads by Zapier, Make or Pabbly ───────────────────────────
def test_a_lead_ad_through_zapier_says_which_ad(client, business, run, sent, fired):
    u = business()
    lead = {"full_name": "Divya Menon", "phone_number": "+91 98765 00211", "email": "divya@buyers.in", "lead_id": "3301", "campaign_name": "Diwali offer",
            "ad_name": "2BHK carousel", "form_name": "Site visit form", "platform": "ig"}
    for _ in range(2):  # Zapier sends it again when it retries
        assert client.post(f"/api/leads/in/{u.code}/connect", json=lead).status_code == 200
    run(_settled)
    [c] = run(_all, Contact, u.bot_id)
    assert c.source == "Instagram lead ads" and len(run(_all, LeadIntake, u.bot_id)) == 1
    assert c.origin == {"channel": "meta_ads", "campaign_name": "Diwali offer", "ad_name": "2BHK carousel", "form_name": "Site visit form", "platform": "ig"}
    assert ("new_lead", ("meta", "ads", "any_ad")) in fired  # a Facebook or Instagram lead ad, by Zapier as by a direct connection
    facebook = business()
    client.post(f"/api/leads/in/{facebook.code}/connect", data={"Full Name": "Rohan", "Phone Number": "98765 00212"})       # a form post, names as Zapier shows them
    client.post(f"/api/leads/in/{facebook.code}/connect", json={"full_name": "Sara", "email": "sara@buyers.in", "source": "Typeform"})
    run(_settled)
    assert sorted(c.source for c in run(_all, Contact, facebook.bot_id)) == ["Facebook lead ads", "Typeform"]           # their own source wins


def test_the_connect_link_takes_more_than_a_website_form_from_one_address(client, business, run):
    """Every lead from Zapier comes from the same few servers: only the website form is limited per address."""
    u = business()
    codes = [client.post(f"/api/leads/in/{u.code}/connect", json={"full_name": f"Lead {n}", "phone_number": f"98765 003{n:02d}", "lead_id": f"z{n}"}).status_code
             for n in range(22)]
    assert set(codes) == {200}
    run(_settled)


def test_a_website_form_keeps_the_pages_tags(client, business, run):
    u = business()
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Anil", "phone": "98765 00221", "utm_source": "google", "utm_campaign": "anna-nagar", "gclid": "abc", "secret": "x"})
    run(_settled)
    [c] = run(_all, Contact, u.bot_id)
    assert c.origin == {"channel": "website", "utm_source": "google", "utm_campaign": "anna-nagar", "gclid": "abc"} and c.source == "Website form"


# ─── the website widget and WhatsApp ads ──────────────────────────
def test_the_widget_keeps_where_the_visitor_first_came_from(client, make_user, run):
    u = make_user()
    bot = u.bot()
    first = {"utm_source": "facebook", "utm_campaign": "diwali", "utm_term": "<script>alert(1)</script>", "landing_page": "https://sunrise.in/offer",
             "referrer": "https://l.facebook.com/", "secret": "x", "nested": {"a": 1}, "gclid": True, "headline": "Free flat today", "channel": "whatsapp_ad"}
    session = f"widget-session-ai-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/chat/variables", json={"bot_id": bot, "visitor_session_id": session, "variable_name": "name", "variable_value": "Hema", "origin": first}).status_code == 200
    client.post("/api/chat/variables", json={"bot_id": bot, "visitor_session_id": session, "variable_name": "phone", "variable_value": "98765 00231",
                                            "origin": {"utm_source": "newsletter"}})

    async def kept():
        async with async_session() as db:
            return (await db.execute(select(Conversation.origin).where(Conversation.visitor_session_id == session))).scalar_one()
    expected = {"channel": "website", "utm_source": "facebook", "utm_campaign": "diwali", "utm_term": "<script>alert(1)</script>",
                "landing_page": "https://sunrise.in/offer", "referrer": "https://l.facebook.com/"}
    assert run(kept) == expected                                     # the first touch, as plain text, only what's known
    run(_settled)
    [lead] = client.get("/api/crm/leads", headers=u.h()).json()["items"]
    assert lead["origin"] == expected
    assert client.post("/api/chat/variables", json={"bot_id": bot, "visitor_session_id": session, "variable_name": "x", "variable_value": "y", "origin": ["a"]}).status_code == 422


def test_a_whatsapp_ad_is_kept_on_the_lead_and_told_to_the_assistant(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    tapped = {"source_url": "https://fb.me/2bhk", "source_id": "120208", "source_type": "ad", "headline": "2BHK in Anna Nagar from 45 lakh",
              "body": "Book a site visit this weekend", "ctwa_clid": "ARAk-test"}
    post(client, body(pid, text_msg("Is it still available?", sender=sender, referral=tapped)))
    assert run(wait_for(lambda: len(meta.prompts) == 1, 4))
    assert '"2BHK in Anna Nagar from 45 lakh" / "Book a site visit this weekend"' in meta.prompts[0]["system"]
    post(client, body(pid, text_msg("And parking?", sender=sender, referral={**tapped, "headline": "Another ad"})))
    assert run(wait_for(lambda: len(meta.prompts) == 2, 4))
    assert "2BHK in Anna Nagar from 45 lakh" in meta.prompts[1]["system"] and "Another ad" not in meta.prompts[1]["system"]   # the ad that brought them stays theirs
    run(_settled)
    [lead] = client.get("/api/crm/leads", headers=u.h()).json()["items"]
    assert lead["origin"] == {"channel": "whatsapp_ad", "ad_id": "120208", "ad_url": "https://fb.me/2bhk", "headline": "2BHK in Anna Nagar from 45 lakh",
                              "ad_text": "Book a site visit this weekend", "ctwa_clid": "ARAk-test"}       # the first ad stays theirs
    story = client.get(f"/api/crm/leads/{lead['id']}", headers=u.h()).json()["timeline"]
    chat = next(t for t in story if t["kind"] == "chat")
    assert chat["text"] == "WhatsApp: Is it still available?" and chat["chat_link"].startswith("/dashboard/whatsapp/inbox?chat=")


def test_an_ordinary_whatsapp_chat_has_no_ad(client, make_user, meta, run):
    u = make_user()
    pid, sender = _pid(), _sender()
    connect(client, u, u.bot(), pid)
    post(client, body(pid, text_msg("Hello", sender=sender)))
    assert run(wait_for(lambda: len(meta.prompts) == 1, 4))
    assert "WhatsApp ad" not in meta.prompts[0]["system"]


# ─── junk ──────────────────────────────────────────────────────
def test_junk_is_kept_marked_and_told_to_nobody(client, business, run, sent, fired):
    u = business()
    for phone in ("9999999999", "99999 99999"):
        client.post(f"/api/leads/in/{u.code}/form", json={"name": "Test", "phone": phone, "message": "Price?"})
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Temp", "email": "temp@mailinator.com"})
    run(_settled)
    junk = run(_all, Contact, u.bot_id)
    assert len(junk) == 3 and {c.quality for c in junk} == {"junk"}                          # kept, each on its own: a fake number joins nobody together
    assert [c.e164 for c in junk if c.details.get("Phone they gave")] == [None, None]
    assert sent == [] and fired == []
    for c in junk:
        assert run(_events, c.id)[0].kind == "junk" and not run(_all_tasks, c.id)
    assert {r.note for r in run(_all, LeadIntake, u.bot_id)} == {"Marked as junk (the number can't be real): nobody was told or contacted",
                                                                 "Marked as junk (a throwaway email address): nobody was told or contacted"}
    shown = client.get("/api/crm/leads", headers=u.h()).json()
    assert shown["total"] == 0 and shown["junk"] == 3
    assert client.get("/api/crm/leads", params={"quality": "junk"}, headers=u.h()).json()["total"] == 3
    queues = client.get("/api/crm/queues", headers=u.h()).json()
    assert not any(queues[q] for q in ("new", "no_next", "overdue", "today"))
    lead = client.get(f"/api/crm/leads/{junk[0].id}", headers=u.h()).json()
    assert lead["quality"] == "junk" and lead["junk_reason"] == "The number can't be real"
    report = client.get("/api/crm/reports", headers=u.h()).json()
    assert report["junk"] == 3 and report["leads"] == 0                                       # counted apart, not as leads


async def _all_tasks(contact_id):
    async with async_session() as db:
        return (await db.execute(select(LeadTask).where(LeadTask.contact_id == contact_id))).scalars().all()


def test_a_real_email_with_a_made_up_number_is_a_real_lead(client, business, run, sent):
    u = business()
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Nila", "phone": "1234567890", "email": "nila@buyers.in"})
    run(_settled)
    [c] = run(_all, Contact, u.bot_id)
    assert c.quality is None and c.e164 is None and c.email == "nila@buyers.in" and c.details["Phone they gave"] == "1234567890"
    assert len(alerts(sent)) == 1 and run(_all, CallbackJob, u.bot_id) == []                   # nobody rings a number nobody has


def test_a_manager_can_overrule_the_junk_filter(client, business, joined, run, sent):
    u = business()
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Temp Mail", "email": "real.person@mailinator.com"})
    run(_settled)
    [c] = run(_all, Contact, u.bot_id)
    seller = joined(u)
    assert client.post(f"/api/crm/leads/{c.id}/real", headers=seller.h(u.id)).status_code == 403
    assert client.post(f"/api/crm/leads/{c.id}/real", headers=u.h()).status_code == 200
    assert client.post(f"/api/crm/leads/{c.id}/real", headers=u.h()).status_code == 409
    lead = client.get(f"/api/crm/leads/{c.id}", headers=u.h()).json()
    assert lead["quality"] == "ok" and lead["enquiry_days_left"] == 7 and [t["kind"] for t in lead["timeline"]][:1] == ["real"]
    assert "Temp Mail" in [x["name"] for x in client.get("/api/crm/queues", headers=u.h()).json()["new"]]
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Temp Mail", "email": "real.person@mailinator.com", "message": "Me again"})
    run(_settled)
    again = run(_all, Contact, u.bot_id)[0]
    assert again.quality == "ok" and [e.kind for e in run(_events, c.id)] == ["junk", "real", "asked_again"]   # not marked again
    assert alerts(sent) == []                                                                 # the manager who overruled it has them already


def test_a_chat_lead_nobody_could_reach_is_junk(client, make_user, run, monkeypatch):
    started = []

    async def fire_for(owner_id, bot_id, trigger, phone, address, value=None):
        started.append(address or phone)
    monkeypatch.setattr(journeys, "fire_for", fire_for)
    u = make_user()
    bot = u.bot()

    async def welcome_on():
        async with async_session() as db:
            db.add(IntegrationSettings(user_id=u.id, email_alerts=True, whatsapp_language="en", email_automations={"chat_lead": {"enabled": True, "steps": [
                {"delay": "now", "subject": "Thanks", "body": "Hi {{name}}"}]}}))
            await db.commit()
    run(welcome_on)
    for session, name, value in (("junk-1", "phone", "1234567890"), ("junk-2", "email", "someone@mailinator.com"), ("real-1", "email", "real.person@buyers.in")):
        client.post("/api/chat/variables", json={"bot_id": bot, "visitor_session_id": session, "variable_name": name, "variable_value": value})
    run(_settled)

    async def logs():
        async with async_session() as db:
            return (await db.execute(select(NotificationLog.kind).where(NotificationLog.user_id == u.id))).scalars().all()

    async def welcomes():
        async with async_session() as db:
            return (await db.execute(select(EmailJob.to_email).where(EmailJob.user_id == u.id))).scalars().all()
    assert run(logs).count("lead_email") == 1                                                   # only the real one's alert
    assert client.get("/api/crm/leads", headers=u.h()).json()["junk"] == 2
    assert started == ["real.person@buyers.in"] and run(welcomes) == ["real.person@buyers.in"]


def test_someone_who_called_isnt_junk_whatever_they_type(client, business, run, sent):
    u = business()

    async def caller():
        async with async_session() as db:
            db.add(Contact(user_id=u.id, bot_id=u.bot_id, email="caller@mailinator.com", details={}, calls=2))
            await db.commit()
    run(caller)
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Caller", "email": "caller@mailinator.com"})
    run(_settled)
    assert run(_all, Contact, u.bot_id)[0].quality is None and len(alerts(sent)) == 1


# ─── the same person again ───────────────────────────────────────
def test_the_same_person_twice_in_a_day_is_told_once(client, business, run, sent, fired):
    u = business()
    for ask, ticked in (("A 2BHK", ""), ("Parking?", "yes")):
        client.post(f"/api/leads/in/{u.code}/form", json={"name": "Priya", "phone": "98765 00241", "email": "priya@buyers.in", "message": ask, "newsletter": ticked})
        run(_settled)
    [c] = run(_all, Contact, u.bot_id)
    assert len(alerts(sent)) == 1 and fired.count(("new_lead", ("form",))) == 1
    assert run(_all, LeadIntake, u.bot_id)[1].note == "They asked again within a day: the team has them already, so nobody was told again"
    assert [e.kind for e in run(_events, c.id)] == ["came_in", "asked_again"]

    async def agreed():
        async with async_session() as db:
            return (await db.execute(select(Consent.status).where(Consent.bot_id == u.bot_id, Consent.email == "priya@buyers.in"))).scalars().all()
    assert run(agreed) == ["given"]                                                              # their own tick is kept, even the second time

    async def a_day_later():
        async with async_session() as db:
            await db.execute(update(Contact).where(Contact.id == c.id).values(last_enquiry_at=datetime.utcnow() - timedelta(hours=25)))
            await db.commit()
    run(a_day_later)
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Priya", "phone": "98765 00241", "message": "Still there?"})
    run(_settled)
    assert len(alerts(sent)) == 2


# ─── old leads from a list ───────────────────────────────────────
CSV = """Name,Phone,Email,Source,Stage,Notes,Tags
Ravi,98765 00301,,Expo 2025,interested,Wants a 3BHK,vip; expo
Meena,,meena@buyers.in,,customer,,
Fake,9999999999,,,,,
Bad,,not-an-email,,,,
Ravi again,98765 00301,,,,,
Mixed,1234567890,mixed@buyers.in,,,,
"""


def test_old_leads_are_imported_and_nobody_is_contacted(client, business, joined, make_user, run, sent, fired):
    u = business()
    done = client.post("/api/crm/import", json={"bot_id": u.bot_id, "csv": CSV, "source": "Old sheet"}, headers=u.h()).json()
    assert (done["added"], done["existing"], done["skipped_count"]) == (3, 1, 2)
    assert [s["why"] for s in done["skipped"]] == ["The number can't be real", "No valid phone number or email"]
    leads = {c.name: c for c in run(_all, Contact, u.bot_id)}
    ravi, meena = leads["Ravi"], leads["Meena"]
    assert (leads["Mixed"].e164, leads["Mixed"].email) == (None, "mixed@buyers.in")         # a real email kept, the number nobody has left out
    assert (ravi.source, ravi.stage, ravi.notes, ravi.tags, ravi.quality, ravi.origin, ravi.last_enquiry_at) == ("Expo 2025", "interested", "Wants a 3BHK", ["expo", "vip"], "old", {"channel": "import"}, None)
    assert (meena.source, meena.stage, meena.lead_status) == ("Old sheet", "customer", "customer")
    run(_settled)
    assert sent == [] and fired == [] and run(_all, CallbackJob, u.bot_id) == [] and run(_all, EmailJob, u.bot_id) == []
    assert not run(_all_tasks, ravi.id) and [e.kind for e in run(_events, ravi.id)] == ["imported"]
    queues = client.get("/api/crm/queues", headers=u.h()).json()
    assert not any(queues[q] for q in ("new", "no_next"))                                    # an old list isn't new enquiries
    assert client.get("/api/crm/leads", headers=u.h()).json()["total"] == 3
    assert client.get("/api/crm/reports", headers=u.h()).json()["leads"] == 0
    assert client.get(f"/api/crm/leads/{ravi.id}", headers=u.h()).json()["enquiry_days_left"] is None

    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Ravi", "phone": "98765 00301", "message": "Is the 3BHK still there?"})   # asking now: a lead like any other
    run(_settled)
    now = client.get(f"/api/crm/leads/{ravi.id}", headers=u.h()).json()
    assert now["quality"] is None and now["enquiry_days_left"] == 7 and len(now["tasks"]) == 1

    seller, stranger = joined(u), make_user("Stranger")
    assert client.post("/api/crm/import", json={"bot_id": u.bot_id, "csv": CSV}, headers=seller.h(u.id)).status_code == 403
    assert client.post("/api/crm/import", json={"bot_id": u.bot_id, "csv": CSV}, headers=stranger.h()).status_code == 404
    assert client.post("/api/crm/import", json={"bot_id": u.bot_id, "csv": "Name,City\nA,B\n"}, headers=u.h()).status_code == 400


def test_nimmi_finds_the_junk_when_asked(client, business, run):
    from agent import registry
    from auth import AuthContext
    u = business()
    client.post(f"/api/leads/in/{u.code}/form", json={"name": "Fake", "phone": "0000000000"})
    run(_settled)
    tc = registry.ToolContext(ctx=AuthContext(u.id, u.id, "owner"), run_id="r", thread_id="t", screen={})
    import json
    usual = json.loads(run(registry.run, tc, "find_leads", {}).text)
    junk = json.loads(run(registry.run, tc, "find_leads", {"junk": True}).text)
    assert (usual["total"], usual["junk"], junk["total"], junk["leads"][0]["name"]) == (0, 1, 1, "Fake")
    sources = run(registry.run, tc, "email_lead_sources", {"assistant_id": u.bot_id})
    assert sources.ok and u.key not in sources.text and "/google" in sources.text                 # Google's key never goes to an AI model


# ─── the pieces ─────────────────────────────────────────────────
def test_only_known_parts_of_where_they_came_from_are_kept():
    assert lead_origin.clean({"utm_source": "x\n\ty", "landing_page": "a" * 500, "unknown": "z", "gclid": False, "ad_id": 120, "channel": "spaceship"}) == \
        {"utm_source": "x y", "landing_page": "a" * 300, "ad_id": "120"}
    assert lead_origin.clean(["a"]) is None and lead_origin.clean({"secret": 1}) is None
    assert lead_origin.from_whatsapp("not a referral") is None


@pytest.mark.parametrize("phone,mail,why", [
    ("9999999999", None, "The number can't be real"), ("+91 12345 67890", None, "The number can't be real"), ("0987654321", None, "The number can't be real"),
    (None, "x@mailinator.com", "A throwaway email address"), ("9999999999", "x@mailinator.com", "The number can't be real"),
    ("98765 00251", None, None), ("98765 43210", None, None), ("044 2812 3456", None, None), ("+1 415 555 0199", None, None),
    ("9999999999", "real@buyers.in", None), ("98765 00251", "x@mailinator.com", None), (None, None, None), ("12", None, None)])
def test_what_counts_as_junk(phone, mail, why):
    assert quality.why_junk(phone, mail) == why
