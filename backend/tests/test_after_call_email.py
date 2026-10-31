"""
Email, phase 1 (mail_plan.md): the AI's email after a phone call. Per direction it's off, review first or automatic; it's
written from the call and the knowledge, in the language of the call, with what's really booked; a second model checks
it; invented numbers go; drafts wait for the team, who edit, send, discard or ask for it again; unhappy callers and failed
checks wait for a person even on automatic; questions it can't answer go to Questions; after 20 approvals it offers
automatic; the fixed call emails step aside; and nothing goes to anyone who shouldn't get it.
"""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.future import select

from backend.models import (AiReplyUsage, CallbackJob, CallLog, Contact, DncEntry, EmailJob, EmailLink, KnowledgeGap, Meeting, Subscription,
                            VoiceAgent, WhatsAppFile)
from database import async_session
from mail import after_call, compose, setup
from notify import automations, email, events
from voice import llm

BASE = {
    "email_alerts": True, "alert_email": "", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
    "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "", "reply_to": "hello@sunrise.in",
}
KNOWLEDGE = "Sunrise Homes builds 2BHK homes in Anna Nagar from 45 lakh. Every home has one covered parking space."
TALK = [{"speaker": "agent", "text": "Hello, this is Sunrise Homes."},
        {"speaker": "caller", "text": "Do you have 2BHK homes in Anna Nagar? Is parking included? I'm Priya."},
        {"speaker": "agent", "text": "Yes, from 45 lakh, with one covered parking space. I'll send the brochure."}]
WRITTEN = {"recap": ["You asked about 2BHK homes in Anna Nagar."],
           "answers": [{"q": "Is parking included?", "a": "Yes, every home has one covered parking space."}],
           "unanswered": [], "next_step": "", "files": []}


@pytest.fixture(autouse=True)
def tidy(run):
    yield

    async def clean():
        async with async_session() as db:
            await db.execute(delete(EmailJob).where(EmailJob.automation.in_(("after_call", "call_lead", "goal_met"))))
            await db.commit()
    run(clean)


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def deliver(to, subject, text, html_body=None, **more):
        if (more.get("tags") or {}).get("kind") == "customer":  # not the team's own alerts
            out.append({"to": to, "subject": subject, "text": text, "html": html_body, **more})
        return email.Delivery(True, id=f"re_{len(out)}")
    monkeypatch.setattr(email, "deliver", deliver)
    monkeypatch.setattr(email, "is_configured", lambda: True)
    return out


@pytest.fixture
def model(monkeypatch):
    """A scripted writer and checker. `.write` and `.check` are what they answer; an Exception is raised."""
    class Model:
        write, check = dict(WRITTEN), {"verdict": "ok"}
        asked: list = []
    m = Model()
    m.write, m.check, m.asked = dict(WRITTEN), {"verdict": "ok"}, []

    async def complete(bot, system, user, max_tokens=600, urgent=False):
        m.asked.append((system, user))
        answer = m.check if system.startswith("You check") else m.write
        if isinstance(answer, list):
            answer = answer.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return f"```json\n{json.dumps(answer, ensure_ascii=False)}\n```"

    async def knowledge(bot):
        return KNOWLEDGE
    monkeypatch.setattr(llm, "_complete", complete)
    monkeypatch.setattr(llm, "call_knowledge", knowledge)
    return m


@pytest.fixture
def business(client, make_user):
    def make(mode="review", direction="inbound"):
        u = make_user()
        u.bot_id = u.bot("Sunrise")
        assert client.put("/api/integrations", json=BASE, headers=u.h()).status_code == 200
        r = client.put(f"/api/email/setup/{u.bot_id}", json={"settings": {"after_call": {direction: mode}}}, headers=u.h())
        assert r.status_code == 200, r.text
        return u
    return make


def call_row(u, **more):
    data = {"user_id": u.id, "bot_id": u.bot_id, "direction": "inbound", "channel": "phone", "caller_e164": "+919876543210",
            "outcome": "lead_captured", "language": "en-IN", "summary": "Priya asked about 2BHK homes.",
            "captured": {"Name": "Priya Sharma", "Email": "priya@sunrise-test.in"}, "transcript": TALK, **more}
    return CallLog(**data)


