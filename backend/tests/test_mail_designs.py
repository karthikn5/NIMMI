"""
Email, phase 1 (mail_plan.md): designed emails (blocks, brand, placeholders with fallbacks), which design an assistant
uses (its own, per language, the workspace's old text, the ready-made one), the welcome email after a chat with the
AI's note and the files that fit (written in the background, numbers it can't back up removed, counted as an AI
reply), the wait for a quiet chat, Starter's plain welcome, tracked links and downloads, and the dashboard's API.
"""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy.future import select

from database import async_session
from backend.models import (AiReplyUsage, Bot, Conversation, EmailJob, EmailLink, EmailTemplate, IntegrationSettings, Message,
                            Subscription, WhatsAppFile, WhatsAppNumber)
from mail import compose, designs, render, setup
from notify import automations, email, events

BASE = {
    "email_alerts": True, "alert_email": "", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
    "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "",
}


def _capture(monkeypatch):
    sent = []

    async def fake_deliver(to, subject, text, html_body=None, **more):
        sent.append({"to": to, "subject": subject, "text": text, "html": html_body, **more})
        return email.Delivery(True, id=f"re_{len(sent)}")
    monkeypatch.setattr(email, "deliver", fake_deliver)
    return sent


# ─── the renderer ────────────────────────────────────────────────

def test_a_design_becomes_an_email_mail_apps_show_well():
    design = {"subject": "Thanks, {{first_name|there}}", "blocks": [
        {"type": "text", "text": "Hi {{first_name|}},\n\nSee https://sunrise.in/homes for more."},
        {"type": "ai_note"}, {"type": "files"},
        {"type": "button", "label": "Chat on WhatsApp", "action": "whatsapp"},
        {"type": "button", "label": "Book a time", "action": "book"},  # no address for it: left out
        {"type": "signature"}]}
    tracked = []

    def link(url, kind, label):
        tracked.append((kind, url))
        return f"https://api.test/l/{len(tracked)}"
    made = render.email(design, {"first_name": "", "ai_note": "You asked about 2BHK homes.", "files": [],
                                 "actions": {"whatsapp": "https://wa.me/919876543210"}},
                        render.brand_of({"color": "#ffdd00", "logo_url": "https://cdn.test/logo.svg"}, "Sunrise Homes"),
                        unsubscribe_url="https://api.test/unsub", link=link)
    assert made.subject == "Thanks, there"
    assert ">Hi,</p>" in made.html and "Hi ," not in made.html  # no name: no stray space
    assert "You asked about 2BHK homes." in made.html and made.preheader == "You asked about 2BHK homes."
    assert "Book a time" not in made.html and "Chat on WhatsApp: https://api.test/l/" in made.text
    assert ("link", "https://sunrise.in/homes") in tracked and ("whatsapp", "https://wa.me/919876543210") in tracked
    assert "background:#ffdd00" in made.html and "color:#1c1719;text-decoration:none" in made.html  # dark text on yellow
    assert "logo.svg" not in made.html and "Sunrise Homes" in made.html  # mail apps don't show SVG logos: the name instead
    assert "Unsubscribe" in made.html and made.text.endswith("Unsubscribe: https://api.test/unsub")
    assert len(made.html) < render.GMAIL_CLIPS


