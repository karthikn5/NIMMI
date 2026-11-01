"""How long email text is kept, and Compliance > Erase (mail plan 5.2, phase 9): the words go, the record stays, and what proves the business kept its word is never touched."""
import uuid
from datetime import datetime, timedelta

from sqlalchemy.future import select

from backend.models import (Consent, Contact, EmailAgentAction, EmailClick, EmailJob, EmailLink, EmailThread, EmailUnsubscribe, IntegrationSettings, LeadIntake, ThreadMessage)
from database import async_session
from mail import retention

MONTH = timedelta(days=30)


def job(run, user, bot, months_old, status="sent", to="asha@example.com"):
    async def go():
        async with async_session() as db:
            row = EmailJob(user_id=user.id, bot_id=bot, kind=f"chat_lead#{uuid.uuid4().hex[:8]}", ref_id=uuid.uuid4().hex, to_email=to, automation="chat_lead", step=1, subject="About your home",
                           body="Hi Asha, your flat at 12 Anna Salai", status=status, send_at=datetime.utcnow(), sent_at=datetime.utcnow() - months_old * MONTH, merge_data={"name": "Asha"},
                           body_tpl="Hi {{name}}", created_at=datetime.utcnow() - months_old * MONTH)
            db.add(row)
            await db.commit()
            return row.id
    return run(go)


def get(run, model, key):
    async def go():
        async with async_session() as db:
            return await db.get(model, key)
    return run(go)


def keep(run, user, months):
    async def go():
        async with async_session() as db:
            db.add(IntegrationSettings(user_id=user.id, email_keep_months=months))
            await db.commit()
    run(go)


def thread(run, user, bot, months_old, status="received", email="asha@example.com"):
    async def go():
        async with async_session() as db:
            t = EmailThread(user_id=user.id, bot_id=bot, code=uuid.uuid4().hex[:16], email=email, subject="Parking")
            db.add(t)
            await db.flush()
            m = ThreadMessage(thread_id=t.id, user_id=user.id, direction="in", who="customer", status=status, text="My number is 98765 00001", attachments=[{"id": "a", "filename": "id.pdf"}],
                              provider_id=uuid.uuid4().hex, created_at=datetime.utcnow() - months_old * MONTH)
            db.add(m)
            await db.commit()
            return t.id, m.id
    return run(go)


def test_after_a_year_the_words_go_and_the_record_stays(make_user, run):
    u = make_user()
    bot = u.bot()
    old, recent = job(run, u, bot, 13), job(run, u, bot, 11)
    assert run(retention.purge) >= 1
    gone = get(run, EmailJob, old)
    assert gone.body == retention.GONE and gone.subject == retention.GONE and gone.body_tpl is None and gone.merge_data is None
    assert gone.status == "sent" and gone.to_email == "asha@example.com" and gone.sent_at is not None, "the record that it was sent stays"
    assert get(run, EmailJob, recent).body.startswith("Hi Asha")


def test_an_email_still_to_go_is_never_cleared(make_user, run):
    u = make_user()
    bot = u.bot()
    for status in ("queued", "draft", "held"):
        waiting = job(run, u, bot, 20, status=status)
        run(retention.purge)
        assert get(run, EmailJob, waiting).body.startswith("Hi Asha"), status


def test_each_business_picks_its_own_time(make_user, run):
    short, long, usual = make_user(), make_user(), make_user()
    keep(run, short, 6)
    keep(run, long, 24)
    seven = job(run, short, short.bot(), 7)
    five = job(run, short, short.bot(), 5)
    thirteen = job(run, long, long.bot(), 13)
    other = job(run, usual, usual.bot(), 7)
    run(retention.purge)
    assert get(run, EmailJob, seven).body == retention.GONE and get(run, EmailJob, five).body != retention.GONE
    assert get(run, EmailJob, thirteen).body != retention.GONE, "24 months: still here"
    assert get(run, EmailJob, other).body != retention.GONE, "one business's choice isn't another's"


def test_replies_lose_their_words_and_attachments_but_a_draft_waits(make_user, run):
    u = make_user()
    bot = u.bot()
    _, old = thread(run, u, bot, 13)
    _, draft = thread(run, u, bot, 13, status="draft")
    _, recent = thread(run, u, bot, 2)
    run(retention.purge)
    row = get(run, ThreadMessage, old)
    assert row.text == retention.GONE and row.attachments is None
    assert get(run, ThreadMessage, draft).text.startswith("My number") and get(run, ThreadMessage, recent).text.startswith("My number")


def test_what_came_from_a_lead_portal_goes_and_the_row_stays_so_retries_stay_single(make_user, run):
    u = make_user()
    bot = u.bot()
    async def intake():
        async with async_session() as db:
            row = LeadIntake(user_id=u.id, bot_id=bot, channel="email", ref=uuid.uuid4().hex, raw="A full forwarded email", created_at=datetime.utcnow() - 13 * MONTH)
            db.add(row)
            await db.commit()
            return row.id
    row_id = run(intake)
    run(retention.purge)
    assert get(run, LeadIntake, row_id).raw is None