async def _ended(u, **more) -> str:
    """A call ends: the row is saved, then the email is queued, as the pipeline does."""
    async with async_session() as db:
        row = call_row(u, **more)
        db.add(row)
        await db.commit()
        call_id = row.id
    await after_call.queue(call_id)
    return call_id


async def _job(call_id):
    async with async_session() as db:
        return (await db.execute(select(EmailJob).where(EmailJob.ref_id == call_id, EmailJob.automation == "after_call"))).scalars().first()


async def _write_all():
    while await compose._prepare_one():
        pass


# ─── which calls get one ─────────────────────────────────────────

def test_off_by_default_and_the_fixed_emails_go_as_before(client, make_user, run, sent, model):
    u = make_user()
    u.bot_id = u.bot("Sunrise")
    client.put("/api/integrations", json={**BASE, "automations": {"call_lead": {"enabled": True, "steps": [
        {"delay": "now", "subject": "Thanks", "body": "Hi {{name}}"}]}}}, headers=u.h())
    call_id = run(_ended, u)
    assert run(_job, call_id) is None
    run(events.call_completed, call_id)
    run(automations.process_due)
    assert [m["subject"] for m in sent] == ["Thanks"]
    assert model.asked == []


def test_the_fixed_call_emails_step_aside_while_it_is_on_for_that_direction(client, business, run, sent, model):
    u = business("auto", "inbound")
    client.put(f"/api/email/setup/{u.bot_id}", json={"automations": {"call_lead": {"enabled": True, "steps": [
        {"delay": "now", "subject": "Fixed", "body": "Hi {{name}}"}]}}}, headers=u.h())
    call_id = run(_ended, u)
    run(events.call_completed, call_id)
    run(_write_all)
    run(automations.process_due)
    assert [m["subject"] for m in sent] == ["Your call with Sunrise"]

    other = run(_ended, u, direction="outbound", captured={"Email": "ravi@sunrise-test.in"})  # off for outgoing calls
    assert run(_job, other) is None
    run(events.call_completed, other)
    run(automations.process_due)
    assert "Fixed" in [m["subject"] for m in sent]


@pytest.mark.parametrize("more", [{"outcome": "voicemail"}, {"outcome": "opted_out"}, {"outcome": "transferred"}, {"outcome": "no_answer"},
                                  {"outcome": "failed"}, {"channel": "browser"}, {"transcript": [{"speaker": "agent", "text": "Hello?"}]},
                                  {"captured": {}}])
def test_only_calls_where_they_really_talked_and_left_an_address(business, run, model, more):
    u = business("auto")
    assert run(_job, run(_ended, u, **more)) is None


def test_someone_on_the_do_not_call_list_or_unsubscribed_gets_nothing(client, business, run, model, sent):
    u = business("auto")

    async def dnc():
        async with async_session() as db:
            db.add(DncEntry(user_id=u.id, e164="+919876543210"))
            await db.commit()
    run(dnc)
    assert run(_job, run(_ended, u)) is None

    u2 = business("auto")
    client.post("/api/integrations/email/stop", json={"email": "priya@sunrise-test.in"}, headers=u2.h())
    assert run(_job, run(_ended, u2)) is None


def test_the_address_on_file_is_used_unless_remember_callers_is_off(business, run, model):
    u = business("auto")

    async def on_file():
        async with async_session() as db:
            db.add(Contact(user_id=u.id, bot_id=u.bot_id, e164="+919876543210", name="Priya Sharma", email="filed@sunrise-test.in", details={}, calls=1))
            await db.commit()
    run(on_file)
    job = run(_job, run(_ended, u, captured={}))
    assert job.to_email == "filed@sunrise-test.in" and job.merge_data["name"] == "Priya Sharma"

    async def forget_them():
        async with async_session() as db:
            agent = await db.get(VoiceAgent, u.bot_id)
            if agent is None:
                agent = VoiceAgent(bot_id=u.bot_id, user_id=u.id)
                db.add(agent)
            agent.remember_callers = False
            await db.commit()
    run(forget_them)
    assert run(_job, run(_ended, u, captured={})) is None


def test_a_bad_address_shows_in_history_with_the_reason(business, run, model, monkeypatch):
    from mail import address

    async def lookup(domain):
        return False
    monkeypatch.setattr(address, "_lookup", lookup)
    u = business("auto")
    job = run(_job, run(_ended, u))
    assert job.status == "cancelled" and "mail" in job.error.lower()


