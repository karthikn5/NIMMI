"""Journeys and lead stages (mail plan, phase 4)."""
import asyncio
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.future import select

from backend.models import CallbackJob, CallLog, Contact, Conversation, EmailJob, EmailThread, EmailUnsubscribe, IntegrationSettings, Journey, JourneyRun, Meeting, ThreadMessage
from database import async_session
from mail import journeys

pytestmark = pytest.mark.usefixtures("no_ai")


@pytest.fixture
def make_user(make_user):
    """With assistants made ahead: a test's coroutine runs on the app's loop, where the test client can't be called."""
    def made():
        user = make_user()
        user.spare = [user.bot() for _ in range(3)]
        return user
    return made


@pytest.fixture(autouse=True)
def _nothing_left_running(run):
    """The tests share a database, and each pass takes a batch of runs."""
    async def clear():
        async with async_session() as db:
            for r in (await db.execute(select(JourneyRun).where(JourneyRun.status == "active"))).scalars().all():
                journeys._end(r, "stopped", "The test is over")
            for j in (await db.execute(select(Journey).where(Journey.enabled.is_(True)))).scalars().all():
                j.enabled = False
            for job in (await db.execute(select(EmailJob).where(EmailJob.status == "queued"))).scalars().all():
                job.status = "cancelled"
            await db.commit()
    run(clear)
    yield
    run(clear)  # later tests in this database send what's queued


@pytest.fixture
def no_ai(monkeypatch):
    async def nothing(*_a, **_k):
        return ""
    monkeypatch.setattr("mail.compose.ask_model", nothing)


async def _seed(user, steps, *, trigger="new_lead", value=None, goal=None, options=None, email="asha@example.com", e164="+919876543210", enabled=True, name="Asha Rao", **fields):
    bot_id = user.spare.pop()
    async with async_session() as db:
        settings = (await db.execute(select(IntegrationSettings).where(IntegrationSettings.user_id == user.id))).scalars().first()
        if settings is None:
            db.add(IntegrationSettings(user_id=user.id, reply_to="team@example.com"))
        journey = Journey(user_id=user.id, bot_id=bot_id, name="Test", trigger=trigger, trigger_value=value, goal=goal, options=options or {}, steps=steps, enabled=enabled)
        contact = Contact(user_id=user.id, bot_id=bot_id, e164=e164, email=email, name=name, details=fields.pop("details", {}), calls=fields.pop("calls", 0), **fields)
        db.add_all([journey, contact])
        await db.commit()
    return journey.id, contact.id, bot_id


async def _run(journey_id):
    async with async_session() as db:
        return (await db.execute(select(JourneyRun).where(JourneyRun.journey_id == journey_id))).scalars().first()


async def _emails(user, to="asha@example.com"):
    async with async_session() as db:
        return (await db.execute(select(EmailJob).where(EmailJob.user_id == user.id, EmailJob.to_email == to).order_by(EmailJob.created_at))).scalars().all()


AT_NOON = datetime(2026, 11, 3, 6, 30)  # 12:00 in India, a Tuesday


async def _go(user, journey_id, contact_id, bot_id, at=AT_NOON):
    assert await journeys.fire(user.id, bot_id, "new_lead", contact_id, "chat", now=at) == 1
    await journeys.tick(at + journeys.START_DELAY)


def test_a_journey_runs_step_by_step_and_ends(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "Hi {{first_name|there}}", "body": "From {{business}}"}, {"type": "wait", "days": 2},
                                           {"type": "email", "subject": "Again", "body": "Still there?"}])
        await _go(user, jid, cid, bot)
        assert [e.subject for e in await _emails(user)] == ["Hi Asha"]
        r = await _run(jid)
        assert r.status == "active" and r.step == 2 and r.next_at.replace(tzinfo=None) > AT_NOON + timedelta(days=1, hours=20)
        await journeys.tick(AT_NOON + timedelta(days=1))
        assert len(await _emails(user)) == 1, "the wait isn't over"
        await journeys.tick(r.next_at.replace(tzinfo=None))
        assert [e.subject for e in await _emails(user)] == ["Hi Asha", "Again"]
        r = await _run(jid)
        assert r.status == "done" and r.reason == "It ran to the end" and r.slot == r.id
    run(go)


def test_someone_is_on_a_journey_once_at_a_time_and_not_again_soon(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "Hi", "body": "x"}])
        now = datetime.utcnow()
        assert await journeys.fire(user.id, bot, "new_lead", cid, now=now) == 1
        assert await journeys.fire(user.id, bot, "new_lead", cid, now=now) == 0
        await journeys.tick(now + journeys.START_DELAY)
        assert (await _run(jid)).status == "done"
        assert await journeys.fire(user.id, bot, "new_lead", cid, now=now + timedelta(days=5)) == 0
        assert await journeys.fire(user.id, bot, "new_lead", cid, now=now + timedelta(days=31)) == 1
    run(go)


def test_the_trigger_value_decides_who_starts(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "Hi", "body": "x"}], value="portal")
        assert await journeys.fire(user.id, bot, "new_lead", cid, "chat") == 0
        assert await journeys.fire(user.id, bot, "new_lead", cid, "portal") == 1
    run(go)


def test_a_journey_turned_off_starts_nobody_and_stops_those_on_it(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "wait", "days": 1}, {"type": "email", "subject": "Hi", "body": "x"}])
        await _go(user, jid, cid, bot)
        async with async_session() as db:
            (await db.get(Journey, jid)).enabled = False
            await db.commit()
        r = await _run(jid)
        await journeys.tick(r.next_at.replace(tzinfo=None))
        assert (await _run(jid)).status == "stopped" and await _emails(user) == []
    run(go)


@pytest.mark.parametrize("stopper", ["unsubscribed", "dnc", "reply"])
def test_an_unsubscribe_the_do_not_call_list_or_a_reply_stops_it_at_every_step(make_user, run, stopper):
    from backend.models import DncEntry
    user = make_user()
    async def go():
        steps = [{"type": "email", "subject": "One", "body": "x"}, {"type": "wait", "days": 1}, {"type": "email", "subject": "Two", "body": "x"}, {"type": "wait", "days": 1},
                 {"type": "email", "subject": "Three", "body": "x"}]
        jid, cid, bot = await _seed(user, steps)
        await _go(user, jid, cid, bot)
        r = await _run(jid)
        async with async_session() as db:
            if stopper == "unsubscribed":
                db.add(EmailUnsubscribe(user_id=user.id, email="asha@example.com", reason="unsubscribed", scope="marketing"))
            elif stopper == "dnc":
                db.add(DncEntry(user_id=user.id, e164="+919876543210"))
            else:
                thread = EmailThread(user_id=user.id, bot_id=bot, code="c1", email="asha@example.com")
                db.add(thread)
                await journeys.stopped_by_reply(db, thread)
            await db.commit()
        await journeys.tick(r.next_at.replace(tzinfo=None))
        r = await _run(jid)
        assert r.status == "stopped", r.reason
        assert [e.subject for e in await _emails(user)] == ["One"]
    run(go)