def test_what_proves_the_business_kept_its_word_is_never_touched(make_user, run):
    u = make_user()
    bot = u.bot()
    async def records():
        async with async_session() as db:
            db.add_all([Consent(user_id=u.id, bot_id=bot, email="asha@example.com", source="import", words="Signed up at the expo"),
                        EmailUnsubscribe(user_id=u.id, email="ravi@example.com", reason="unsubscribed", created_at=datetime.utcnow() - 40 * MONTH)])
            await db.commit()
    run(records)
    run(retention.purge)
    async def still():
        async with async_session() as db:
            return ((await db.execute(select(Consent).where(Consent.user_id == u.id))).scalars().first(),
                    (await db.execute(select(EmailUnsubscribe).where(EmailUnsubscribe.user_id == u.id))).scalars().first())
    assert all(run(still))


def test_old_agent_notes_go(make_user, run):
    u = make_user()
    bot = u.bot()
    async def note():
        async with async_session() as db:
            c = Contact(user_id=u.id, bot_id=bot, e164=f"+9198{uuid.uuid4().int % 10**8:08d}", name="Asha")
            db.add(c)
            await db.flush()
            row = EmailAgentAction(user_id=u.id, bot_id=bot, contact_id=c.id, action="email", why="She asked about parking", created_at=datetime.utcnow() - 13 * MONTH)
            db.add(row)
            await db.commit()
            return row.id
    row_id = run(note)
    run(retention.purge)
    assert get(run, EmailAgentAction, row_id) is None


def test_running_it_again_finds_nothing_new_to_clear(make_user, run):
    u = make_user()
    old = job(run, u, u.bot(), 13)
    run(retention.purge)
    first = get(run, EmailJob, old)
    assert run(retention.purge) == 0 and get(run, EmailJob, old).body == first.body


def test_the_time_kept_is_the_businesss_choice(client, make_user):
    u, other = make_user(), make_user()
    assert client.get("/api/email/retention", headers=u.h()).json() == {"months": 12, "choices": [6, 12, 24, 36]}
    assert client.put("/api/email/retention", json={"months": 7}, headers=u.h()).status_code == 400
    assert client.put("/api/email/retention", json={"months": 24}, headers=u.h()).json()["months"] == 24
    assert client.get("/api/email/retention", headers=u.h()).json()["months"] == 24
    assert client.get("/api/email/retention", headers=other.h()).json()["months"] == 12


def test_erase_removes_their_emails_and_keeps_what_stops_them_being_emailed(client, make_user, run):
    u, other = make_user(), make_user()
    bot = u.bot()
    number = "+919876500077"
    async def person():
        async with async_session() as db:
            db.add(Contact(user_id=u.id, bot_id=bot, e164=number, name="Asha", email="Asha@Example.com"))
            db.add(EmailUnsubscribe(user_id=u.id, email="asha@example.com", reason="unsubscribed"))
            await db.commit()
    run(person)
    mine, keeps, theirs = job(run, u, bot, 1), job(run, u, bot, 1, to="ravi@example.com"), job(run, other, other.bot(), 1)
    thread_id, message_id = thread(run, u, bot, 1)
    async def tracked():
        async with async_session() as db:
            db.add(EmailLink(token=uuid.uuid4().hex[:22], user_id=u.id, job_id=mine, kind="link", target="https://example.com/", label="Prices", clicks=1))
            db.add(EmailClick(user_id=u.id, job_id=mine, token="t", at=datetime.utcnow()))
            intake = LeadIntake(user_id=u.id, bot_id=bot, channel="form", ref=uuid.uuid4().hex, raw="Asha's form")
            db.add(intake)
            await db.flush()
            contact = (await db.execute(select(Contact).where(Contact.user_id == u.id))).scalars().first()
            intake.contact_id = contact.id
            await db.commit()
            return intake.id
    intake_id = run(tracked)
    assert client.post("/api/voice/erase", json={"number": number}, headers=u.h()).status_code == 200
    assert get(run, EmailJob, mine) is None and get(run, EmailThread, thread_id) is None and get(run, ThreadMessage, message_id) is None and get(run, LeadIntake, intake_id) is None
    assert get(run, EmailJob, keeps) is not None and get(run, EmailJob, theirs) is not None
    async def left():
        async with async_session() as db:
            return ((await db.execute(select(EmailLink).where(EmailLink.job_id == mine))).scalars().all(), (await db.execute(select(EmailClick).where(EmailClick.job_id == mine))).scalars().all(),
                    (await db.execute(select(EmailUnsubscribe).where(EmailUnsubscribe.user_id == u.id))).scalars().first())
    links, clicks, stopped = run(left)
    assert links == [] and clicks == [] and stopped is not None, "their unsubscribe is what keeps them from being emailed again"