def test_someone_calling_three_times_in_a_day_gets_three_and_no_more(business, run, model):
    u = business("review")
    ids = [run(_ended, u) for _ in range(4)]
    assert [run(_job, i) is not None for i in ids] == [True, True, True, False]


# ─── writing it ──────────────────────────────────────────────────

def test_review_first_writes_a_draft_and_nothing_goes_until_the_team_approves(client, business, run, sent, model):
    u = business("review")
    call_id = run(_ended, u)
    job = run(_job, call_id)
    assert job.status == "draft" and job.compose_state == "pending"

    listed = client.get("/api/email/drafts", headers=u.h()).json()
    assert listed["total"] == 1 and listed["items"][0]["state"] == "writing"
    assert client.post(f"/api/email/drafts/{job.id}/send", headers=u.h()).status_code == 409  # still being written

    run(_write_all)
    run(automations.process_due)
    assert sent == []
    draft = client.get(f"/api/email/drafts/{job.id}", headers=u.h()).json()
    assert draft["state"] == "ready" and draft["note"] is None and draft["name"] == "Priya Sharma"
    assert draft["recap"] == WRITTEN["recap"] and draft["direction"] == "inbound"
    assert "2BHK homes in Anna Nagar" in draft["html"] and draft["shown_subject"] == "Your call with Sunrise"
    assert "Hi Priya," in draft["html"] and "covered parking" in draft["html"]

    assert client.post(f"/api/email/drafts/{job.id}/send", headers=u.h()).json() == {"status": "sending"}
    assert client.get("/api/email/drafts", headers=u.h()).json()["total"] == 0
    run(automations.process_due)
    assert len(sent) == 1 and sent[0]["to"] == "priya@sunrise-test.in" and sent[0]["reply_to"] == "hello@sunrise.in"
    assert "covered parking space" in sent[0]["text"] and sent[0]["unsubscribe_url"]
    assert client.post(f"/api/email/drafts/{job.id}/send", headers=u.h()).status_code == 404  # once

    row = run(_job, call_id)
    assert row.status == "sent" and row.subject == "Your call with Sunrise" and "covered parking" in row.body
    settings = client.get(f"/api/email/setup/{u.bot_id}", headers=u.h()).json()["settings"]["after_call"]
    assert settings["approved"] == 1 and settings["approved_unchanged"] == 1


def test_automatic_goes_by_itself_written_checked_and_counted_as_one_ai_reply(client, business, run, sent, model):
    u = business("auto")
    call_id = run(_ended, u)
    run(automations.process_due)
    assert sent == []  # not before it's written
    run(_write_all)
    assert len(model.asked) == 2
    run(automations.process_due)
    assert len(sent) == 1

    async def used():
        async with async_session() as db:
            return (await db.execute(select(AiReplyUsage.replies).where(AiReplyUsage.bot_id == u.bot_id))).scalar()
    assert run(used) == 1
    assert run(_job, call_id).status == "sent"


def test_what_is_written_comes_from_the_call_the_knowledge_and_what_is_booked(business, run, model):
    u = business("review")

    async def book():
        async with async_session() as db:
            db.add(CallbackJob(user_id=u.id, bot_id=u.bot_id, e164="+919876543210", kind="callback", status="queued", consent_source="test",
                               next_attempt_at=datetime(2030, 3, 5, 10, 30)))  # 4 pm in India
            await db.commit()
    run(book)
    model.write = {**WRITTEN, "next_step": "We will call you back on Tuesday 5 March at 4 pm."}
    job = run(_job, run(_ended, u))
    run(_write_all)
    system, user = model.asked[0]
    assert "Do you have 2BHK homes" in user and KNOWLEDGE in user
    assert "We will call them back on Tuesday 5 March at 4 pm." in user  # the real time, never "today"
    assert "Sunrise" in system and "Indian English" in system
    assert run(_job, job.ref_id).merge_data["call"]["next_step"] == "We will call you back on Tuesday 5 March at 4 pm."