def test_a_reply_cancels_the_email_about_to_go(make_user, run):
    from notify import automations
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "One", "body": "x"}])
        await _go(user, jid, cid, bot)
        async with async_session() as db:
            run_row = await _run(jid)
            await journeys.stop_for(db, user.id, [cid], "They replied")
            await db.commit()
        async with async_session() as db:
            job = (await db.execute(select(EmailJob).where(EmailJob.ref_id == run_row.id))).scalars().first()
            run_row = await db.get(JourneyRun, run_row.id)
            run_row.status = "stopped"
            job.send_at = datetime.utcnow() - timedelta(minutes=1)
            await db.commit()
        await automations.process_due()
        assert (await _emails(user))[0].status == "cancelled"
    run(go)


def test_a_reply_to_another_business_of_the_same_account_stops_nothing(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "wait", "days": 1}, {"type": "email", "subject": "Hi", "body": "x"}])
        await _go(user, jid, cid, bot)
        other = user.spare.pop()
        async with async_session() as db:
            await journeys.stopped_by_reply(db, EmailThread(user_id=user.id, bot_id=other, code="c2", email="asha@example.com"))
            await db.commit()
        assert (await _run(jid)).status == "active"
    run(go)


def test_the_goal_ends_it(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "wait", "days": 1}, {"type": "email", "subject": "Hi", "body": "x"}], goal="booked")
        await _go(user, jid, cid, bot)
        r = await _run(jid)
        async with async_session() as db:
            db.add(Meeting(user_id=user.id, bot_id=bot, e164="+919876543210", starts_at=AT_NOON + timedelta(days=5), status="requested", created_at=AT_NOON + timedelta(hours=1)))
            await db.commit()
        await journeys.tick(r.next_at.replace(tzinfo=None))
        r = await _run(jid)
        assert r.status == "done" and r.reason == "They booked a meeting" and await _emails(user) == []
    run(go)


def test_a_call_or_a_whatsapp_chat_counts_as_a_reply(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "wait", "days": 1}, {"type": "email", "subject": "Hi", "body": "x"}], goal="replied")
        await _go(user, jid, cid, bot)
        r = await _run(jid)
        async with async_session() as db:
            (await db.get(Contact, cid)).last_chat_at = r.started_at.replace(tzinfo=None) + timedelta(hours=2)
            await db.commit()
        await journeys.tick(r.next_at.replace(tzinfo=None))
        r = await _run(jid)
        assert r.status == "done" and r.reason == "They replied"
    run(go)


def test_the_cap_holds_across_three_journeys_and_counts_other_emails(make_user, run):
    user = make_user()
    async def go():
        one, cid, bot = await _seed(user, [{"type": "email", "subject": "One", "body": "x"}])
        async with async_session() as db:
            two = Journey(user_id=user.id, bot_id=bot, name="Two", trigger="new_lead", steps=[{"type": "email", "subject": "Two", "body": "x"}], enabled=True)
            three = Journey(user_id=user.id, bot_id=bot, name="Three", trigger="new_lead", steps=[{"type": "email", "subject": "Three", "body": "x"}], enabled=True)
            db.add_all([two, three])
            await db.commit()
        assert await journeys.fire(user.id, bot, "new_lead", cid, now=AT_NOON) == 3
        clock = AT_NOON + journeys.START_DELAY
        await journeys.tick(clock)
        assert len(await _emails(user)) == 1, "one a day"
        for job in await _emails(user):
            assert job.automation == "journey"
        async with async_session() as db:
            for job in (await db.execute(select(EmailJob).where(EmailJob.user_id == user.id))).scalars().all():
                job.status = "sent"
            await db.commit()
        waiting = await _next_due(user)
        assert waiting > clock + timedelta(hours=23)
        await journeys.tick(waiting)
        assert len(await _emails(user)) == 2
        async with async_session() as db:
            for job in (await db.execute(select(EmailJob).where(EmailJob.user_id == user.id))).scalars().all():
                job.status = "sent"
            await db.commit()
        waiting = await _next_due(user)
        await journeys.tick(waiting)
        assert len(await _emails(user)) == 3
        stamps = sorted(e.send_at.replace(tzinfo=None) for e in await _emails(user))
        assert all(b - a >= timedelta(hours=23) for a, b in zip(stamps, stamps[1:])), stamps
    run(go)


async def _next_due(user):
    async with async_session() as db:
        return min(r.next_at.replace(tzinfo=None) for r in (await db.execute(select(JourneyRun).where(JourneyRun.user_id == user.id, JourneyRun.status == "active"))).scalars().all())


def test_a_welcome_email_already_queued_counts_towards_the_cap(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "Thanks", "body": "x"}])
        async with async_session() as db:
            db.add(EmailJob(user_id=user.id, bot_id=bot, kind="chat_lead", ref_id="c", to_email="asha@example.com", automation="chat_lead", step=1, subject="Welcome", body="x",
                            send_at=AT_NOON + timedelta(minutes=2)))
            await db.commit()
        await _go(user, jid, cid, bot)
        assert [e.subject for e in await _emails(user)] == ["Welcome"], "the journey's waits a day instead of landing on top of it"
        assert (await _run(jid)).status == "active"
    run(go)


def test_the_cap_can_be_changed(make_user, run):
    from mail import setup
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "One", "body": "x"}, {"type": "email", "subject": "Two", "body": "x"}])
        async with async_session() as db:
            await setup.save_settings(db, user.id, bot, "journeys", {"per_day": 2})
            await db.commit()
        await _go(user, jid, cid, bot)
        assert len(await _emails(user)) == 2
    run(go)


def test_messages_keep_to_quiet_hours_but_a_new_lead_hears_back_at_once(make_user, run):
    user = make_user()
    night = datetime(2026, 11, 3, 18, 0)  # 11:30 pm in India
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "Thanks", "body": "x"}, {"type": "email", "subject": "Next", "body": "x"}])
        await journeys.fire(user.id, bot, "new_lead", cid, now=night)
        await journeys.tick(night + journeys.START_DELAY)
        assert [e.subject for e in await _emails(user)] == ["Thanks"]
        r = await _run(jid)
        assert r.step == 1 and r.next_at.replace(tzinfo=None) == datetime(2026, 11, 4, 3, 30), "9 am India"
    run(go)


