"""The team's answer reaching everyone who asked (mail plan 5.3, phase 4)."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.future import select

import assist
from backend.models import Contact, Conversation, EmailJob, EmailUnsubscribe, IntegrationSettings, KnowledgeGap, QuestionAsker
from database import async_session


@pytest.fixture(autouse=True)
def _nothing_left_queued(run):
    """Later tests in this database send what's queued."""
    yield
    async def clear():
        async with async_session() as db:
            for job in (await db.execute(select(EmailJob).where(EmailJob.automation == "question_answer", EmailJob.status == "queued"))).scalars().all():
                job.status = "cancelled"
            await db.commit()
    run(clear)


async def _chat(bot_id, captured):
    async with async_session() as db:
        conv = Conversation(bot_id=bot_id, visitor_session_id="widget-session-ai-x", captured_data=captured)
        db.add(conv)
        await db.commit()
        return conv.conversation_id


async def _gap(bot_id):
    async with async_session() as db:
        return (await db.execute(select(KnowledgeGap).where(KnowledgeGap.bot_id == bot_id))).scalars().first()


async def _askers(bot_id):
    async with async_session() as db:
        return (await db.execute(select(QuestionAsker).where(QuestionAsker.bot_id == bot_id))).scalars().all()


async def _jobs(user):
    async with async_session() as db:
        return (await db.execute(select(EmailJob).where(EmailJob.user_id == user.id, EmailJob.automation == "question_answer"))).scalars().all()


def test_who_asked_is_kept_once_each(make_user, run):
    user = make_user()
    bot = user.bot()
    async def go():
        conv = await _chat(bot, {})
        await assist.record_gap(bot, "Do you open on Sundays?", "chat", conv)
        await assist.record_gap(bot, "Do you open on Sundays?", "chat", conv)
        await assist.record_gap(bot, "Do you open on sundays", "voice", None, "phone:+919876543210")
        await assist.record_gap(bot, "Do you open on Sundays?", "email", None, "email:asha@example.com")
        await assist.record_gap(bot, "Do you open on Sundays?", "voice", None)  # nobody known
        assert (await _gap(bot)).count == 5
        assert sorted(a.who.split(":")[0] for a in await _askers(bot)) == ["chat", "email", "phone"]
    run(go)


def _answered(client, user, bot, run, seeded):
    run(seeded)
    gap = run(_gap, bot)
    assert client.post(f"/api/questions/{gap.id}/answer", json={"answer": "Yes, 10 to 2."}, headers=user.h()).status_code == 200
    return gap


def test_the_team_sees_who_left_an_email_and_ticks_who_gets_it(make_user, client, run):
    from notify import automations
    user = make_user()
    bot = user.bot()
    async def seeded():
        conv = await _chat(bot, {"name": "Ravi", "email": "ravi@example.com"})
        no_email = await _chat(bot, {"name": "Nobody"})
        async with async_session() as db:
            db.add(Contact(user_id=user.id, bot_id=bot, e164="+919876543210", name="Asha", email="asha@example.com", details={}, calls=1))
            db.add(IntegrationSettings(user_id=user.id, reply_to="team@example.com"))
            await db.commit()
        await assist.record_gap(bot, "Do you open on Sundays?", "chat", conv)
        await assist.record_gap(bot, "Do you open on Sundays?", "chat", no_email)
        await assist.record_gap(bot, "Do you open on Sundays?", "voice", None, "phone:+919876543210")
    gap = _answered(client, user, bot, run, seeded)
    asked = client.get(f"/api/email/questions/{gap.id}/people", headers=user.h()).json()
    assert sorted(p["email"] for p in asked["people"]) == ["asha@example.com", "ravi@example.com"] and asked["without_email"] == 1
    ravi = next(p for p in asked["people"] if p["email"] == "ravi@example.com")
    assert client.post(f"/api/email/questions/{gap.id}/send", json={"ids": [ravi["id"]]}, headers=user.h()).json() == {"sent": 1, "not_sent": 0}
    assert [j.to_email for j in run(_jobs, user)] == ["ravi@example.com"], "only who was ticked"
    assert client.post(f"/api/email/questions/{gap.id}/send", json={"ids": [ravi["id"]]}, headers=user.h()).json() == {"sent": 0, "not_sent": 0}, "once each"
    assert next(p for p in client.get(f"/api/email/questions/{gap.id}/people", headers=user.h()).json()["people"] if p["email"] == "ravi@example.com")["sent"]
    made = run(_made, user)
    assert "Do you open on Sundays?" in made and "Yes, 10 to 2." in made and "Ravi" in made