def test_a_meeting_waiting_for_the_team_is_told_as_waiting_and_a_confirmed_one_as_confirmed(business, run, model):
    u = business("review")

    async def meet(status):
        async with async_session() as db:
            await db.execute(delete(Meeting).where(Meeting.bot_id == u.bot_id))
            db.add(Meeting(user_id=u.id, bot_id=u.bot_id, e164="+919876543210", starts_at=datetime(2030, 3, 5, 5, 30), status=status))
            await db.commit()
    run(meet, "requested")
    run(_ended, u)
    run(_write_all)
    assert "They asked to meet on Tuesday 5 March at 11 am. The team will confirm it." in model.asked[0][1]
    model.asked.clear()
    run(meet, "confirmed")
    run(_ended, u, captured={"Email": "second@sunrise-test.in"})
    run(_write_all)
    assert "Their meeting is confirmed for Tuesday 5 March at 11 am." in model.asked[0][1]


def test_a_number_nobody_said_is_taken_out_with_its_sentence(business, run, model):
    u = business("review")
    model.write = {"recap": ["You asked about 2BHK homes.", "Prices start at 30 lakh."],
                   "answers": [{"q": "What is the price?", "a": "They start at 45 lakh. There's a 5% discount this month."},
                               {"q": "Is there a discount of 20%?", "a": "Yes."}],
                   "unanswered": [], "next_step": "We'll call you at 6 pm.", "files": []}
    job = run(_job, run(_ended, u))
    run(_write_all)
    written = run(_job, job.ref_id).merge_data["call"]
    assert written["recap"] == ["You asked about 2BHK homes."]
    assert written["answers"] == [{"q": "What is the price?", "a": "They start at 45 lakh."}]
    assert written["next_step"] == ""


def test_the_check_can_correct_an_email_and_the_number_rule_applies_to_its_words_too(client, business, run, sent, model):
    u = business("auto")
    model.write = {**WRITTEN, "next_step": "Our team will visit you."}
    model.check = {"verdict": "fix", "reason": "Nobody promised a visit",
                   "email": {"recap": WRITTEN["recap"], "answers": WRITTEN["answers"] + [{"q": "Offer?", "a": "99 lakh only."}], "next_step": ""}}
    call_id = run(_ended, u)
    run(_write_all)
    run(automations.process_due)
    assert len(sent) == 1 and "visit" not in sent[0]["text"] and "99 lakh" not in sent[0]["text"]
    assert run(_job, call_id).merge_data["fixed"] == "Nobody promised a visit"


@pytest.mark.parametrize("check, more, why", [
    ({"verdict": "hold", "reason": "They complained about a refund"}, {}, "They complained about a refund"),
    (RuntimeError("no model"), {}, after_call.COULD_NOT_CHECK),
    ({"verdict": "ok"}, {"sentiment": "negative"}, after_call.UNHAPPY),
    ({"verdict": "what"}, {}, after_call.COULD_NOT_CHECK),
])
def test_on_automatic_these_still_wait_for_a_person(business, run, sent, model, check, more, why):
    u = business("auto")
    model.check = check
    call_id = run(_ended, u, **more)
    run(_write_all)
    run(automations.process_due)
    job = run(_job, call_id)
    assert sent == [] and job.status == "draft" and job.error == why and job.merge_data["call"]["recap"]


def test_when_the_model_fails_it_waits_in_drafts_and_can_be_written_again(client, business, run, sent, model):
    u = business("auto")
    model.write = RuntimeError("no model")
    call_id = run(_ended, u)
    run(_write_all)
    run(automations.process_due)
    job = run(_job, call_id)
    assert sent == [] and job.status == "draft" and job.compose_state == "failed"
    draft = client.get(f"/api/email/drafts/{job.id}", headers=u.h()).json()
    assert draft["state"] == "failed" and draft["note"] == after_call.COULD_NOT_WRITE
    assert client.post(f"/api/email/drafts/{job.id}/send", headers=u.h()).status_code == 400  # nothing written

    model.write = dict(WRITTEN)
    assert client.post(f"/api/email/drafts/{job.id}/rewrite", headers=u.h()).json() == {"status": "writing"}
    run(_write_all)
    draft = client.get(f"/api/email/drafts/{job.id}", headers=u.h()).json()
    assert draft["state"] == "ready" and draft["note"] is None and draft["recap"]