def test_a_wait_of_days_ends_at_the_hour_they_last_picked_up(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "wait", "days": 2}, {"type": "email", "subject": "Hi", "body": "x"}], last_call_at=datetime(2026, 11, 1, 12, 0))  # 5:30 pm
        await _go(user, jid, cid, bot)
        local = (await _run(jid)).next_at.replace(tzinfo=None) + timedelta(hours=5, minutes=30)
        assert (local.date().isoformat(), local.hour) == ("2026-11-05", 17)
    run(go)


def test_a_wait_until_a_weekday(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "wait", "weekday": "mon", "at": "10:00"}, {"type": "email", "subject": "Hi", "body": "x"}])
        await _go(user, jid, cid, bot)
        assert (await _run(jid)).next_at.replace(tzinfo=None) == datetime(2026, 11, 9, 4, 30)
    run(go)


def test_a_wait_for_something_ends_when_it_happens_or_runs_out(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "wait", "hours": 5, "until": "detail:paid"}, {"type": "email", "subject": "Hi", "body": "x"}], e164="+919876543211")
        await _go(user, jid, cid, bot)
        r = await _run(jid)
        assert r.status == "active" and r.step == 0 and r.wait_ends is not None
        async with async_session() as db:
            (await db.get(Contact, cid)).details = {"paid": "yes"}
            await db.commit()
        await journeys.tick(r.next_at.replace(tzinfo=None))
        assert [e.subject for e in await _emails(user)] == ["Hi"]

        other, cid2, bot2 = await _seed(user, [{"type": "wait", "hours": 2, "until": "detail:paid"}, {"type": "notify", "text": "x"}], email="b@example.com", e164="+919876543212")
        await journeys.fire(user.id, bot2, "new_lead", cid2, now=AT_NOON)
        clock = AT_NOON + journeys.START_DELAY
        for _ in range(4):
            await journeys.tick(clock)
            r = await _run(other)
            if r.status != "active":
                break
            clock = r.next_at.replace(tzinfo=None)
        assert r.status == "done" and any("didn't happen" in h["what"] for h in r.history)
    run(go)


def test_a_branch_ends_or_skips(make_user, run):
    user = make_user()
    async def go():
        steps = [{"type": "branch", "if": "detail:paid", "then": "skip", "skip": 1}, {"type": "email", "subject": "Skipped", "body": "x"}, {"type": "email", "subject": "Kept", "body": "x"}]
        jid, cid, bot = await _seed(user, steps, details={"paid": "yes"}, e164="+919876543213")
        async with async_session() as db:
            from mail import setup
            await setup.save_settings(db, user.id, bot, "journeys", {"per_day": 5})
            await db.commit()
        await _go(user, jid, cid, bot)
        assert [e.subject for e in await _emails(user)] == ["Kept"]

        steps = [{"type": "branch", "if": "detail:paid", "not": True, "then": "end"}, {"type": "email", "subject": "Paid only", "body": "x"}]
        jid2, cid2, bot2 = await _seed(user, steps, email="c@example.com", e164="+919876543214")
        await journeys.fire(user.id, bot2, "new_lead", cid2, now=AT_NOON)
        await journeys.tick(AT_NOON + journeys.START_DELAY)
        assert await _emails(user, "c@example.com") == [] and (await _run(jid2)).status == "done"
    run(go)


def test_an_update_step_changes_the_contact(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "update", "stage": "interested", "status": "warm", "tag": "vip", "owner": user.id}])
        await _go(user, jid, cid, bot)
        async with async_session() as db:
            c = await db.get(Contact, cid)
            assert (c.stage, c.lead_status, c.tags, c.assigned_to) == ("interested", "warm", ["vip"], user.id)
    run(go)


def test_a_notify_step_makes_a_to_do(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "notify", "text": "{{name|Someone}} needs a call", "todo": True}])
        await _go(user, jid, cid, bot)
        async with async_session() as db:
            todo = (await db.execute(select(CallbackJob).where(CallbackJob.bot_id == bot))).scalars().first()
        assert (todo.kind, todo.status, todo.purpose) == ("person", "todo", "Asha Rao needs a call")
    run(go)


def _follow_ups_on(monkeypatch, review=False):
    from voice import schedule
    real = schedule.settings_for
    async def on(bot_id, db=None):
        s = await real(bot_id, db)
        s["follow_ups"] = {**s["follow_ups"], "enabled": True, "review": review}
        return s
    monkeypatch.setattr(schedule, "settings_for", on)


def test_a_call_step_is_a_schedule_follow_up_that_passes_its_checks(make_user, run, monkeypatch):
    from voice import schedule
    _follow_ups_on(monkeypatch)
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "call", "about": "Ask about the flat"}])
        await _go(user, jid, cid, bot, at=datetime.utcnow())
        async with async_session() as db:
            job = (await db.execute(select(CallbackJob).where(CallbackJob.bot_id == bot))).scalars().first()
            assert (job.kind, job.status, job.purpose) == ("follow_up", "queued", "Ask about the flat")
            # A lead who was never rated: Schedule's own check would call this off.
            check = await schedule.dial_check(db, job)
            assert check.stop is None or check.stop[1] == "No active number to call from", check.stop
    run(go)


def test_a_journey_call_keeps_to_the_seven_day_rule_and_the_not_interested_rating(make_user, run, monkeypatch):
    from voice import schedule
    _follow_ups_on(monkeypatch)
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "call"}], created_at=datetime.utcnow() - timedelta(days=10))
        await _go(user, jid, cid, bot, at=datetime.utcnow())
        async with async_session() as db:
            job = (await db.execute(select(CallbackJob).where(CallbackJob.bot_id == bot))).scalars().first()
            assert "days since they last spoke" in (await schedule.dial_check(db, job)).stop[1]
            contact = await db.get(Contact, cid)
            contact.created_at, contact.lead_status = datetime.utcnow(), "not_interested"
            await db.commit()
            assert "not interested" in (await schedule.dial_check(db, job)).stop[1]
    run(go)


def test_a_call_step_says_why_it_was_skipped(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "call"}])
        await _go(user, jid, cid, bot)
        r = await _run(jid)
        assert "follow-up calls are off" in r.history[0]["what"] and r.status == "done"
    run(go)


def test_whatsapp_outside_the_window_goes_by_email(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "whatsapp", "text": "Hi {{first_name|there}}"}])
        await _go(user, jid, cid, bot)
        assert [(e.subject, e.body) for e in await _emails(user)] == [("A message from " + (await _sender(user, bot)), "Hi Asha")]
        assert "by email instead" in (await _run(jid)).history[0]["what"]
    run(go)


async def _sender(user, bot):
    from mail import senders
    async with async_session() as db:
        return (await senders.sender_for(db, user.id, bot)).name