def test_which_design_an_email_uses(client, make_user, run):
    u = make_user()
    bot = u.bot("Sunrise")

    async def design(language):
        async with async_session() as db:
            return await setup.design_for(db, u.id, bot, "welcome", language)
    ta = run(design, "ta")
    assert ta["language"] == "ta" and "வணக்கம்" in ta["blocks"][0]["text"] and not ta["saved"]

    # The workspace's own first email after a chat, written before designs: their words stay.
    client.put("/api/integrations", json={**BASE, "reply_to": "hi@sunrise.in", "automations": {"chat_lead": {
        "enabled": True, "steps": [{"delay": "now", "subject": "Hello from Sunrise", "body": "Hi {{name}}, our brochure is attached."}]}}},
               headers=u.h())
    own = run(design, "en")
    assert own["subject"] == "Hello from Sunrise" and own["blocks"][0]["text"].startswith("Hi {{name}}, our brochure")

    saved = client.put(f"/api/email/designs/{bot}/welcome", json={"language": "en", "subject": "Welcome!", "blocks": [
        {"type": "text", "text": "Hello"}, {"type": "script", "text": "<b>x</b>"}, {"type": "button", "label": "Site", "action": "link",
                                                                                     "url": "https://sunrise.in"}]}, headers=u.h())
    assert saved.status_code == 200 and [b["type"] for b in saved.json()["blocks"]] == ["text", "button"]  # unknown blocks dropped
    assert run(design, "ta")["subject"] == "Welcome!"  # their English design over the ready-made Tamil
    reset = client.delete(f"/api/email/designs/{bot}/welcome?language=en", headers=u.h()).json()
    assert reset["subject"] == "Hello from Sunrise" and not reset["saved"]

    assert designs.language_of("ஒரு 2BHK வீடு வேண்டும்") == "ta" and designs.language_of("मुझे घर चाहिए") == "hi"
    assert designs.language_of("enakku oru veedu venum") == "en"  # Tanglish stays in English letters


def test_a_welcome_note_in_another_language_is_left_out():
    from mail import designs
    assert designs.written_in("You asked about 2BHK homes.", "en") and not designs.written_in("You asked about 2BHK homes.", "ta")


# ─── the welcome email ───────────────────────────────────────────

@pytest.fixture
def writing(monkeypatch):
    """The welcome email as on live: it waits for its AI parts (a scripted model writes them)."""
    monkeypatch.setattr(compose, "needs_writing", lambda kind: kind == "chat_lead")
    asked = []

    async def complete(bot, system, user, max_tokens=600, urgent=False):
        asked.append((system, user))
        return json.dumps({"note": "You asked about 2BHK homes near Anna Nagar. Prices start at 45 lakh, and 3 homes are ready.",
                           "files": [1]})

    async def knowledge(bot):
        return "Sunrise Homes builds 2BHK and 3BHK homes in Anna Nagar. 3 homes are ready to move in."
    from voice import llm
    monkeypatch.setattr(llm, "_complete", complete)
    monkeypatch.setattr(llm, "call_knowledge", knowledge)
    return asked


def _chat(run, bot, messages, captured):
    async def add():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id=f"s{datetime.utcnow().timestamp()}", captured_data=captured)
            db.add(conv)
            await db.flush()
            for role, text in messages:
                db.add(Message(conversation_id=conv.conversation_id, role=role, content=text))
            await db.commit()
            return conv.conversation_id
    return run(add)


def _job(run, owner, conv_id):
    async def get():
        async with async_session() as db:
            return (await db.execute(select(EmailJob).where(EmailJob.user_id == owner, EmailJob.ref_id == conv_id))).scalars().first()
    return run(get)


def _setup_business(client, run, u, bot):
    client.put("/api/integrations", json={**BASE, "sender_name": "Sunrise Homes", "reply_to": "sales@sunrise.in",
                                          "automations": {"chat_lead": {"enabled": True, "steps": [{
                                              "delay": "now", "subject": "Thanks {{name}}", "body": "Hi {{name}}"}]}}}, headers=u.h())
    client.delete(f"/api/email/designs/{bot}/welcome?language=en", headers=u.h())

    async def extras():
        async with async_session() as db:
            db.add(WhatsAppFile(user_id=u.id, bot_id=None, name="Anna Nagar brochure", when_to_send="When someone asks about homes",
                                kind="document", mime="application/pdf", filename="brochure.pdf", size=1_300_000,
                                stored="local:x/brochure.pdf"))
            db.add(WhatsAppNumber(user_id=u.id, bot_id=bot, display_number="+91 98400 12345", phone_number_id=f"pn{bot[:8]}",
                                  waba_id="w", access_token="t", status="connected"))
            await db.commit()
    run(extras)