def test_it_does_not_wait_for_ever_for_a_lost_writer(business, run, sent, model):
    u = business("auto")
    call_id = run(_ended, u)

    async def lost():
        async with async_session() as db:
            job = (await db.execute(select(EmailJob).where(EmailJob.ref_id == call_id))).scalars().first()
            job.compose_state, job.compose_at, job.created_at = "working", datetime.utcnow(), datetime.utcnow() - timedelta(minutes=4)
            await db.commit()
    run(lost)
    run(automations.process_due)
    job = run(_job, call_id)
    assert sent == [] and job.status == "draft" and job.error == after_call.TOO_SLOW


def test_a_call_with_nothing_to_say_is_dropped(business, run, sent, model):
    u = business("auto")
    model.write = {"recap": []}
    job = run(_job, run(_ended, u))
    run(_write_all)
    job = run(_job, job.ref_id)
    assert job.status == "cancelled" and job.error == after_call.NOTHING_TO_SAY and len(model.asked) == 1


def test_no_replies_left_this_month_means_no_ai_email(business, run, sent, model, monkeypatch):
    import plans
    u = business("auto")

    async def none_left(db, bot_id):
        return False
    monkeypatch.setattr(plans, "can_reply", none_left)
    job = run(_job, run(_ended, u))
    run(_write_all)
    job = run(_job, job.ref_id)
    assert model.asked == [] and job.status == "cancelled" and "used up" in job.error


def test_questions_it_cannot_answer_go_to_questions_and_the_email_says_the_team_will_reply(business, run, sent, model):
    u = business("auto")
    model.write = {**WRITTEN, "unanswered": ["Do you allow pets?"]}
    run(_ended, u)
    run(_write_all)
    run(automations.process_due)
    assert "Do you allow pets?\nOur team will reply to you about this." in sent[0]["text"]

    async def gaps():
        async with async_session() as db:
            return (await db.execute(select(KnowledgeGap.question).where(KnowledgeGap.bot_id == u.bot_id))).scalars().all()
    assert run(gaps) == ["Do you allow pets?"]


def test_the_language_of_the_call(business, run, sent, model):
    u = business("auto")
    model.write = {**WRITTEN, "recap": ["நீங்கள் 2BHK வீடுகள் பற்றி கேட்டீர்கள்."], "answers": [], "unanswered": ["செல்லப்பிராணிகள் அனுமதியா?"]}
    run(_ended, u, language="ta-IN")
    run(_write_all)
    run(automations.process_due)
    assert "Tamil" in model.asked[0][0]
    assert sent[0]["subject"] == "Sunrise உடனான உங்கள் அழைப்பு" and "வணக்கம் Priya" in sent[0]["text"]
    assert "நாம் பேசியவை" in sent[0]["html"] and "எங்கள் குழு உங்களுக்குப் பதில்" in sent[0]["text"]

    # A language without a ready-made email: the frame in English, the AI's part in their language.
    model.asked.clear()
    u2 = business("auto")
    run(_ended, u2, language="te-IN")
    run(_write_all)
    assert "Telugu" in model.asked[0][0]


def test_an_email_that_drifts_out_of_the_language_of_the_call_is_written_again_then_held(business, run, sent, model):
    """Real calls, Nov 2026: a Tamil call got an email half in Hindi and half in English, and the checking model passed it."""
    tamil = {**WRITTEN, "recap": ["நீங்கள் Nimmi AI-ன் 2BHK வீடுகள் பற்றி கேட்டீர்கள்."], "answers": []}
    u = business("auto")
    model.write = [{**WRITTEN, "answers": []}, tamil]  # English, then Tamil
    run(_ended, u, language="ta-IN")
    run(_write_all)
    run(automations.process_due)
    writes = [user for system, user in model.asked if not system.startswith("You check")]
    assert len(writes) == 2 and "wasn't in Tamil" in writes[1]
    assert len(sent) == 1 and "பற்றி கேட்டீர்கள்" in sent[0]["text"]

    u2 = business("auto")
    hindi = {**WRITTEN, "recap": ["आपने 2BHK घरों के बारे में पूछा।"], "answers": []}
    model.asked.clear()
    model.write = [hindi, dict(hindi)]  # still not Tamil: a person reads it, and the check isn't needed
    call_id = run(_ended, u2, language="ta-IN", captured={"Email": "second@sunrise-test.in"})
    run(_write_all)
    run(automations.process_due)
    job = run(_job, call_id)
    assert len(sent) == 1 and job.status == "draft" and "Tamil" in job.error and job.merge_data["call"]["recap"] == hindi["recap"]
    assert len(model.asked) == 2

    # The check's correction has to stay in the language too.
    u3 = business("auto")
    model.asked.clear()
    model.write = dict(tamil)
    model.check = {"verdict": "fix", "reason": "A detail was wrong", "email": {"recap": ["You asked about homes."], "answers": [], "next_step": ""}}
    call_id = run(_ended, u3, language="ta-IN", captured={"Email": "third@sunrise-test.in"})
    run(_write_all)
    job = run(_job, call_id)
    assert job.status == "draft" and job.error == "A detail was wrong" and job.merge_data["call"]["recap"] == tamil["recap"]