def test_an_ai_email_takes_the_models_words_without_invented_numbers_and_falls_back(make_user, run, monkeypatch):
    user = make_user()
    answers = iter(["Hi Asha, our plan costs Rs 4,999 a month. Tell us what you need.", ""])
    async def model(*_a, **_k):
        return next(answers)
    monkeypatch.setattr("mail.compose.ask_model", model)
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "Hi", "body": "Tell us what you need.", "ai": True}])
        await _go(user, jid, cid, bot)
        assert "4,999" not in (await _emails(user))[0].body and "Tell us what you need" in (await _emails(user))[0].body
        jid2, cid2, bot2 = await _seed(user, [{"type": "email", "subject": "Hi", "body": "The words stand.", "ai": True}], email="d@example.com", e164="+919876543215")
        await journeys.fire(user.id, bot2, "new_lead", cid2, now=AT_NOON)
        await journeys.tick(AT_NOON + journeys.START_DELAY)
        assert (await _emails(user, "d@example.com"))[0].body == "The words stand."
    run(go)


def test_no_connection_is_held_while_a_model_writes(make_user, run, monkeypatch):
    user = make_user()
    seen = []
    async def model(*_a, **_k):
        seen.append(True)
        return "Written."
    monkeypatch.setattr("mail.compose.ask_model", model)
    commits = []
    real = journeys._write_email
    async def spy(db, *a):
        original = db.commit
        async def counted():
            commits.append(len(seen))
            await original()
        db.commit = counted
        try:
            return await real(db, *a)
        finally:
            db.commit = original
    monkeypatch.setattr(journeys, "_write_email", spy)
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "Hi", "body": "x", "ai": True}])
        await _go(user, jid, cid, bot)
        assert seen and commits == [0], "it committed before the model was asked"
    run(go)


def test_a_date_starts_a_journey_once_on_its_day(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "Due on {{service_due}}", "body": "x"}], trigger="date", value="service_due", options={"days_before": 7},
                                    details={"Service due": "10/11/2026"})
        await journeys.tick(datetime(2026, 11, 1, 6, 30))
        assert await _run(jid) is None, "not yet"
        await journeys.tick(datetime(2026, 11, 3, 6, 30))
        assert (await _run(jid)).status == "done"
        await journeys.tick(datetime(2026, 11, 3, 7, 30))  # the same day: once
        assert [e.subject for e in await _emails(user)] == ["Due on 10/11/2026"]
    run(go)


def test_a_yearly_date_ignores_the_year(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "notify", "text": "x"}], trigger="date", value="birthday", options={"days_before": 0, "yearly": True}, details={"birthday": "3 Nov 1990"})
        await journeys.tick(datetime(2026, 11, 3, 6, 30))
        assert await _run(jid) is not None
    run(go)


def test_dates_are_read_as_people_write_them():
    from datetime import date
    assert journeys.date_of("2026-11-10") == journeys.date_of("10/11/2026") == journeys.date_of("10-11-2026") == journeys.date_of("10 Nov 2026") == date(2026, 11, 10)
    assert journeys.date_of("soon") is None and journeys.date_of(None) is None


@pytest.mark.parametrize("steps,word", [([], "at least one"), ([{"type": "email", "subject": "", "body": "x"}], "subject"), ([{"type": "wait"}], "wait"), ([{"type": "sms"}], "knows"),
                                        ([{"type": "branch", "if": "maybe"}], "check"), ([{"type": "update"}], "change"), ([{"type": "email", "subject": "s", "body": "b"}] * 21, "up to")])
def test_bad_steps_are_refused(steps, word):
    with pytest.raises(ValueError, match=word):
        journeys.checked(steps)


def test_every_ready_made_journey_is_valid():
    for key, ready in journeys.READY.items():
        journeys.checked(ready["steps"])
        journeys.checked_start(ready["trigger"], ready.get("trigger_value"), ready.get("goal"), ready.get("options"))


def test_stages_move_forward_by_themselves():
    c = Contact()
    journeys.move_stage(c, "interested")
    assert c.stage == "interested"
    journeys.move_stage(c, "contacted")
    assert c.stage == "interested"
    journeys.move_stage(c, "lost")
    assert c.stage == "lost"
    journeys.move_stage(c, "meeting")
    assert c.stage == "meeting"
    journeys.move_stage(c, "customer")
    journeys.move_stage(c, "lost")
    assert c.stage == "customer"


def test_a_rating_moves_the_stage(make_user, run):
    from voice import schedule
    c = Contact()
    schedule.rate(c, "hot", "x")
    assert c.stage == "interested"
    schedule.rate(c, "not_interested", "x")
    assert c.stage == "lost"


def test_the_api_saves_a_journey_and_turning_it_on_needs_a_reply_address(make_user, client):
    user = make_user()
    bot = user.bot()
    made = client.post("/api/email/journeys", json={"bot_id": bot, "ready": "meeting_missed"}, headers=user.h()).json()
    assert made["trigger"] == "meeting_missed" and not made["enabled"]
    body = {k: made[k] for k in ("name", "trigger", "trigger_value", "goal", "steps", "options")}
    refused = client.put(f"/api/email/journeys/{made['id']}", json={**body, "enabled": True}, headers=user.h())
    assert refused.status_code == 400 and "replies" in refused.json()["detail"]
    assert client.put(f"/api/email/journeys/{made['id']}", json={**body, "steps": []}, headers=user.h()).status_code == 400
    changed = client.put(f"/api/email/journeys/{made['id']}", json={**body, "name": "Missed them"}, headers=user.h())
    assert changed.status_code == 200, changed.text
    assert changed.json()["name"] == "Missed them" and [x["type"] for x in changed.json()["steps"]] == [x["type"] for x in made["steps"]] and not changed.json()["enabled"]
    client.put("/api/email/senders/" + bot, json={"reply_to": "team@example.com"}, headers=user.h())
    on = client.put(f"/api/email/journeys/{made['id']}", json={**body, "enabled": True}, headers=user.h())
    assert on.status_code == 200 and on.json()["enabled"], on.text
    listed = client.get(f"/api/email/journeys?bot_id={bot}", headers=user.h()).json()
    assert [j["id"] for j in listed["items"]] == [made["id"]] and listed["cap"] == {"per_day": 1, "per_week": 3}
    assert {r["key"] for r in listed["ready"]} >= {"new_lead", "after_call", "not_reached", "meeting_missed", "cold", "customer", "service_due"}
    assert any(a["name"] == "Follow-up calls by lead status" for a in listed["already_running"])
    assert client.delete(f"/api/email/journeys/{made['id']}", headers=user.h()).json() == {"status": "deleted"}