def test_the_welcome_email_has_the_ais_note_and_the_files_that_fit(client, make_user, run, monkeypatch, writing):
    u = make_user()
    bot = u.bot("Sunrise")
    _setup_business(client, run, u, bot)
    # Their own design (the ready-made one, but theirs): the note and files have their places in it.
    ready = designs.default("welcome")
    client.put(f"/api/email/designs/{bot}/welcome", json={"language": "en", "subject": "Thanks, {{first_name|there}}",
                                                         "blocks": ready["blocks"]}, headers=u.h())
    sent = _capture(monkeypatch)
    conv = _chat(run, bot, [("user", "Do you have 2BHK homes near Anna Nagar?"), ("assistant", "Yes, three are ready.")],
                 {"Name": "Karthi R", "Email": "karthi@example.com"})
    run(events.lead_captured, conv)
    job = _job(run, u.id, conv)
    assert job.compose_state == "pending"

    run(automations.process_due)
    assert not [m for m in sent if m["to"] == "karthi@example.com"]  # still being written: it waits

    run(compose.prepare_due)
    job = _job(run, u.id, conv)
    assert job.compose_state == "done"
    # The price the knowledge doesn't have is gone with its sentence; what the knowledge says stays.
    assert job.merge_data["ai_note"] == "You asked about 2BHK homes near Anna Nagar."
    assert len(job.merge_data["file_ids"]) == 1
    system, user = writing[0]
    assert "Anna Nagar brochure" in system and "Do you have 2BHK homes near Anna Nagar?" in user

    run(automations.process_due)
    m = next(m for m in sent if m["to"] == "karthi@example.com")
    assert m["subject"] == "Thanks, Karthi" and "You asked about 2BHK homes near Anna Nagar." in m["html"]
    assert "Anna Nagar brochure" in m["html"] and "(1.2 MB)" in m["html"] and "/api/email/l/" in m["html"]
    assert "Chat on WhatsApp" in m["html"] and "Book a time" not in m["html"]  # no booking page yet: left out
    assert "Prices start" not in m["html"]

    async def used():
        async with async_session() as db:
            row = (await db.execute(select(AiReplyUsage).where(AiReplyUsage.bot_id == bot))).scalars().first()
            links = (await db.execute(select(EmailLink).where(EmailLink.job_id == job.id))).scalars().all()
            return (row.replies if row else 0), {l.kind: l.target for l in links}
    replies, made = run(used)
    assert replies == 1  # an AI-written email counts as one AI reply
    assert made["whatsapp"] == "https://wa.me/919840012345" and made["file"].startswith("file:")


def test_a_welcome_email_whose_writing_stalls_goes_without_it(client, make_user, run, monkeypatch, writing):
    u = make_user()
    bot = u.bot("Sunrise")
    _setup_business(client, run, u, bot)
    sent = _capture(monkeypatch)
    conv = _chat(run, bot, [("user", "Hi")], {"Name": "Asha", "Email": "asha@example.com"})
    run(events.lead_captured, conv)

    async def stale():
        async with async_session() as db:
            job = (await db.execute(select(EmailJob).where(EmailJob.ref_id == conv))).scalars().first()
            job.created_at = datetime.utcnow() - compose.WAIT - timedelta(seconds=5)
            await db.commit()
    run(stale)
    run(automations.process_due)
    m = next(m for m in sent if m["to"] == "asha@example.com")
    assert m["subject"] == "Thanks Asha" and "Hi Asha" in m["text"]


def test_the_welcome_email_waits_for_the_chat_to_go_quiet(client, make_user, run, monkeypatch):
    monkeypatch.setattr(automations, "QUIET", 120)
    u = make_user()
    bot = u.bot("Sunrise")
    _setup_business(client, run, u, bot)
    conv = _chat(run, bot, [], {"Email": "ravi@example.com"})
    run(events.lead_captured, conv)
    first = _job(run, u.id, conv).send_at

    async def more():
        async with async_session() as db:
            await compose.chat_went_on(db, conv)
            await db.commit()
    run(more)
    assert _job(run, u.id, conv).send_at >= first  # pushed on while they chat

    async def long_ago():
        async with async_session() as db:
            job = (await db.execute(select(EmailJob).where(EmailJob.ref_id == conv))).scalars().first()
            job.created_at = datetime.utcnow() - timedelta(minutes=11)
            job.send_at = datetime.utcnow() - timedelta(minutes=1)
            await db.commit()
    run(long_ago)
    run(more)
    assert _job(run, u.id, conv).send_at < datetime.utcnow()  # never more than 10 minutes after their address