def test_the_language_of_a_text_by_its_script():
    from mail import designs
    assert designs.written_in("நீங்கள் Nimmi AI-ன் சேவைகள் மற்றும் இன்டர்ன்ஷிப் (internship) பற்றி கேட்டீர்கள்.", "ta-IN")
    assert designs.written_in("आपने 2BHK घरों के बारे में पूछा।", "hi")
    assert designs.written_in("You asked about 2BHK homes in Anna Nagar.", "en-IN")
    assert designs.written_in("మీరు ఇళ్ల గురించి అడిగారు.", "te-IN")
    assert not designs.written_in("You asked about homes.", "ta-IN")
    assert not designs.written_in("நீங்கள் கேட்டீர்கள். आपने घरों के बारे में पूछा। हम बात कर रहे हैं।", "ta-IN")  # half Tamil, half Hindi
    assert not designs.written_in("நீங்கள் வீடுகள் பற்றி கேட்டீர்கள்.", "en-IN")
    assert designs.written_in("", "ta-IN") and designs.written_in("₹45,000", "ta-IN")  # nothing to go on: no complaint
    assert designs.written_in("Anything at all", "xx-IN")


def test_the_files_they_were_promised_go_with_it_and_downloads_are_counted(client, business, run, sent, model):
    u = business("auto")

    async def add():
        async with async_session() as db:
            f = WhatsAppFile(user_id=u.id, name="Brochure", kind="document", filename="brochure.pdf", mime="application/pdf", stored="x", size=1_300_000)
            db.add(f)
            await db.commit()
            return f.id
    file_id = run(add)
    model.write = {**WRITTEN, "files": [1, 1, 9, "x"]}
    call_id = run(_ended, u)
    run(_write_all)
    assert "1. Brochure" in model.asked[0][1]
    run(automations.process_due)
    assert "Brochure" in sent[0]["html"] and "1.2 MB" in sent[0]["html"]

    async def link_row():
        async with async_session() as db:
            job = (await db.execute(select(EmailJob).where(EmailJob.ref_id == call_id))).scalars().first()
            return (await db.execute(select(EmailLink).where(EmailLink.job_id == job.id, EmailLink.kind == "file"))).scalars().all()
    rows = run(link_row)
    assert [r.target for r in rows] == [f"file:{file_id}"]


# ─── the team's part ─────────────────────────────────────────────

def test_the_team_edits_a_draft_and_it_counts_as_changed(client, business, run, sent, model):
    u = business("review")
    job = run(_job, run(_ended, u))
    run(_write_all)
    saved = client.put(f"/api/email/drafts/{job.id}", json={
        "to": "priya.new@sunrise-test.in", "subject": "Lovely to speak with you", "recap": ["We talked about Anna Nagar.", " "],
        "answers": [{"q": "Parking?", "a": "One covered space."}, {"q": "Empty", "a": " "}], "next_step": "We will send the plans.",
        "file_ids": []}, headers=u.h())
    assert saved.status_code == 200 and "We talked about Anna Nagar." in saved.json()["html"]
    assert saved.json()["shown_subject"] == "Lovely to speak with you" and saved.json()["recap"] == ["We talked about Anna Nagar."]
    assert saved.json()["answers"] == [{"q": "Parking?", "a": "One covered space."}]
    assert client.put(f"/api/email/drafts/{job.id}", json={"to": "nope", "recap": []}, headers=u.h()).status_code == 400

    client.post(f"/api/email/drafts/{job.id}/send", headers=u.h())
    run(automations.process_due)
    assert sent[0]["to"] == "priya.new@sunrise-test.in" and sent[0]["subject"] == "Lovely to speak with you"
    assert "We will send the plans." in sent[0]["text"]
    settings = client.get(f"/api/email/setup/{u.bot_id}", headers=u.h()).json()["settings"]["after_call"]
    assert settings["approved"] == 1 and settings["approved_unchanged"] == 0