async def _made(user):
    from mail import senders, small
    async with async_session() as db:
        job = (await db.execute(select(EmailJob).where(EmailJob.user_id == user.id, EmailJob.automation == "question_answer"))).scalars().first()
        rendered, _ = await small.made(db, job, await senders.sender_for(db, user.id, job.bot_id), "https://x.in/u")
    return rendered.text


def test_one_person_asking_twice_gets_one_email(make_user, client, run):
    user = make_user()
    bot = user.bot()
    async def seeded():
        await assist.record_gap(bot, "Do you open on Sundays?", "chat", await _chat(bot, {"email": "asha@example.com"}))
        await assist.record_gap(bot, "Do you open on Sundays?", "email", None, "email:asha@example.com")
    gap = _answered(client, user, bot, run, seeded)
    assert len(client.get(f"/api/email/questions/{gap.id}/people", headers=user.h()).json()["people"]) == 1


def test_someone_who_unsubscribed_doesnt_get_it(make_user, client, run):
    user = make_user()
    bot = user.bot()
    async def seeded():
        await assist.record_gap(bot, "Do you open on Sundays?", "email", None, "email:asha@example.com")
        async with async_session() as db:
            db.add(EmailUnsubscribe(user_id=user.id, email="asha@example.com", reason="unsubscribed", scope="all"))
            await db.commit()
    gap = _answered(client, user, bot, run, seeded)
    person = client.get(f"/api/email/questions/{gap.id}/people", headers=user.h()).json()["people"][0]
    assert client.post(f"/api/email/questions/{gap.id}/send", json={"ids": [person["id"]]}, headers=user.h()).json() == {"sent": 0, "not_sent": 1}
    assert run(_jobs, user) == []


def test_it_needs_an_answer_and_belongs_to_its_workspace(make_user, client, run):
    user, other = make_user(), make_user()
    bot = user.bot()
    async def seeded():
        await assist.record_gap(bot, "Do you open on Sundays?", "email", None, "email:asha@example.com")
    run(seeded)
    gap = run(_gap, bot)
    assert client.post(f"/api/email/questions/{gap.id}/send", json={"ids": ["x"]}, headers=user.h()).status_code == 400
    assert client.get(f"/api/email/questions/{gap.id}/people", headers=other.h()).status_code == 404
    assert client.post(f"/api/email/questions/{gap.id}/send", json={"ids": ["x"]}, headers=other.h()).status_code == 404


def test_erasing_someone_takes_the_record_of_what_they_asked(make_user, client, run):
    user = make_user()
    bot = user.bot()
    async def seeded():
        async with async_session() as db:
            db.add(Contact(user_id=user.id, bot_id=bot, e164="+919876543210", email="asha@example.com", details={}, calls=1))
            await db.commit()
        await assist.record_gap(bot, "Do you open on Sundays?", "voice", None, "phone:+919876543210")
        await assist.record_gap(bot, "Do you open on Sundays?", "email", None, "email:asha@example.com")
        await assist.record_gap(bot, "Do you open on Sundays?", "email", None, "email:someone@example.com")
    run(seeded)
    assert client.post("/api/voice/erase", json={"number": "+919876543210"}, headers=user.h()).status_code == 200
    assert [a.who for a in run(_askers, bot)] == ["email:someone@example.com"]