def test_journeys_belong_to_their_workspace(make_user, client):
    user, other = make_user(), make_user()
    made = client.post("/api/email/journeys", json={"bot_id": user.bot(), "name": "Mine"}, headers=user.h()).json()
    assert client.delete(f"/api/email/journeys/{made['id']}", headers=other.h()).status_code == 404
    assert client.get(f"/api/email/journeys/{made['id']}/runs", headers=other.h()).status_code == 404
    assert client.get(f"/api/email/journeys?bot_id={user.bot()}", headers=other.h()).status_code == 404


def test_the_board_moves_a_lead_and_keeps_the_status_in_step(make_user, client, run):
    user = make_user()
    async def seed():
        return await _seed(user, [{"type": "email", "subject": "Welcome", "body": "x"}], trigger="customer")
    jid, cid, bot = run(seed)
    board = client.get(f"/api/email/board/{bot}", headers=user.h()).json()
    assert [(l["id"], l["stage"]) for l in board["leads"]] == [(cid, "new")]
    done = client.put(f"/api/email/board/leads/{cid}", json={"stage": "customer", "tags": ["vip", "vip"], "assigned_to": user.id}, headers=user.h()).json()
    assert (done["stage"], done["status"], done["tags"], done["assigned_to"]) == ("customer", "customer", ["vip"], user.id)
    assert run(_run, jid) is not None, "becoming a customer started the journey"
    back = client.put(f"/api/email/board/leads/{cid}", json={"stage": "interested"}, headers=user.h()).json()
    assert (back["stage"], back["status"]) == ("interested", "warm")
    assert client.put(f"/api/email/board/leads/{cid}", json={"stage": "lost"}, headers=user.h()).json()["status"] == "not_interested"
    assert client.put(f"/api/email/board/leads/{cid}", json={"stage": "nope"}, headers=user.h()).status_code == 400


def test_the_feedback_page_only_asks_and_a_bad_answer_tells_the_team(make_user, client, run, monkeypatch):
    from auth import issue_scoped_token
    from notify import events
    told = []
    async def team(to, subject, text, owner=None):
        told.append(subject)
    monkeypatch.setattr(events, "_email_team", team)
    user = make_user()
    async def seed():
        return await _seed(user, [{"type": "wait", "days": 1}])
    _, cid, _ = run(seed)
    token = issue_scoped_token(cid, "email_feedback", 3600)
    assert "How was it" in client.get(f"/api/email/p/feedback?token={token}").text
    async def details():
        async with async_session() as db:
            return (await db.get(Contact, cid)).details
    assert run(details) == {}, "opening the link changed nothing"
    client.post(f"/api/email/p/feedback?token={token}", data={"action": "bad", "comment": "Too slow"})
    assert run(details) == {"Feedback": "Not good", "Feedback comment": "Too slow"} and told == ["Feedback from Asha Rao: not good"]
    assert "expired" in client.get("/api/email/p/feedback?token=nope").text


# ─── the whole journey, on a fake clock ──────────────────────────
LEAD_STEPS = [{"type": "email", "subject": "Thanks", "body": "x"}, {"type": "wait", "days": 1}, {"type": "whatsapp", "text": "Hi {{first_name|there}}"}, {"type": "wait", "days": 1},
              {"type": "call", "about": "Try them"}, {"type": "wait", "days": 1}, {"type": "notify", "text": "Worth a call"}]
EFFECTS = ["email", "whatsapp", "call", "team"]


async def _whatsapp_chat(user, bot, e164="+919876543210"):
    from backend.models import WhatsAppChat, WhatsAppNumber
    async with async_session() as db:
        conv = Conversation(bot_id=bot, visitor_session_id=f"wa:{e164}")
        number = WhatsAppNumber(user_id=user.id, bot_id=bot, phone_number_id=f"pn-{bot[:8]}", access_token="tok", status="connected")
        db.add_all([conv, number])
        await db.flush()
        db.add(WhatsAppChat(number_id=number.id, user_id=user.id, bot_id=bot, conversation_id=conv.conversation_id, wa_user=e164, wa_id=e164.lstrip("+"), last_inbound_at=datetime.utcnow()))
        await db.commit()


async def _reply(user, bot, automatic=False):
    """Through the code that keeps a reply."""
    from mail import inbound
    async with async_session() as db:
        thread = EmailThread(user_id=user.id, bot_id=bot, code=uuid.uuid4().hex[:16], email="asha@example.com")
        db.add(thread)
        await db.flush()
        row = ThreadMessage(thread_id=thread.id, direction="in", who="customer", status="working", sender="asha@example.com", subject="Re: Thanks", text="Yes please", automatic=automatic)
        db.add(row)
        await inbound._their_reply(db, row, thread)
        await db.commit()


async def _effects(user, bot, sent):
    jobs = await _emails(user)
    async with async_session() as db:
        calls = (await db.execute(select(CallbackJob).where(CallbackJob.bot_id == bot, CallbackJob.kind == "follow_up"))).scalars().all()
    return ["email"] * len(jobs) + [s for s in sent if s == "whatsapp"] + ["call"] * len(calls) + [s for s in sent if s == "team"]


@pytest.fixture
def lead_journey(make_user, monkeypatch):
    """The "new website lead" journey, with what it sends written down."""
    from notify import events
    from whatsapp import outbound
    _follow_ups_on(monkeypatch)
    sent = []
    async def whatsapp(number, chat, text, *, sent_by, **_k):
        sent.append("whatsapp")
        assert text == "Hi Asha" and sent_by == "ai"
        return SimpleNamespace(status="sent", error=None)
    async def team(*_a, **_k):
        sent.append("team")
    monkeypatch.setattr(outbound, "send_text", whatsapp)
    monkeypatch.setattr(events, "_email_team", team)
    return make_user(), sent


@pytest.mark.parametrize("reply_before", range(5))
def test_the_new_website_lead_journey_stops_on_a_reply_at_every_step(lead_journey, run, reply_before):
    user, sent = lead_journey
    async def go():
        jid, cid, bot = await _seed(user, LEAD_STEPS)
        await _whatsapp_chat(user, bot)
        assert await journeys.fire(user.id, bot, "new_lead", cid, "chat", now=AT_NOON) == 1
        clock = AT_NOON + journeys.START_DELAY
        for step in range(4):
            if step == reply_before:
                await _reply(user, bot)
            await journeys.tick(clock)
            r = await _run(jid)
            clock = (r.next_at or (clock + timedelta(days=1)).replace(tzinfo=None))
            clock = clock.replace(tzinfo=None)
            async with async_session() as db:  # sent, so the cap of one a day is about tomorrow's
                for job in (await db.execute(select(EmailJob).where(EmailJob.user_id == user.id))).scalars().all():
                    job.status = "sent" if job.status == "queued" else job.status
                await db.commit()
        await journeys.tick(clock + timedelta(days=30))
        return await _effects(user, bot, sent), await _run(jid)
    effects, r = run(go)
    assert effects == EFFECTS[:reply_before]
    assert (r.status, r.reason) == (("stopped", "They replied") if reply_before < 4 else ("done", "It ran to the end"))