def test_a_discarded_draft_is_gone_from_drafts_and_in_history(client, business, run, sent, model):
    u = business("review")
    job = run(_job, run(_ended, u))
    run(_write_all)
    history = client.get("/api/integrations/email/history", headers=u.h()).json()
    assert history["total"] == 0  # drafts have their own page
    assert client.post(f"/api/email/drafts/{job.id}/discard", headers=u.h()).status_code == 200
    assert client.get("/api/email/drafts", headers=u.h()).json()["total"] == 0
    history = client.get("/api/integrations/email/history", headers=u.h()).json()
    assert history["items"][0]["status"] == "cancelled" and history["items"][0]["label"] == "After a call, by the AI"
    assert client.post(f"/api/email/drafts/{job.id}/send", headers=u.h()).status_code == 404
    run(automations.process_due)
    assert sent == []


def test_someone_who_unsubscribes_loses_their_draft_and_an_approval_after_a_stop_is_refused(client, business, run, sent, model):
    u = business("review")
    job = run(_job, run(_ended, u))
    run(_write_all)
    run(automations.unsubscribe, u.id, "priya@sunrise-test.in")
    assert run(_job, job.ref_id).status == "cancelled"
    assert client.get("/api/email/drafts", headers=u.h()).json()["total"] == 0

    u2 = business("review")
    job2 = run(_job, run(_ended, u2))
    run(_write_all)
    from backend.models import EmailUnsubscribe

    async def stopped():
        async with async_session() as db:  # stopped by a path that doesn't touch the queue
            db.add(EmailUnsubscribe(user_id=u2.id, email="priya@sunrise-test.in", reason="team", scope="all"))
            await db.commit()
    run(stopped)
    refused = client.post(f"/api/email/drafts/{job2.id}/send", headers=u2.h())
    assert refused.status_code == 409 and "isn't emailed" in refused.json()["detail"]


def test_an_approved_email_goes_even_if_the_setting_changed_but_an_unapproved_one_does_not(client, business, run, sent, model):
    u = business("review")
    job = run(_job, run(_ended, u))
    run(_write_all)
    client.post(f"/api/email/drafts/{job.id}/send", headers=u.h())
    client.put(f"/api/email/setup/{u.bot_id}", json={"settings": {"after_call": {"inbound": "off"}}}, headers=u.h())
    run(automations.process_due)
    assert len(sent) == 1

    client.put(f"/api/email/setup/{u.bot_id}", json={"settings": {"after_call": {"inbound": "auto"}}}, headers=u.h())
    other = run(_ended, u, captured={"Email": "ravi@sunrise-test.in"})
    run(_write_all)
    client.put(f"/api/email/setup/{u.bot_id}", json={"settings": {"after_call": {"inbound": "off"}}}, headers=u.h())
    run(automations.process_due)
    assert len(sent) == 1 and run(_job, other).status == "cancelled"


def test_after_20_approvals_it_offers_automatic_once(client, business, run, model):
    u = business("review")

    async def approved(n):
        async with async_session() as db:
            await setup.save_settings(db, u.id, u.bot_id, "after_call", {"approved": n, "approved_unchanged": n - 2})
            await db.commit()
    run(approved, 19)
    assert client.get("/api/email/drafts", headers=u.h()).json()["suggest"] == []
    run(approved, 20)
    assert client.get("/api/email/drafts", headers=u.h()).json()["suggest"] == [
        {"bot_id": u.bot_id, "bot_name": "Sunrise", "approved": 20, "unchanged": 18}]

    assert client.post("/api/email/drafts/suggestion", json={"bot_id": u.bot_id, "accept": False}, headers=u.h()).status_code == 200
    assert client.get("/api/email/drafts", headers=u.h()).json()["suggest"] == []
    settings = client.get(f"/api/email/setup/{u.bot_id}", headers=u.h()).json()["settings"]["after_call"]
    assert settings["inbound"] == "review"

    u2 = business("review", "outbound")

    async def approved2():
        async with async_session() as db:
            await setup.save_settings(db, u2.id, u2.bot_id, "after_call", {"approved": 25, "approved_unchanged": 25})
            await db.commit()
    run(approved2)
    client.post("/api/email/drafts/suggestion", json={"bot_id": u2.bot_id, "accept": True}, headers=u2.h())
    settings = client.get(f"/api/email/setup/{u2.bot_id}", headers=u2.h()).json()["settings"]["after_call"]
    assert settings["outbound"] == "auto" and settings["inbound"] == "off"  # only what was on review
    assert client.get("/api/email/drafts", headers=u2.h()).json()["suggest"] == []