def test_starter_sends_the_welcome_email_without_the_ais_note_or_files(client, make_user, run, monkeypatch, writing):
    monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")
    u = make_user()
    bot = u.bot("Sunrise")

    async def starter():
        async with async_session() as db:
            db.add(Subscription(user_id=u.id, bot_id=bot, tier="starter", period="monthly", plan_name="Starter monthly",
                                price_paid=999, credits_granted=1, start_date=datetime.utcnow() - timedelta(days=1),
                                end_date=datetime.utcnow() + timedelta(days=29), status="active", razorpay_order_id="o_starter"))
            await db.commit()
    run(starter)
    _setup_business(client, run, u, bot)
    sent = _capture(monkeypatch)
    conv = _chat(run, bot, [("user", "Do you have 2BHK homes?")], {"Name": "Meena", "Email": "meena@example.com"})
    run(events.lead_captured, conv)
    assert _job(run, u.id, conv).compose_state is None  # nothing for the AI to write on Starter
    run(automations.process_due)
    m = next(m for m in sent if m["to"] == "meena@example.com")
    assert "Hi Meena" in m["text"] and "brochure" not in m["html"] and writing == []


# ─── links in emails ─────────────────────────────────────────────

def test_links_and_files_in_emails_are_counted_then_opened(client, make_user, run, monkeypatch):
    from whatsapp import storage
    u = make_user()

    async def rows():
        async with async_session() as db:
            f = WhatsAppFile(user_id=u.id, name="Price list", kind="document", mime="application/pdf", filename="price list.pdf",
                             size=10, stored="local:x/p.pdf")
            job = EmailJob(user_id=u.id, kind="chat_lead", ref_id="r-links", to_email="a@x.in", subject="s", body="b",
                           status="sent", send_at=datetime.utcnow())
            db.add_all([f, job])
            await db.flush()
            db.add_all([EmailLink(token="tok_link", user_id=u.id, job_id=job.id, kind="link", target="https://sunrise.in/homes"),
                        EmailLink(token="tok_file", user_id=u.id, job_id=job.id, kind="file", target=f"file:{f.id}"),
                        EmailLink(token="tok_bad", user_id=u.id, kind="link", target="javascript:alert(1)")])
            await db.commit()
            return job.id
    job_id = run(rows)

    async def load(stored):
        return b"%PDF-1.4 prices"
    monkeypatch.setattr(storage, "load", load)
    r = client.get("/api/email/l/tok_link", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "https://sunrise.in/homes"
    f = client.get("/api/email/l/tok_file")
    assert f.status_code == 200 and f.content == b"%PDF-1.4 prices" and 'filename="price list.pdf"' in f.headers["content-disposition"]
    assert client.get("/api/email/l/tok_bad", follow_redirects=False).status_code == 404
    assert client.get("/api/email/l/nope").status_code == 404

    async def counted():
        from mail import clicks
        from backend.models import EmailClick
        assert await clicks.settle_due(datetime.utcnow() + clicks.SETTLE + timedelta(seconds=1)) >= 2  # a click counts once it's settled
        async with async_session() as db:
            link = await db.get(EmailLink, "tok_link")
            job = await db.get(EmailJob, job_id)
            refused = (await db.execute(select(EmailClick).where(EmailClick.token == "tok_bad"))).scalars().all()
            return link.clicks, job.clicked_at is not None, len(refused)
    assert run(counted) == (1, True, 0), "a link that doesn't open isn't a click"


# ─── the dashboard's API ─────────────────────────────────────────

def test_an_assistant_has_its_own_emails_over_the_workspaces(client, make_user, run, monkeypatch):
    u = make_user()
    a, b = u.bot("Clinic"), u.bot("Shop")
    client.put("/api/integrations", json={**BASE, "reply_to": "hi@biz.in"}, headers=u.h())
    on = {"chat_lead": {"enabled": True, "steps": [{"delay": "now", "subject": "Hi", "body": "Thanks"}]}}
    r = client.put(f"/api/email/setup/{a}", json={"automations": on, "settings": {"after_call": {"inbound": "review"}}}, headers=u.h())
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["own_automations"] and s["automations"]["chat_lead"]["enabled"] and s["settings"]["after_call"]["inbound"] == "review"
    assert client.get(f"/api/email/setup/{b}", headers=u.h()).json()["automations"]["chat_lead"]["enabled"] is False
    bad = client.put(f"/api/email/setup/{a}", json={"settings": {"after_call": {"inbound": "sometimes"}}}, headers=u.h())
    assert bad.status_code == 400
    sent = _capture(monkeypatch)

    async def leads():
        for bot, addr in ((a, "one@example.com"), (b, "two@example.com")):
            async with async_session() as db:
                conv = Conversation(bot_id=bot, visitor_session_id=f"s-{addr}", captured_data={"Email": addr})
                db.add(conv)
                await db.commit()
            await events.lead_captured(conv.conversation_id)
        await automations.process_due()
    run(leads)
    assert [m["to"] for m in sent if m["to"] in ("one@example.com", "two@example.com")] == ["one@example.com"]  # the clinic's only

    preview = client.post(f"/api/email/designs/{a}/welcome/preview", json=designs.default("welcome", "ta") | {"language": "ta"}, headers=u.h())
    assert preview.status_code == 200 and "Priya" in preview.json()["html"] and "வணக்கம்" in preview.json()["html"]
    test = client.post(f"/api/email/designs/{a}/welcome/test", json=designs.default("welcome") | {"language": "en"}, headers=u.h())
    assert test.status_code == 200 and test.json()["to"] == u.email and sent[-1]["subject"].startswith("[Test] ")
    other = make_user()
    assert client.get(f"/api/email/setup/{a}", headers=other.h()).status_code == 404


def test_starter_can_turn_on_the_welcome_email_but_not_the_rest(client, make_user, run, monkeypatch):
    monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")
    u = make_user()
    bot = u.bot("Desk")

    async def starter():
        async with async_session() as db:
            db.add(Subscription(user_id=u.id, bot_id=bot, tier="starter", period="monthly", plan_name="Starter monthly",
                                price_paid=999, credits_granted=1, start_date=datetime.utcnow() - timedelta(days=1),
                                end_date=datetime.utcnow() + timedelta(days=29), status="active", razorpay_order_id="o_st2"))
            db.add(IntegrationSettings(user_id=u.id, email_alerts=True, reply_to="hi@desk.in"))
            await db.commit()
    run(starter)
    one = {"chat_lead": {"enabled": True, "steps": [{"delay": "now", "subject": "Hi", "body": "Thanks"}]}}
    assert client.put(f"/api/email/setup/{bot}", json={"automations": one}, headers=u.h()).status_code == 200
    two = {"chat_lead": {"enabled": True, "steps": one["chat_lead"]["steps"] + [{"delay": "2d", "subject": "Again", "body": "Hi"}]}}
    assert client.put(f"/api/email/setup/{bot}", json={"automations": two}, headers=u.h()).status_code == 402
    ai = client.put(f"/api/email/setup/{bot}", json={"settings": {"after_call": {"inbound": "review"}}}, headers=u.h())
    assert ai.status_code == 402 and "Growth" in ai.json()["detail"]
    assert client.put(f"/api/email/designs/{bot}/welcome", json={"language": "en", "subject": "Hello", "blocks": [
        {"type": "text", "text": "Hi"}]}, headers=u.h()).status_code == 200