def test_the_new_website_lead_journey_runs_to_its_end(lead_journey, run):
    user, sent = lead_journey
    async def go():
        jid, cid, bot = await _seed(user, LEAD_STEPS)
        await _whatsapp_chat(user, bot)
        await journeys.fire(user.id, bot, "new_lead", cid, "chat", now=AT_NOON)
        clock = AT_NOON + journeys.START_DELAY
        seen = []
        for _ in range(4):
            await journeys.tick(clock)
            r = await _run(jid)
            seen.append(r.next_at.replace(tzinfo=None) if r.next_at else None)
            if r.next_at:
                local = r.next_at.replace(tzinfo=None) + timedelta(hours=5, minutes=30)
                assert 9 <= local.hour < 20, "waits end in the daytime"
                clock = r.next_at.replace(tzinfo=None)
        return await _effects(user, bot, sent), await _run(jid)
    effects, r = run(go)
    assert effects == EFFECTS and r.status == "done"


def test_an_out_of_office_reply_doesnt_stop_it(make_user, run):
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "wait", "days": 1}, {"type": "email", "subject": "Hi", "body": "x"}])
        await _go(user, jid, cid, bot)
        await _reply(user, bot, automatic=True)
        assert (await _run(jid)).status == "active"
    run(go)


# ─── what starts them ────────────────────────────────────────────
ONE = [{"type": "wait", "days": 1}]


def test_a_chat_lead_starts_a_journey(make_user, run):
    from notify import events
    user = make_user()
    async def go():
        jid, _, bot = await _seed(user, ONE, value="chat", e164="+919800000001", email="someone@example.com")
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id="widget-session-ai-1", captured_data={"name": "Ravi", "email": "ravi@example.com"})
            db.add(conv)
            await db.commit()
        await events.lead_captured(conv.conversation_id)
        r = await _run(jid)
        async with async_session() as db:
            assert (await db.get(Contact, r.contact_id)).email == "ravi@example.com"
    run(go)


def test_a_lead_from_a_portal_starts_a_journey(make_user, run):
    from backend.models import Bot
    from mail import intake
    user = make_user()
    async def go():
        jid, _, bot = await _seed(user, ONE, value="portal", e164="+919800000002", email="someone@example.com")
        async with async_session() as db:
            row = await db.get(Bot, bot)
        await intake.act(row, {"name": "Ravi", "email": "ravi@example.com", "phone": "+919800000003", "portal": "IndiaMART"})
        assert await _run(jid) is not None
    run(go)


def _phone_call(user_id, bot, **values):
    return CallLog(**{**dict(user_id=user_id, bot_id=bot, caller_e164="+919876543210", direction="inbound", channel="phone", outcome="answered", summary="Asked about it.",
                             started_at=datetime.utcnow() - timedelta(minutes=5)), **values})


def test_a_new_status_after_a_call_starts_a_journey_but_a_test_call_doesnt(make_user, run):
    from voice import router, schedule
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, ONE, trigger="status", value="hot", calls=3)
        async with async_session() as db:
            test = _phone_call(user.id, bot, lead="hot", consent_source=router.TEST_CALL)
            db.add(test)
            await db.commit()
        await schedule.after_call(test.id)
        assert await _run(jid) is None, "the business trying its own agent"
        async with async_session() as db:
            (await db.get(Contact, cid)).lead_status = "warm"
            real = _phone_call(user.id, bot, lead="hot")
            db.add(real)
            await db.commit()
        await schedule.after_call(real.id)
        assert (await _run(jid)).status == "active"
        async with async_session() as db:
            assert (await db.get(Contact, cid)).stage == "interested"
    run(go)


def test_a_first_call_is_a_new_lead(make_user, run):
    from voice import schedule
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, ONE, value="call", calls=1)
        async with async_session() as db:
            call = _phone_call(user.id, bot)
            db.add(call)
            await db.commit()
        await schedule.after_call(call.id)
        assert await _run(jid) is not None
    run(go)


def test_the_team_marking_a_lead_starts_journeys(make_user, client, run):
    user = make_user()
    async def seed():
        one = await _seed(user, ONE, trigger="status", value="warm")
        async with async_session() as db:
            two = Journey(user_id=user.id, bot_id=one[2], name="Customer", trigger="customer", steps=ONE, enabled=True)
            db.add(two)
            await db.commit()
        return one, two.id
    (status, cid, _), customer = run(seed)
    assert client.patch(f"/api/voice/schedule/contacts/{cid}", json={"lead_status": "warm"}, headers=user.h()).status_code == 200
    assert run(_run, status) is not None
    assert client.patch(f"/api/voice/schedule/contacts/{cid}", json={"lead_status": "customer"}, headers=user.h()).status_code == 200
    assert run(_run, customer) is not None


def test_a_meeting_booked_attended_or_missed_starts_journeys(make_user, run):
    from test_voice_schedule import _save
    from voice import meetings, schedule
    user = make_user()
    bot = user.spare[-1]
    _save(run, user.id, bot)
    day = (datetime.utcnow() + timedelta(days=2)).date()
    async def go():
        booked, cid, _ = await _seed(user, ONE, trigger="meeting_booked")
        async with async_session() as db:
            attended = Journey(user_id=user.id, bot_id=bot, name="A", trigger="meeting_attended", steps=ONE, enabled=True)
            missed = Journey(user_id=user.id, bot_id=bot, name="M", trigger="meeting_missed", steps=ONE, enabled=True)
            db.add_all([attended, missed])
            await db.commit()
        tools = await schedule.tools_for(user.id, bot, "+919876543210", None, call_id=lambda: "call-9")
        said = await tools.run("book_meeting", {"date": day.isoformat(), "time": "10:30", "topic": "Plans", "name": "Asha"})
        assert said.startswith(("Requested", "Booked")), said
        await asyncio.sleep(0.3)  # it starts in the background
        assert await _run(booked) is not None
        async with async_session() as db:
            assert (await db.get(Contact, cid)).stage == "meeting"
            meeting = (await db.execute(select(Meeting).where(Meeting.bot_id == bot))).scalars().first()
        await meetings.after_meeting(meeting.id, True)
        assert await _run(attended.id) is not None and await _run(missed.id) is None
        await meetings.after_meeting(meeting.id, False)
        assert await _run(missed.id) is not None
    run(go)