def test_the_counters_are_not_for_the_dashboard_to_set(client, business):
    u = business("review")
    client.put(f"/api/email/setup/{u.bot_id}", json={"settings": {"after_call": {"approved": 99, "suggested": True}}}, headers=u.h())
    settings = client.get(f"/api/email/setup/{u.bot_id}", headers=u.h()).json()["settings"]["after_call"]
    assert settings["approved"] == 0 and settings["suggested"] is False


def test_it_needs_somewhere_for_replies_to_go(client, make_user):
    u = make_user()
    bot = u.bot("Sunrise")
    r = client.put(f"/api/email/setup/{bot}", json={"settings": {"after_call": {"inbound": "review"}}}, headers=u.h())
    assert r.status_code == 400 and "where replies go" in r.json()["detail"]


def test_another_workspace_cannot_touch_a_draft(client, business, make_user, run, model):
    u = business("review")
    job = run(_job, run(_ended, u))
    run(_write_all)
    stranger = make_user()
    assert client.get("/api/email/drafts", headers=stranger.h()).json()["total"] == 0
    assert client.get(f"/api/email/drafts/{job.id}", headers=stranger.h()).status_code == 404
    for path in ("send", "discard", "rewrite"):
        assert client.post(f"/api/email/drafts/{job.id}/{path}", headers=stranger.h()).status_code == 404
    assert client.put(f"/api/email/drafts/{job.id}", json={"to": "a@b.co"}, headers=stranger.h()).status_code == 404
    assert client.post("/api/email/drafts/suggestion", json={"bot_id": u.bot_id, "accept": True}, headers=stranger.h()).status_code == 404
    assert run(_job, job.ref_id).status == "draft"


def test_old_drafts_are_dropped(business, run, model):
    u = business("review")
    call_id = run(_ended, u)

    async def age():
        async with async_session() as db:
            job = (await db.execute(select(EmailJob).where(EmailJob.ref_id == call_id))).scalars().first()
            job.created_at = datetime.utcnow() - timedelta(days=15)
            await db.commit()
    run(age)
    run(after_call.expire_drafts)
    job = run(_job, call_id)
    assert job.status == "cancelled" and "two weeks" in job.error


def test_a_business_that_took_the_summary_out_of_its_email_sends_its_own_text_without_the_ai(client, business, run, sent, model):
    u = business("auto")
    client.put(f"/api/email/designs/{u.bot_id}/after_call", json={"language": "en", "subject": "Thanks for calling", "blocks": [
        {"type": "text", "text": "Thanks for calling {{business}}, {{first_name|there}}."}, {"type": "signature"}]}, headers=u.h())
    run(_ended, u)
    run(_write_all)
    run(automations.process_due)
    assert model.asked == [] and sent[0]["subject"] == "Thanks for calling" and "Thanks for calling Sunrise, Priya." in sent[0]["text"]


def test_starter_does_not_get_it(client, make_user, run, model, monkeypatch):
    monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")
    u = make_user()
    u.bot_id = u.bot("Sunrise")

    async def starter():
        async with async_session() as db:
            db.add(Subscription(user_id=u.id, bot_id=u.bot_id, tier="starter", period="monthly", plan_name="Starter", price_paid=999,
                                credits_granted=1, start_date=datetime.utcnow() - timedelta(days=1),
                                end_date=datetime.utcnow() + timedelta(days=29), auto_renewal=False, status="active"))
            await db.commit()
    run(starter)
    client.put("/api/integrations", json=BASE, headers=u.h())
    refused = client.put(f"/api/email/setup/{u.bot_id}", json={"settings": {"after_call": {"inbound": "review"}}}, headers=u.h())
    assert refused.status_code == 402 and "Growth" in refused.json()["detail"]