def test_a_plan_without_journeys_starts_none_and_stops_those_running(make_user, run, monkeypatch):
    import plans
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "wait", "days": 1}, {"type": "email", "subject": "Hi", "body": "x"}])
        await _go(user, jid, cid, bot)
        r = await _run(jid)
        real = plans.includes
        async def starter(db, bot_id):
            included = await real(db, bot_id)
            return SimpleNamespace(**{**included.__dict__, "email_alerts": False})
        monkeypatch.setattr(plans, "includes", starter)
        await journeys.tick(r.next_at.replace(tzinfo=None))
        assert (await _run(jid)).reason == "The plan no longer includes journeys"
        assert await journeys.fire(user.id, bot, "customer", cid) == 0
    run(go)


def test_write_with_ai_makes_a_journey_that_is_off_without_invented_numbers(make_user, client, monkeypatch):
    user = make_user()
    answer = '''{"name": "Quick follow up", "trigger": "new_lead", "steps": [
        {"type": "email", "subject": "Hi", "body": "Our plan costs Rs 4,999. Tell us what you need."}, {"type": "wait", "hours": 2}, {"type": "whatsapp", "text": "Still there?"}, {"type": "call", "about": "Next morning"}]}'''
    async def model(*_a, **_k):
        return answer
    monkeypatch.setattr("mail.compose.ask_model", model)
    made = client.post("/api/email/journeys/write", json={"bot_id": user.bot(), "text": "Email them now, WhatsApp after 2 hours, call the next morning"}, headers=user.h())
    assert made.status_code == 200, made.text
    j = made.json()
    assert j["enabled"] is False and [s["type"] for s in j["steps"]] == ["email", "wait", "whatsapp", "call"]
    assert "4,999" not in j["steps"][0]["body"] and "Tell us what you need" in j["steps"][0]["body"]


def test_write_with_ai_says_so_when_it_cant(make_user, client, monkeypatch):
    user = make_user()
    async def model(*_a, **_k):
        return "Sorry, I can't."
    monkeypatch.setattr("mail.compose.ask_model", model)
    made = client.post("/api/email/journeys/write", json={"bot_id": user.bot(), "text": "Email them now"}, headers=user.h())
    assert made.status_code == 502


def test_a_ready_made_journey_opens_in_the_business_words_and_keeps_its_own_without_a_model(make_user, client, monkeypatch):
    from voice import llm
    user = make_user()
    bot = user.bot()
    async def knowledge(_bot):
        return "We fix roofs in Chennai."
    monkeypatch.setattr(llm, "call_knowledge", knowledge)
    plain = client.post("/api/email/journeys", json={"bot_id": bot, "ready": "meeting_missed"}, headers=user.h()).json()
    assert "sorry we missed you" in next(s for s in plain["steps"] if s["type"] == "email")["body"]
    async def model(*_a, **_k):
        return '[{"subject": "Roof check?", "body": "Hi {{first_name|there}}, shall we look at your roof another day?"}]'
    monkeypatch.setattr("mail.compose.ask_model", model)
    written = client.post("/api/email/journeys", json={"bot_id": bot, "ready": "meeting_missed"}, headers=user.h()).json()
    assert next(s for s in written["steps"] if s["type"] == "email")["subject"] == "Roof check?"


def test_a_clicked_link_is_seen_by_the_journey(make_user, client, run, monkeypatch):
    from notify import automations, email
    sent = []
    async def deliver(to, subject, text, html_body=None, **_k):
        if subject == "Price list":
            sent.append((text, html_body))
        return SimpleNamespace(ok=True, id="r1", error=None)
    monkeypatch.setattr(email, "deliver", deliver)
    user = make_user()
    async def seed():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "Price list", "body": "See https://example.com/prices?a=1&b=2 today."}, {"type": "wait", "hours": 1},
                                           {"type": "branch", "if": "clicked", "not": True, "then": "end"}, {"type": "email", "subject": "You looked", "body": "x"}])
        now = datetime.utcnow() - timedelta(minutes=2)  # so its email is due
        await journeys.fire(user.id, bot, "new_lead", cid, now=now)
        await journeys.tick(now + journeys.START_DELAY)
        await automations.process_due()
        return jid
    jid = run(seed)
    text, html_body = sent[0]
    assert "example.com/prices" not in text, "the link goes through Nimmi"
    link = next(w for w in text.split() if "/api/email/l/" in w)
    assert f'<a href="{link}"' in html_body
    opened = client.get("/api/email/l/" + link.rsplit("/", 1)[1], follow_redirects=False)
    assert opened.status_code in (302, 303, 307) and opened.headers["location"] == "https://example.com/prices?a=1&b=2"
    async def after():
        r = await _run(jid)
        await journeys.tick(r.next_at.replace(tzinfo=None) + timedelta(hours=1))
        async with async_session() as db:
            for job in (await db.execute(select(EmailJob).where(EmailJob.user_id == user.id, EmailJob.status == "sent"))).scalars().all():
                job.send_at = job.send_at.replace(tzinfo=None) - timedelta(days=2)
            await db.commit()
        r = await _run(jid)
        if r.next_at:
            await journeys.tick(r.next_at.replace(tzinfo=None))
        return [e.subject for e in await _emails(user)]
    assert run(after) == ["Price list", "You looked"]


def test_the_board_only_takes_people_on_the_team(make_user, client, run):
    user = make_user()
    async def seed():
        return await _seed(user, ONE)
    _, cid, bot = run(seed)
    assert client.put(f"/api/email/board/leads/{cid}", json={"assigned_to": "someone-else"}, headers=user.h()).status_code == 400
    assert client.put(f"/api/email/board/leads/{cid}", json={"assigned_to": user.id}, headers=user.h()).json()["assigned_to"] == user.id
    assert client.get(f"/api/email/board/{bot}", headers=user.h()).json()["leads"][0]["phone"].startswith("+91 ")


def test_a_lead_board_card_of_another_workspace_is_out_of_reach(make_user, client, run):
    user, other = make_user(), make_user()
    async def seed():
        return await _seed(user, ONE)
    _, cid, bot = run(seed)
    assert client.put(f"/api/email/board/leads/{cid}", json={"stage": "lost"}, headers=other.h()).status_code == 404
    assert client.get(f"/api/email/board/{bot}", headers=other.h()).status_code == 404


def test_addresses_in_an_email_are_links_and_nothing_else_is_html():
    from notify import automations
    made = automations.html_email('See https://x.in/a?b=1&c=2 <script>alert(1)</script>', "Shop", None)
    assert '<a href="https://x.in/a?b=1&amp;c=2"' in made and "<script>" not in made


def test_nimmi_turns_a_journey_on_and_moves_a_lead_and_both_undo(make_user, client, run):
    from agent import registry
    from auth import AuthContext
    user = make_user()
    async def seed():
        return await _seed(user, [{"type": "email", "subject": "Hi", "body": "x"}], enabled=False)
    jid, cid, bot = run(seed)
    client.put("/api/email/senders/" + bot, json={"reply_to": "team@example.com"}, headers=user.h())
    ctx = AuthContext(user.id, user.id, "owner")
    tc = registry.ToolContext(ctx=ctx, run_id="r", thread_id="t", screen={})
    assert run(registry.run, tc, "email_journeys", {"assistant_id": bot}).ok
    assert run(registry.run, tc, "email_journeys", {"assistant_id": bot, "journey_id": jid}).ok
    assert run(registry.run, tc, "lead_board", {"assistant_id": bot}).ok
    on = run(registry.run, tc, "set_journey", {"journey_id": jid, "on": True})
    assert on.ok, on
    async def enabled():
        async with async_session() as db:
            return (await db.get(Journey, jid)).enabled
    assert run(enabled) is True
    moved = run(registry.run, tc, "update_lead", {"lead_id": cid, "stage": "interested", "tags": ["vip"]})
    assert moved.ok, moved
    async def stage():
        async with async_session() as db:
            c = await db.get(Contact, cid)
            return c.stage, c.tags
    assert run(stage) == ("interested", ["vip"])
    run(registry.undo_action, ctx, on.action_id)
    assert run(enabled) is False
    run(registry.undo_action, ctx, moved.action_id)
    assert run(stage) == ("new", [])
    other = make_user()
    theirs = registry.ToolContext(ctx=AuthContext(other.id, other.id, "owner"), run_id="r", thread_id="t", screen={})
    assert not run(registry.run, theirs, "set_journey", {"journey_id": jid, "on": True}).ok
    assert not run(registry.run, theirs, "update_lead", {"lead_id": cid, "stage": "lost"}).ok


def test_write_with_ai_takes_what_starts_and_ends_it(make_user, client, monkeypatch):
    user = make_user()
    answer = '''{"name": "Hot leads", "trigger": "status", "trigger_value": "hot", "goal": "booked", "steps": [{"type": "wait", "days": 3}, {"type": "notify", "text": "They haven't booked"}]}'''
    async def model(*_a, **_k):
        return answer
    monkeypatch.setattr("mail.compose.ask_model", model)
    j = client.post("/api/email/journeys/write", json={"bot_id": user.bot(), "text": "If a hot lead doesn't book in 3 days, tell my team"}, headers=user.h()).json()
    assert (j["trigger"], j["trigger_value"], j["goal"]) == ("status", "hot", "booked")


def test_write_with_ai_keeps_good_steps_when_it_gets_the_start_wrong(make_user, client, monkeypatch):
    user = make_user()
    async def model(*_a, **_k):
        return '{"name": "X", "trigger": "status", "trigger_value": "furious", "steps": [{"type": "call", "about": "Ask"}]}'
    monkeypatch.setattr("mail.compose.ask_model", model)
    j = client.post("/api/email/journeys/write", json={"bot_id": user.bot(), "text": "Call them"}, headers=user.h()).json()
    assert (j["trigger"], j["trigger_value"], j["goal"]) == ("new_lead", None, "replied") and j["steps"][0]["type"] == "call"


def test_a_ready_made_email_that_loses_a_placeholder_keeps_its_own_words(make_user, client, monkeypatch):
    from voice import llm
    user = make_user()
    async def knowledge(_bot):
        return "We service air conditioners."
    async def model(*_a, **_k):
        return '[{"subject": "Your AC", "body": "Hi {{first_name|there}}, your service is due soon."}]'
    monkeypatch.setattr(llm, "call_knowledge", knowledge)
    monkeypatch.setattr("mail.compose.ask_model", model)
    j = client.post("/api/email/journeys", json={"bot_id": user.bot(), "ready": "service_due"}, headers=user.h()).json()
    assert "{{service_due}}" in j["steps"][0]["body"], "the date is the point of it"


def test_a_journey_for_customers_cant_end_by_someone_being_a_customer():
    assert journeys.checked_start("customer", None, "customer", None)[1] is None
    assert journeys.checked_start("status", "customer", "customer", None)[1] is None
    assert journeys.checked_start("status", "hot", "customer", None)[1] == "customer"


def test_an_address_that_cant_take_mail_is_skipped_and_the_journey_goes_on(make_user, run, monkeypatch):
    from mail import address
    async def nowhere(domain):
        return False
    monkeypatch.setattr(address, "_lookup", nowhere)
    address._cache.clear()
    user = make_user()
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "Hi", "body": "x"}, {"type": "notify", "text": "Tell them", "todo": True}], email="asha@nowhere.example")
        await journeys.fire(user.id, bot, "new_lead", cid, now=AT_NOON)
        await journeys.tick(AT_NOON + journeys.START_DELAY)
        r = await _run(jid)
        assert await _emails(user, "asha@nowhere.example") == [] and r.history[0]["what"].startswith("Skipped") and r.status == "done"
    run(go)


def test_an_ai_email_that_loses_the_link_keeps_the_words_it_was_given(make_user, run, monkeypatch):
    user = make_user()
    async def model(*_a, **_k):
        return "Hi Asha, please leave us a review."
    monkeypatch.setattr("mail.compose.ask_model", model)
    async def go():
        jid, cid, bot = await _seed(user, [{"type": "email", "subject": "Hi", "body": "Please review us: https://g.page/r/abc", "ai": True}])
        await _go(user, jid, cid, bot)
        assert "https://g.page/r/abc" in (await _emails(user))[0].body
    run(go)


def test_a_conversation_moves_someone_to_contacted(make_user, run):
    from voice import schedule
    user = make_user()
    async def go():
        _, cid, bot = await _seed(user, ONE, calls=2)
        async with async_session() as db:
            call = _phone_call(user.id, bot)
            db.add(call)
            await db.commit()
        await schedule.after_call(call.id)
        async with async_session() as db:
            assert (await db.get(Contact, cid)).stage == "contacted"
        _, cid2, bot2 = await _seed(user, ONE, e164="+919876500123", email="asha@example.com")
        await _reply(user, bot2)
        async with async_session() as db:
            assert (await db.get(Contact, cid2)).stage == "contacted"
    run(go)


def test_write_with_ai_says_when_no_model_answers(make_user, client, monkeypatch):
    user = make_user()
    async def down(*_a, **_k):
        raise ConnectionError("no network")
    monkeypatch.setattr("mail.compose.ask_model", down)
    made = client.post("/api/email/journeys/write", json={"bot_id": user.bot(), "text": "Email them now"}, headers=user.h())
    assert made.status_code == 503 and "Try again" in made.json()["detail"]

