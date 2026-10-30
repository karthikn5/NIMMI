"""Voice > Schedule: call-backs booked on calls, follow-ups by lead rating, meetings with the team's OK, and the calls
and reminders they lead to."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.future import select

from database import async_session
from backend.models import (CallbackJob, CallLog, Campaign, Contact, DncEntry, Meeting, NotificationLog, PhoneNumber,
                            ScheduleSettings, VoiceAgent, WorkspaceSettings)
from voice import functions, llm, meetings, schedule, scheduler, twilio
from voice import router as voice_router

IST = ZoneInfo("Asia/Kolkata")
NUMBER = "+919876543210"
ALL_DAYS = list(schedule.DAYS)
WIDE = ["00:00", "23:59"]


def _raw(**parts) -> dict:
    """Everything on, at any hour on any day (so tests don't depend on when they run); `parts` override."""
    raw = {"callbacks": {"enabled": True, "hours": WIDE},
           "follow_ups": {"enabled": True, "hours": WIDE, "days": ALL_DAYS},
           "meetings": {"enabled": True, "hours": ["10:00", "12:00"], "days": ALL_DAYS, "notice_hours": 0,
                        "link": "https://meet.example.com/desk"}}
    for part, values in parts.items():
        raw[part] = {**raw.get(part, {}), **values}
    return raw


def _save(run, owner, bot, **parts) -> dict:
    settings = schedule.clean(_raw(**parts))

    async def go():
        async with async_session() as db:
            row = await db.get(ScheduleSettings, bot)
            if row is None:
                db.add(ScheduleSettings(bot_id=bot, user_id=owner, settings=settings))
            else:
                row.settings = settings
            await db.commit()
    run(go)
    return settings


def _add(run, *rows):
    async def go():
        async with async_session() as db:
            db.add_all(rows)
            await db.commit()
    run(go)
    return rows[0] if len(rows) == 1 else rows


def _jobs(run, bot, **where):
    async def go():
        async with async_session() as db:
            query = select(CallbackJob).where(CallbackJob.bot_id == bot)
            for key, value in where.items():
                query = query.where(getattr(CallbackJob, key) == value)
            return (await db.execute(query.order_by(CallbackJob.created_at))).scalars().all()
    return run(go)


def _get(run, model, key):
    async def go():
        async with async_session() as db:
            return await db.get(model, key)
    return run(go)


def _contact(owner, bot, **values) -> Contact:
    base = dict(user_id=owner, bot_id=bot, e164=NUMBER, name="Priya Raman", calls=1, details={},
                last_call_at=datetime.utcnow() - timedelta(minutes=5))
    return Contact(**{**base, **values})


def _call(owner, bot, **values) -> CallLog:
    base = dict(user_id=owner, bot_id=bot, caller_e164=NUMBER, direction="inbound", channel="phone", outcome="answered",
                summary="Asked about the Gold plan.", started_at=datetime.utcnow() - timedelta(minutes=5), number_id="num-1")
    return CallLog(**{**base, **values})


def _local(day: date, hhmm: str) -> datetime:
    return schedule.local_time(day.isoformat(), hhmm, IST)


def _midday_yesterday() -> datetime:
    """A call's start that keeps "their hour" well inside the calling hours, whenever the tests run (a call minutes ago,
    run after 23:44, put their hour past the last one allowed)."""
    return _local(datetime.now(IST).date() - timedelta(days=1), "12:00").astimezone(timezone.utc).replace(tzinfo=None)


# ─── settings and times ──────────────────────────────────────────
def test_everything_starts_off_and_settings_stay_in_range():
    default = schedule.clean(None)
    assert not (default["callbacks"]["enabled"] or default["follow_ups"]["enabled"] or default["meetings"]["enabled"])
    assert default["timezone"] == "Asia/Kolkata" and default["follow_ups"]["stop_after_days"] == 7
    odd = schedule.clean({"callbacks": {"attempts": 99, "hours": ["21:00", "09:00"]},
                          "follow_ups": {"days": ["someday"], "rules": {"hot": {"count": 9, "every": 0}}},
                          "meetings": {"link": "ftp://x", "whatsapp_template": "Bad Name", "minutes": 7, "kinds": ["video"]}})
    assert odd["callbacks"]["attempts"] == 5 and odd["callbacks"]["hours"] == ["09:00", "21:00"]
    assert odd["follow_ups"]["days"] == schedule.DAYS[:6] and odd["follow_ups"]["rules"]["hot"] == {"count": 5, "every": 1}
    assert odd["meetings"]["link"] == "" and odd["meetings"]["whatsapp_template"] == "" and odd["meetings"]["minutes"] == 30
    assert odd["meetings"]["kinds"] == ["online"]
    for bad, message in [({"callbacks": {"hours": ["21:00", "09:00"]}}, "start before the end"),
                         ({"meetings": {"link": "meet.google.com/abc"}}, "https://"),
                         ({"meetings": {"enabled": True, "kinds": ["in_person"]}}, "address"),
                         ({"timezone": "Mars/Base"}, "time zone")]:
        with pytest.raises(schedule.ScheduleError, match=message):
            schedule.check(bad)


def test_call_back_times_from_what_the_caller_said():
    settings = schedule.clean({"callbacks": {"enabled": True, "hours": ["09:00", "21:00"]}})
    now = _local(date(2026, 10, 29), "15:00")  # a Thursday afternoon in India

    def at(args):
        when, problem = schedule.callback_time(args, settings, now)
        return when.astimezone(IST).strftime("%a %H:%M") if when else problem
    assert at({"in_minutes": 10}) == "Thu 15:10"
    assert at({"when": "in 10 minutes"}) == at({"when": "10 min"}) == "Thu 15:10"
    assert at({"when": "after 2 hours"}) == "Thu 17:00"
    assert at({"when": "2026-10-30 09:00"}) == at({"when": "2026-10-30T09:00"}) == "Fri 09:00"
    assert at({"when": "16:45"}) == "Thu 16:45"
    assert "what time" in at({"when": "2026-10-30"}) and "YYYY-MM-DD HH:MM" in at({"when": "tomorrow evening"})
    assert at({"in_minutes": 0.5}) == "Thu 15:02"  # at least two minutes
    assert at({"date": "2026-10-30", "time": "11:00"}) == "Fri 11:00"
    assert at({"time": "4:30 pm"}) == "Thu 16:30"
    assert "outside calling hours (9 am to 9 pm)" in at({"time": "22:30"}) and "tomorrow at 9 am" in at({"time": "22:30"})
    assert "what time" in at({"date": "2026-10-30"})
    assert "already passed" in at({"time": "10:00"})
    assert "30 days" in at({"date": "2026-12-15", "time": "11:00"})
    assert "Ask the caller when" in at({})
    friday = _local(date(2026, 10, 30), "16:00")
    assert schedule.when_text(friday, IST, now) == "tomorrow at 4 pm"
    assert schedule.when_text(_local(date(2026, 11, 2), "10:30"), IST, now) == "Monday 2 November at 10:30 am"
    assert schedule.spoken_when(friday, IST, "ta-IN", now) == "நாளைக்கு சாயங்காலம் 4 மணிக்கு"
    assert schedule.spoken_when(_local(date(2026, 10, 31), "18:30"), IST, "hi-IN", now) == "शनिवार, 31 अक्टूबर को शाम 6:30 बजे"
    assert schedule.spoken_when(_local(date(2026, 11, 2), "10:00"), IST, "en-IN", now) == "on Monday 2 November at 10 am"
    nine = schedule.next_allowed(_local(date(2026, 10, 31), "20:00"), ["10:00", "19:00"], schedule.DAYS[:6], IST)
    assert nine.astimezone(IST).strftime("%a %H:%M") == "Mon 10:00"  # Saturday evening -> Monday morning (no Sundays)


# ─── call-backs on a call ─────────────────────────────────────────
def test_the_agent_books_a_call_back_and_it_replaces_whats_waiting(run, make_user):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot, meetings={"enabled": False})
    _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="follow_up", status="queued", consent_source="t",
                          next_attempt_at=datetime.utcnow() + timedelta(days=2)))

    async def scenario():
        tools = await schedule.tools_for(u.id, bot, NUMBER, "num-1", name="Priya", call_id=lambda: "call-1")
        names = tools.names()
        first = await tools.run("schedule_callback", {"when": "in 10 minutes", "about": "plan prices"})
        second = await tools.run("schedule_callback", {"when": "in 30 minutes"})
        after = tools.names()
        cancelled = await tools.run("cancel_callback", {})
        browser = await schedule.tools_for(u.id, bot, None, None, test=True)
        test = await browser.run("schedule_callback", {"in_minutes": 10})
        return names, first, second, after, cancelled, test

    names, first, second, after, cancelled, test = run(scenario)
    assert names == {"schedule_callback"} and "cancel_callback" in after
    assert first.startswith("Booked: you'll call them back today at") or first.startswith("Booked: you'll call them back tomorrow")
    callbacks = _jobs(run, bot, kind="callback")
    assert len(callbacks) == 1  # the second booking moved the first
    job = callbacks[0]
    assert job.status == "cancelled" and "don't need it" in job.last_error  # then they called it off
    assert (job.from_number_id, job.source_call_id, job.purpose, job.name) == ("num-1", "call-1", "plan prices", "Priya")
    assert "Asked on a call" in job.consent_source
    assert schedule.utc(job.next_attempt_at) - datetime.now(timezone.utc) > timedelta(minutes=25)
    assert [j.status for j in _jobs(run, bot, kind="follow_up")] == ["cancelled"]  # a call-back replaces the follow-up
    assert cancelled.startswith("Cancelled") and "test call in the browser" in test


def test_the_model_runs_schedule_functions_beside_the_agents_own(run, monkeypatch):
    prompts, ran = [], []

    def model(bot, prompt, history, text, ai_model, answered, tools):
        prompts.append((prompt, [t["name"] for t in tools or []]))
        if len(prompts) == 1:
            yield llm.ToolCall("call_1", "schedule_callback", {"in_minutes": 10})
        else:
            yield "Sure, I'll call you back in ten minutes."
    monkeypatch.setattr(llm, "stream_reply", model)

    class Tools:
        def specs(self):
            return [{"name": "schedule_callback", "description": "Book a call back.", "parameters": {"type": "object", "properties": {}}}]

        def rules(self):
            return "\n- RULES FOR CALL-BACKS"

        def has(self, name):
            return name == "schedule_callback"

        async def run(self, name, args):
            ran.append((name, args))
            return "Booked: you'll call them back today at 4:40 pm."
    agent = llm.VoiceAgent(language="en-IN", assistant_name="Nimmi", company_name="Shop", greeting="",
                           functions=functions.clean([{"kind": "custom", "name": "check_order", "description": "Orders.",
                                                       "url": "https://shop.example.com/o", "method": "GET"}]))
    log = []

    async def reply():
        return [s async for s in llm.reply_sentences(llm.Bot(bot_name="Shop"), agent, [], "Call me later", "inbound", None,
                                                     knowledge="", function_log=log, schedule_tools=Tools())]
    assert run(reply) == [("Sure, I'll call you back in ten minutes.", None)]
    assert ran == [("schedule_callback", {"in_minutes": 10})]
    prompt, names = prompts[0]
    assert names == ["check_order", "schedule_callback"] and "RULES FOR CALL-BACKS" in prompt and llm.FUNCTION_RULES in prompt
    assert log[1]["content"].startswith("Booked")
    with pytest.raises(functions.FunctionError, match="taken"):
        functions.clean([{"kind": "custom", "name": "book_meeting", "description": "x", "url": "https://x.example.com"}])


# ─── meetings ─────────────────────────────────────────────────────
def test_free_meeting_times_follow_the_hours_bookings_and_holidays(run, make_user):
    u = make_user()
    bot = u.bot()
    settings = _save(run, u.id, bot)
    day = datetime.now(IST).date() + timedelta(days=3)

    async def free(s=settings):
        async with async_session() as db:
            return [t.strftime("%H:%M") for t in (await meetings.free_times(db, s, u.id, bot, day, 1)).get(day, [])]
    assert run(free) == ["10:00", "10:30", "11:00", "11:30"]
    _add(run, Meeting(user_id=u.id, bot_id=bot, e164="+919800000001", starts_at=schedule.stored(_local(day, "10:30")),
                      minutes=30, status="confirmed"))
    assert run(free) == ["10:00", "11:00", "11:30"]
    assert run(free, schedule.clean(_raw(meetings={"at_once": 2}))) == ["10:00", "10:30", "11:00", "11:30"]
    _add(run, WorkspaceSettings(user_id=u.id, business_hours={"holidays": [day.isoformat()]}))
    assert run(free) == []


def test_a_meeting_asked_for_on_a_call_waits_for_the_team_then_gets_a_confirmation_call(run, make_user):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    day = datetime.now(IST).date() + timedelta(days=2)
    _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="follow_up", status="queued", consent_source="t",
                          next_attempt_at=datetime.utcnow() + timedelta(days=1)))

    async def booking():
        tools = await schedule.tools_for(u.id, bot, NUMBER, "num-1", call_id=lambda: "call-7")
        times = await tools.run("check_meeting_times", {"date": day.isoformat()})
        asked = await tools.run("book_meeting", {"date": day.isoformat(), "time": "10:30", "topic": "Gold plan",
                                                 "name": "Priya Raman", "email": "priya@example.com"})
        other = await schedule.tools_for(u.id, bot, "+919800000002", None)
        taken = await other.run("book_meeting", {"date": day.isoformat(), "time": "10:30"})
        await asyncio.sleep(0.3)  # the team's email goes out in the background
        return tools, times, asked, taken
    tools, times, asked, taken = run(booking)
    assert times.startswith(f"Free on {day:%A}") and "10:30 am" in times  # two days out: named, not "tomorrow"
    assert asked.startswith("Requested:") and "call to confirm" in asked
    assert "That time is taken." in taken and "Free times:" in taken and "cancel_meeting" in tools.names()

    async def state():
        async with async_session() as db:
            meeting = (await db.execute(select(Meeting).where(Meeting.bot_id == bot, Meeting.e164 == NUMBER))).scalars().one()
            told = (await db.execute(select(NotificationLog).where(NotificationLog.kind == "meeting_team_requested",
                                                                    NotificationLog.ref_id.startswith(meeting.id)))).scalars().all()
            return meeting, told
    meeting, told = run(state)
    assert (meeting.status, meeting.name, meeting.email, meeting.topic, meeting.source_call_id) == (
        "requested", "Priya Raman", "priya@example.com", "Gold plan", "call-7")
    assert len(told) == 1 and [j.status for j in _jobs(run, bot, kind="follow_up")] == ["cancelled"]

    async def move_it():
        return await tools.run("book_meeting", {"date": day.isoformat(), "time": "11:00"})
    assert run(move_it).startswith("Requested:")
    moved = _get(run, Meeting, meeting.id)
    assert schedule.utc(moved.starts_at).astimezone(IST).strftime("%H:%M") == "11:00" and "Moved on a call" in moved.history[-1]["what"]

    async def approve():
        async with async_session() as db:
            m = await db.get(Meeting, meeting.id)
            await meetings.approve(db, m, by=u.id, host_id=u.id)
            await db.commit()
            return m
    approved = run(approve)
    calls = _jobs(run, bot, kind="meeting")
    assert approved.status == "confirmed" and approved.host_id == u.id
    assert [(j.status, j.variables, j.meeting_id) for j in calls] == [("queued", {"about": "confirmed"}, meeting.id)]


def test_the_team_proposes_another_time_and_the_caller_agrees_on_the_call(run, make_user, client):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot, meetings={"link": ""})
    day = datetime.now(IST).date() + timedelta(days=2)
    meeting = _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, name="Priya", kind="online", status="requested",
                                starts_at=schedule.stored(_local(day, "10:00")), minutes=30, history=[]))
    no_link = client.post(f"/api/voice/schedule/meetings/{meeting.id}/approve", json={}, headers=u.h())
    assert no_link.status_code == 400 and "meeting link" in no_link.json()["detail"]
    proposed = client.post(f"/api/voice/schedule/meetings/{meeting.id}/propose", json={"date": day.isoformat(), "time": "11:30"},
                           headers=u.h())
    assert proposed.status_code == 200 and proposed.json()["status"] == "proposed"
    assert [j.variables for j in _jobs(run, bot, kind="meeting", status="queued")] == [{"about": "proposed"}]

    async def agree():
        tools = await schedule.tools_for(u.id, bot, NUMBER, None)
        return await tools.run("book_meeting", {"date": day.isoformat(), "time": "11:30"})
    assert run(agree).startswith("Booked and confirmed")
    assert _get(run, Meeting, meeting.id).status == "confirmed"
    assert [j.status for j in _jobs(run, bot, kind="meeting")] == ["cancelled"]  # the call to propose it isn't needed now

    other = _add(run, Meeting(user_id=u.id, bot_id=bot, e164="+919800000003", kind="online", status="requested",
                              starts_at=schedule.stored(_local(day, "10:30")), history=[]))
    declined = client.post(f"/api/voice/schedule/meetings/{other.id}/decline", json={"call": True}, headers=u.h())
    assert declined.json()["status"] == "cancelled" and declined.json()["calls"][0]["about"] == "declined"


def test_missed_meetings_get_a_call_and_attended_ones_dont(run, make_user, client):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    past = _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, kind="online", status="confirmed", history=[],
                             starts_at=datetime.utcnow() - timedelta(hours=2)))
    early = client.post(f"/api/voice/schedule/meetings/{past.id}/mark", json={"attended": False}, headers=u.h())
    assert early.status_code == 200 and early.json()["status"] == "no_show"
    assert [(j.kind, j.status) for j in _jobs(run, bot, meeting_id=past.id)] == [("no_show", "queued")]
    fixed = client.post(f"/api/voice/schedule/meetings/{past.id}/mark", json={"attended": True}, headers=u.h())
    assert fixed.json()["status"] == "done" and [j.status for j in _jobs(run, bot, meeting_id=past.id)] == ["cancelled"]
    soon = _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, kind="online", status="confirmed", history=[],
                             starts_at=datetime.utcnow() + timedelta(hours=2)))
    assert client.post(f"/api/voice/schedule/meetings/{soon.id}/mark", json={"attended": True}, headers=u.h()).status_code == 400


def test_reminders_and_the_link_go_out_once(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot, meetings={"link_minutes": 5})
    long_ago = datetime.utcnow() - timedelta(days=3)
    starting = _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, kind="online", status="confirmed", history=[],
                                 starts_at=datetime.utcnow() + timedelta(minutes=4), decided_at=long_ago))
    tomorrow = _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, kind="online", status="confirmed", history=[],
                                 starts_at=datetime.utcnow() + timedelta(hours=20), decided_at=long_ago))
    lapsed = _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, kind="online", status="requested", history=[],
                               starts_at=datetime.utcnow() - timedelta(minutes=1)))
    forgotten = _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, kind="online", status="confirmed", history=[],
                                  starts_at=datetime.utcnow() - timedelta(days=4)))
    sent, team = [], []

    async def to_person(meeting_id, what):
        sent.append((meeting_id, what))
    monkeypatch.setattr(meetings, "_to_person", to_person)

    async def notify(meeting_id, what):
        team.append((meeting_id, what))
    monkeypatch.setattr(meetings, "notify_team", notify)
    run(meetings.process_due)
    run(meetings.process_due)
    assert sorted(sent) == sorted([(starting.id, "link"), (tomorrow.id, "day_before")])
    assert (starting.id, "starting") in team
    assert _get(run, Meeting, lapsed.id).status == "expired" and _get(run, Meeting, forgotten.id).status == "done"


def test_the_confirmation_email_carries_a_calendar_invite(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    meeting = _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, name="Priya Raman", email="priya@example.com",
                                kind="online", status="confirmed", topic="Gold plan", history=[],
                                starts_at=datetime(2030, 1, 2, 5, 0)))
    emails = []

    async def send_email(to, subject, text, html_body=None, reply_to=None, from_name=None, unsubscribe_url=None, attachments=None):
        emails.append((to, subject, text, attachments))
        return True
    monkeypatch.setattr("notify.email.send_email", send_email)
    run(meetings.send_confirmation, meeting.id)
    run(meetings.send_confirmation, meeting.id)  # once only
    to_person = [e for e in emails if e[0] == "priya@example.com"]
    assert len(to_person) == 1
    _, subject, text, attachments = to_person[0]
    assert "Confirmed" in subject and "Hi Priya" in text and "joining link 5 minutes before" in text
    invite = attachments[0]["content"]
    assert "DTSTART:20300102T050000Z" in invite and "LOCATION:https://meet.example.com/desk" in invite
    assert _get(run, Meeting, meeting.id).sent["confirmed"]["via"] == ["email"]


# ─── after a call: ratings and follow-ups ─────────────────────────
def test_after_a_call_the_lead_is_rated_and_a_follow_up_planned_at_their_hour(run, make_user):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot, follow_ups={"rules": {"hot": {"count": 3, "every": 2}}})
    _add(run, _contact(u.id, bot))
    first = _add(run, _call(u.id, bot, lead="hot", next_step={"brief": "Ask whether they chose the Gold plan.", "reason": "Wants to join"},
                            started_at=_midday_yesterday()))
    run(schedule.after_call, first.id)
    contact = _contact_now(run, bot)
    assert (contact.lead_status, contact.lead_reason, contact.lead_set_by) == ("hot", "Wants to join", None)
    [job] = _jobs(run, bot, kind="follow_up")
    due = schedule.utc(job.next_attempt_at) - schedule.utc(first.started_at)
    assert job.status == "queued" and timedelta(days=2, minutes=-1) <= due <= timedelta(days=2, minutes=15)
    assert (job.purpose, job.from_number_id, job.source_call_id, job.variables) == (
        "Ask whether they chose the Gold plan.", "num-1", first.id, {"step": 0})
    assert "Follow-up after their call" in job.consent_source and "hot lead" in job.consent_source

    no = _add(run, _call(u.id, bot, lead="not_interested", next_step={"reason": "Joined elsewhere"}))
    run(schedule.after_call, no.id)
    assert _contact_now(run, bot).lead_status == "not_interested"
    assert [j.status for j in _jobs(run, bot, kind="follow_up")] == ["cancelled"]


def _contact_now(run, bot) -> Contact:
    async def go():
        async with async_session() as db:
            return await schedule.contact_of(db, bot, NUMBER)
    return run(go)


def test_what_a_call_leads_to_besides_follow_ups(run, make_user):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    _add(run, _contact(u.id, bot))
    soon = (datetime.now(IST) + timedelta(hours=3)).replace(second=0, microsecond=0)
    agreed = _add(run, _call(u.id, bot, lead="warm", next_step={"call_back_at": soon.strftime("%Y-%m-%d %H:%M")}))
    run(schedule.after_call, agreed.id)
    [callback] = _jobs(run, bot, kind="callback")
    assert callback.status == "queued" and schedule.utc(callback.next_attempt_at) == soon.astimezone(timezone.utc)
    assert not _jobs(run, bot, kind="follow_up")  # the call-back they agreed to comes first

    person = _add(run, _call(u.id, bot, caller_e164="+919800000010", lead="warm", next_step={"person": True}))
    _add(run, Contact(user_id=u.id, bot_id=bot, e164="+919800000010", calls=1, details={}, last_call_at=datetime.utcnow()))
    run(schedule.after_call, person.id)
    todo = [j for j in _jobs(run, bot, kind="person")]
    assert [(j.status, j.e164) for j in todo] == [("todo", "+919800000010")]

    test = _add(run, Contact(user_id=u.id, bot_id=bot, e164="+919800000011", calls=1, details={}, last_call_at=datetime.utcnow()),
                _call(u.id, bot, caller_e164="+919800000011", lead="hot", consent_source=f"{schedule.TEST_CALL} for x"))[1]
    run(schedule.after_call, test.id)
    assert [j.status for j in _jobs(run, bot, kind="follow_up", e164="+919800000011")] == ["review"]  # never dials by itself

    opted = _add(run, _call(u.id, bot, outcome="opted_out"))
    run(schedule.after_call, opted.id)
    assert _contact_now(run, bot).lead_status == "not_interested"
    assert [j.status for j in _jobs(run, bot, e164=NUMBER)] == ["cancelled"]


def test_the_assistant_doesnt_overrule_the_team_on_a_customer(run, make_user, client):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    contact = _add(run, _contact(u.id, bot))
    _add(run, _call(u.id, bot, lead="hot"))
    marked = client.patch(f"/api/voice/schedule/contacts/{contact.id}", json={"lead_status": "customer"}, headers=u.h())
    assert marked.json()["lead_status"] == "customer" and marked.json()["lead_set_by_team"]
    later = _add(run, _call(u.id, bot, lead="warm"))
    run(schedule.after_call, later.id)
    assert _contact_now(run, bot).lead_status == "customer" and not _jobs(run, bot, kind="follow_up")
    hot = client.patch(f"/api/voice/schedule/contacts/{contact.id}", json={"lead_status": "hot"}, headers=u.h())
    assert hot.json()["lead_status"] == "hot" and [j.status for j in _jobs(run, bot, kind="follow_up")] == ["queued"]
    client.patch(f"/api/voice/schedule/contacts/{contact.id}", json={"follow_ups_off": True}, headers=u.h())
    assert [j.status for j in _jobs(run, bot, kind="follow_up")] == ["cancelled"]


# ─── dialling ─────────────────────────────────────────────────────
def test_a_planned_follow_up_is_checked_again_before_dialling(run, make_user):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    number = _add(run, PhoneNumber(user_id=u.id, number="+1 484 328 5015", e164="+14843285015", status="active",
                                   provider="twilio", bot_id=bot))
    contact = _add(run, _contact(u.id, bot, lead_status="warm", last_call_at=datetime.utcnow() - timedelta(days=1)))
    job = _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="follow_up", status="queued", consent_source="t",
                                next_attempt_at=datetime.utcnow(), from_number_id="gone"))

    async def check(**changes):
        async with async_session() as db:
            c = await db.get(Contact, contact.id)
            for key, value in changes.items():
                setattr(c, key, value)
            await db.commit()
            return await schedule.dial_check(db, await db.get(CallbackJob, job.id))
    ok = run(check)
    assert ok.stop is None and ok.wait_until is None and ok.from_number_id == number.id and ok.attempts == 2
    assert run(check, last_chat_at=datetime.utcnow()).stop == ("cancelled", "They spoke with you after this was planned")
    old = datetime.utcnow() - timedelta(days=9)
    assert "More than 7 days" in run(check, last_chat_at=None, last_call_at=old).stop[1]
    assert run(check, last_call_at=datetime.utcnow() - timedelta(days=1), lead_status="customer").stop[1] == "They're now marked customer"
    run(check, lead_status="warm")
    _add(run, _call(u.id, bot, direction="outbound", started_at=datetime.utcnow()))  # spoke with them today already
    later = run(check)
    assert later.stop is None and schedule.utc(later.wait_until).astimezone(IST).date() > datetime.now(IST).date()
    _add(run, DncEntry(user_id=u.id, e164=NUMBER))
    assert run(check).stop == ("cancelled", "Number is on the do-not-call list")


def test_call_backs_wait_for_calling_hours_and_meeting_calls_for_a_meeting_that_still_needs_them(run, make_user):
    u = make_user()
    bot = u.bot()
    now = datetime.now(IST)
    closed = [(now + timedelta(hours=2)).strftime("%H:00"), (now + timedelta(hours=3)).strftime("%H:00")]
    if closed[0] >= closed[1]:
        pytest.skip("too close to midnight for this check")
    _save(run, u.id, bot, callbacks={"hours": closed})
    callback = _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="callback", status="queued",
                                     consent_source="t", next_attempt_at=datetime.utcnow()))
    meeting = _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, status="cancelled", history=[],
                                starts_at=datetime.utcnow() + timedelta(days=1)))
    stale = _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="meeting", status="queued", consent_source="t",
                                  next_attempt_at=datetime.utcnow(), meeting_id=meeting.id, variables={"about": "confirmed"}))

    async def check(job_id):
        async with async_session() as db:
            return await schedule.dial_check(db, await db.get(CallbackJob, job_id))
    waiting = run(check, callback.id)
    assert waiting.stop is None and schedule.utc(waiting.wait_until).astimezone(IST).strftime("%H:%M") == closed[0]
    assert run(check, stale.id).stop == ("cancelled", "The meeting changed since this call was planned")


def test_the_dialler_calls_back_from_the_number_they_called(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    monkeypatch.setattr(scheduler, "SCHEDULE_LINES", 1)
    placed, prepared = [], []

    async def fake_place(to, frm, job_id, **_):
        placed.append((to, frm, job_id))
        return f"CA-{len(placed)}"
    monkeypatch.setattr(twilio, "place_call", fake_place)

    async def prepare(job):
        prepared.append(job.id)
    monkeypatch.setattr(voice_router, "prepare_job_opening", prepare)
    theirs = _add(run, PhoneNumber(user_id=u.id, number="+1 484 328 5015", e164="+14843285015", status="active", provider="twilio"))
    _add(run, VoiceAgent(bot_id=bot, user_id=u.id, enabled=True, voice_id="priya"), _contact(u.id, bot, lead_status="hot"))
    first = _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="follow_up", status="queued", consent_source="t",
                                  next_attempt_at=datetime.utcnow() - timedelta(minutes=2), from_number_id=theirs.id))
    second = _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164="+919800000020", kind="callback", status="queued",
                                   consent_source="t", next_attempt_at=datetime.utcnow() - timedelta(minutes=1)))
    run(scheduler.dispatch_due_callbacks)
    # One line for this assistant: the call-back someone is waiting for goes first.
    assert placed == [("+919800000020", "+14843285015", second.id)]
    run(scheduler.dispatch_due_callbacks)
    assert len(placed) == 1  # the follow-up waits for the line
    done = _get(run, CallbackJob, second.id)
    assert (done.status, done.from_number_id, done.provider_call_id) == ("calling", theirs.id, "CA-1")

    async def free_line():
        async with async_session() as db:
            (await db.get(CallbackJob, second.id)).status = "done"
            await db.commit()
    run(free_line)
    run(scheduler.dispatch_due_callbacks)
    assert placed[-1] == (NUMBER, "+14843285015", first.id) and _contact_now(run, bot).follow_ups == 1


def test_unanswered_calls_retry_by_kind_and_follow_ups_move_on(run, make_user):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot, callbacks={"retry_minutes": 10})
    _add(run, _contact(u.id, bot, lead_status="hot"))
    callback = _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164="+919800000030", kind="callback", status="calling",
                                     attempts=1, consent_source="t"))
    follow = _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="follow_up", status="calling", attempts=2,
                                   consent_source="t", purpose="Ask about Gold.", variables={"step": 0}))

    async def miss(job_id):
        async with async_session() as db:
            job = await db.get(CallbackJob, job_id)
            await scheduler.retry_later(db, job, "Twilio: no-answer")
            await db.commit()
            return job
    retried = run(miss, callback.id)
    assert retried.status == "queued" and timedelta(minutes=9) < schedule.utc(retried.next_attempt_at) - datetime.now(timezone.utc) < timedelta(minutes=11)
    gave_up = run(miss, follow.id)
    assert gave_up.status == "failed"
    nxt = [j for j in _jobs(run, bot, kind="follow_up") if j.id != follow.id]
    assert [(j.status, j.variables["step"], j.purpose) for j in nxt] == [("queued", 1, "Ask about Gold.")]


# ─── what a Schedule call says ────────────────────────────────────
def test_a_schedule_call_opens_with_what_its_for_in_their_language(run, make_user):
    u = make_user()
    bot = u.bot()
    settings = _save(run, u.id, bot)
    agent = VoiceAgent(language="en-IN", follow_caller_language=True, assistant_name="Nimmi", company_name="Kd Academy")
    callback = CallbackJob(kind="callback", name="Priya Raman", purpose="plan prices", variables=None)
    plan = schedule.plan_for(callback, settings, None, agent, None, "Kd Academy")
    assert plan.greeting == "Hi Priya, calling you back as you asked. Is this a good time to talk?"
    assert "(about: plan prices)" in plan.purpose and plan.language is None
    tamil = schedule.plan_for(callback, settings, None, agent, {"first_name": "Priya", "language": "ta-IN"}, "Kd Academy")
    assert tamil.language == "ta-IN" and tamil.greeting.startswith("வணக்கம் Priya")
    meeting = Meeting(kind="online", status="confirmed", starts_at=schedule.stored(datetime.now(timezone.utc) + timedelta(days=1)))
    confirm = CallbackJob(kind="meeting", variables={"about": "confirmed"})
    plan = schedule.plan_for(confirm, {**settings, "_channels": {"whatsapp": None, "email": True}}, meeting, agent, None, "Kd Academy")
    assert plan.greeting.startswith("Hi, good news: your meeting with us tomorrow at")
    assert "joining link will be sent by email 5 minutes before" in plan.purpose
    gone = schedule.plan_for(confirm, settings, None, agent, None, "Kd Academy")
    assert gone.greeting is None and "Ask how you can help" in gone.purpose
    assert voice_router._job_variables(CallbackJob(kind="follow_up", name="Priya", variables={"step": 2})) == {"name": "Priya"}
    assert voice_router._job_variables(CallbackJob(name="Ravi", variables={"course": "MBA"})) == {"course": "MBA", "name": "Ravi"}


def test_a_schedule_call_is_routed_with_its_purpose_tools_and_number(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    _add(run, VoiceAgent(bot_id=bot, user_id=u.id, enabled=True, voice_id="priya", language="en-IN",
                         assistant_name="Nimmi", company_name="Kd Academy", greeting="How can I help?"))
    job = _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="callback", name="Priya", status="calling",
                                purpose="plan prices", consent_source="Asked on a call", from_number_id="num-9"))
    seen = []

    class Session:
        def __init__(self, setup, transport):
            seen.append(setup)

        async def run(self):
            return None
    monkeypatch.setattr(voice_router, "CallSession", Session)

    class Transport:
        async def hangup(self, reason):
            seen.append(reason)
    run(voice_router._route_and_run, Transport(), "CA-77", None, None, job_id=job.id)
    [setup] = seen
    assert "asked you to call them back (about: plan prices)" in setup.purpose
    assert setup.agent.greeting == "Hi Priya, calling you back as you asked. Is this a good time to talk?"
    assert setup.number_id == "num-9" and setup.tools is not None and "schedule_callback" in setup.tools.names()
    assert setup.variables == {"name": "Priya"} and setup.callback_job_id == job.id


def test_the_analysis_reads_the_lead_and_what_should_come_next(run, monkeypatch):
    prompts = []

    async def complete(bot, system, user, max_tokens=600, urgent=False):
        prompts.append(system)
        return ('{"summary": "Wants the Gold plan.", "fields": {}, "successful": true, "sentiment": "positive", '
                '"wants_callback": false, "lead": "Hot", "lead_reason": "Ready to join", '
                '"follow_up": "Send the fee details and ask about a start date.", "follow_up_on": "2026-11-03", '
                '"call_back_at": "2026-10-30T11:00"}')
    monkeypatch.setattr(llm, "_complete", complete)
    transcript = [{"speaker": "caller", "text": "I want to join."}, {"speaker": "agent", "text": "Great."}]
    result = run(llm.summarize, llm.Bot(bot_name="Desk"), transcript, None)
    assert (result["lead"], result["lead_reason"], result["follow_up_on"], result["call_back_at"]) == (
        "hot", "Ready to join", "2026-11-03", "2026-10-30 11:00")
    assert result["follow_up"].startswith("Send the fee details") and "The call ended on" in prompts[0]

    async def odd(bot, system, user, max_tokens=600, urgent=False):
        return '{"summary": "x", "lead": "lukewarm", "follow_up_on": "soon", "call_back_at": "later"}'
    monkeypatch.setattr(llm, "_complete", odd)
    result = run(llm.summarize, llm.Bot(bot_name="Desk"), transcript, None)
    assert (result["lead"], result["follow_up_on"], result["call_back_at"]) == (None, None, None)


# ─── the dashboard's API ──────────────────────────────────────────
def test_schedule_settings_overview_and_actions(client, make_user, run):
    u, other = make_user(), make_user()
    bot = u.bot()
    shown = client.get(f"/api/voice/schedule/settings/{bot}", headers=u.h()).json()
    assert not shown["settings"]["callbacks"]["enabled"] and shown["numbers"] == []
    bad = client.put(f"/api/voice/schedule/settings/{bot}", json={"meetings": {"link": "meet.example.com"}}, headers=u.h())
    assert bad.status_code == 400
    saved = client.put(f"/api/voice/schedule/settings/{bot}", json=_raw(), headers=u.h()).json()
    assert saved["settings"]["meetings"]["link"] == "https://meet.example.com/desk"
    assert client.get(f"/api/voice/schedule/settings/{bot}", headers=other.h()).status_code == 404

    contact = _add(run, _contact(u.id, bot, lead_status="warm"))
    review, todo = _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="follow_up", status="review",
                                         consent_source="t", next_attempt_at=datetime.utcnow() + timedelta(hours=5)),
                        CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="person", status="todo",
                                    consent_source="t", purpose="Wants a person", next_attempt_at=datetime.utcnow()))
    _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, status="requested", history=[],
                      starts_at=datetime.utcnow() + timedelta(days=1)))
    attention = client.get("/api/voice/schedule/attention", headers=u.h()).json()
    assert (attention["approve"], attention["review"], attention["people"], attention["total"]) == (1, 1, 1, 3)
    overview = client.get("/api/voice/schedule/overview", headers=u.h()).json()
    assert [c["id"] for c in overview["calls"]] == [review.id] and [p["id"] for p in overview["people"]] == [todo.id]
    assert overview["stats"]["leads"] == {"warm": 1} and len(overview["meetings"]) == 1

    assert client.post(f"/api/voice/schedule/items/{review.id}/approve", headers=other.h()).status_code == 404
    assert client.post(f"/api/voice/schedule/items/{review.id}/approve", headers=u.h()).json()["status"] == "queued"
    now = client.post(f"/api/voice/schedule/items/{review.id}/now", headers=u.h()).json()
    assert schedule.utc(datetime.fromisoformat(now["due_at"])) <= datetime.now(timezone.utc)
    assert client.post(f"/api/voice/schedule/items/{todo.id}/done", headers=u.h()).json()["status"] == "done"
    assert client.post(f"/api/voice/schedule/items/{review.id}/cancel", headers=u.h()).json()["status"] == "cancelled"

    day = (datetime.now(IST) + timedelta(days=1)).date().isoformat()
    made = client.post("/api/voice/schedule/items", json={"contact_id": contact.id, "date": day, "time": "11:00",
                                                           "about": "Share the new batch dates"}, headers=u.h())
    assert made.status_code == 200 and made.json()["from"] == "team" and made.json()["purpose"] == "Share the new batch dates"
    past = client.post("/api/voice/schedule/items", json={"contact_id": contact.id, "date": "2020-01-01", "time": "11:00"},
                       headers=u.h())
    assert past.status_code == 400
    free = client.get(f"/api/voice/schedule/free-times?bot_id={bot}", headers=u.h()).json()
    assert free and all(t["times"][0] >= "10:00" for t in free)
    hosts = client.get("/api/voice/schedule/hosts", headers=u.h()).json()
    assert hosts[0]["id"] == u.id


def test_erasing_a_caller_removes_their_meetings(client, make_user, run):
    u = make_user()
    bot = u.bot()
    meeting = _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, status="confirmed", history=[],
                                starts_at=datetime.utcnow() + timedelta(days=1)))
    assert client.post("/api/voice/erase", json={"number": NUMBER}, headers=u.h()).status_code == 200
    assert _get(run, Meeting, meeting.id) is None


def test_call_me_back_on_a_day_books_a_call_back_that_day(run, make_user):
    """'Call me back next Monday' with no time: a call-back that day about the hour they called (they asked for it, so it
    happens even with follow-ups off)."""
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot, follow_ups={"enabled": False})
    _add(run, _contact(u.id, bot))
    day = datetime.now(IST).date() + timedelta(days=4)
    call = _add(run, _call(u.id, bot, lead="warm", next_step={"on": day.isoformat(), "brief": "Ask what they decided."},
                           started_at=_midday_yesterday()))
    run(schedule.after_call, call.id)
    [job] = _jobs(run, bot, kind="callback")
    due = schedule.utc(job.next_attempt_at).astimezone(IST)
    assert job.status == "queued" and due.date() == day and job.purpose == "Ask what they decided."
    called = schedule.utc(call.started_at).astimezone(IST)
    assert timedelta(0) <= due - due.replace(hour=called.hour, minute=called.minute) <= timedelta(minutes=15)


def test_a_meeting_the_agent_agreed_to_but_didnt_book_is_requested_after_the_call(run, make_user, monkeypatch):
    """GPT-OSS 120B said "we have you booked for today at 3 pm" without booking it (a simulated call, Oct 2026)."""
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    told = []

    async def notify(meeting_id, what):
        told.append((meeting_id, what))
    monkeypatch.setattr(meetings, "notify_team", notify)
    _add(run, _contact(u.id, bot, email="priya@example.com"),
         CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="follow_up", status="queued", consent_source="t",
                     next_attempt_at=datetime.utcnow() + timedelta(days=1)))
    day = datetime.now(IST).date() + timedelta(days=2)
    call = _add(run, _call(u.id, bot, lead="hot", next_step={"meeting_at": f"{day.isoformat()} 10:30", "meeting_kind": "online",
                                                              "meeting_about": "MBA fees"}))
    run(schedule.after_call, call.id)

    async def made():
        async with async_session() as db:
            return (await db.execute(select(Meeting).where(Meeting.source_call_id == call.id))).scalars().all()
    [meeting] = run(made)
    assert (meeting.status, meeting.kind, meeting.topic, meeting.name, meeting.email) == (
        "requested", "online", "MBA fees", "Priya Raman", "priya@example.com")
    assert schedule.utc(meeting.starts_at).astimezone(IST).strftime("%H:%M") == "10:30" and "didn't book it" in meeting.history[0]["what"]
    assert told == [(meeting.id, "requested")]
    assert [j.status for j in _jobs(run, bot, kind="follow_up")] == ["cancelled"]  # a meeting is coming: no follow-up
    run(schedule.after_call, call.id)  # the same call again: nothing more
    assert len(run(made)) == 1


# ─── calls not made yet ───────────────────────────────────────────
def _missed_confirmation(run, u, bot, status="queued"):
    """Live, 30 Oct 2026: a confirmed meeting's call found the line busy two minutes ago; another try in half an hour."""
    day = datetime.now(IST).date() + timedelta(days=1)
    meeting = _add(run, Meeting(user_id=u.id, bot_id=bot, e164=NUMBER, name="Peter", kind="online", status="confirmed",
                                starts_at=schedule.stored(_local(day, "10:30")), minutes=30))
    job = _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164=NUMBER, kind="meeting", status=status,
                                variables={"about": "confirmed"}, meeting_id=meeting.id, attempts=1, provider_call_id="CA_busy",
                                last_error="twilio: busy", consent_source="Asked for a meeting on a call",
                                next_attempt_at=datetime.utcnow() + timedelta(minutes=30)))
    _add(run, _call(u.id, bot, direction="outbound", outcome="no_answer", provider_call_id="CA_busy",
                    summary="Call busy. Attempt 1.", started_at=datetime.utcnow() - timedelta(minutes=2)))
    return meeting, job


def _returning_the_call(run, u, bot, monkeypatch, handled: str):
    """They ring back and say a call came from this number. The agent answers from what it was told (the real
    analysis runs, on a model that says `handled`); returns what was said, the analysis prompt and the call."""
    from tests.test_live_calls import hangs_up_after
    from tests.test_pipeline import Ev, FakeStt, FakeTransport, _setup, fake_tts
    from voice.pipeline import CallSession
    prompts = []

    async def complete(bot_, system, user, max_tokens=600, urgent=False):
        prompts.append(system)
        return ('{"summary": "Peter returned a missed call and heard his meeting is confirmed.", "fields": {}, '
                f'"lead": "warm", "handled": {handled}}}')
    monkeypatch.setattr(llm, "_complete", complete)

    async def agent_says(bot_, agent, history, text, direction, consent, schedule_tools=None, **_):
        rules = schedule_tools.rules() if schedule_tools is not None else ""
        told = "didn't reach them" in rules and "is confirmed" in rules and "the line was busy" in rules
        yield ("We called to tell you your meeting tomorrow at 10:30 am is confirmed." if told else
               "How can I help you today?"), None

    async def scenario():
        setup = await _setup(u.id, bot)
        setup.tools = await schedule.tools_for(u.id, bot, NUMBER, "num-1")
        t = FakeTransport()
        session = CallSession(setup, t, stt_factory=lambda *a: FakeStt([Ev("transcript", "A call came from this number.")]),
                              tts=fake_tts, replier=agent_says, summarizer=llm.summarize)

        async def feed():
            await asyncio.sleep(0.05)
            for _ in range(3):
                await t.inbox.put(b"\x00\x00" * 160)
                await asyncio.sleep(0.05)
        tasks = [asyncio.create_task(feed()), asyncio.create_task(hangs_up_after("How can I help you today?")(session)),
                 asyncio.create_task(hangs_up_after("is confirmed")(session))]
        try:
            call_id = await asyncio.wait_for(session.run(), timeout=20)
        finally:
            for task in tasks:
                task.cancel()
        await asyncio.sleep(0.5)  # what follows the call is planned in the background
        async with async_session() as db:
            return t.said(), await db.get(CallLog, call_id)
    said, log = run(scenario)
    return said, prompts, log


def test_someone_returning_a_missed_call_hears_why_and_the_call_isnt_made_again(run, make_user, monkeypatch):
    """Live, 30 Oct 2026 (GBOT): the meeting's confirmation call found the line busy; the person rang straight back and
    said four times that a call had come from this number, and the agent, never told about it, kept asking how it could
    help, then booked a call-back when they said "I called back". Half an hour later the retry rang to tell them again."""
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    meeting, job = _missed_confirmation(run, u, bot)
    said, prompts, log = _returning_the_call(run, u, bot, monkeypatch, '["call_1", "call_7"]')
    assert "We called to tell you your meeting tomorrow at 10:30 am is confirmed." in said
    assert "- call_1: to tell them their online meeting" in prompts[0] and '"handled"' in prompts[0]
    assert log.next_step["handled"] == [job.id]  # an id the analysis made up is left out
    done = _get(run, CallbackJob, job.id)
    assert (done.status, done.call_id) == ("done", log.id) and done.last_error.startswith("Taken care of on their call on")


def test_a_missed_call_the_conversation_didnt_cover_is_still_made(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    meeting, job = _missed_confirmation(run, u, bot)
    said, prompts, log = _returning_the_call(run, u, bot, monkeypatch, "[]")
    assert not (log.next_step or {}).get("handled")
    kept = _get(run, CallbackJob, job.id)
    assert (kept.status, kept.attempts) == ("queued", 1)


def test_what_a_call_is_told_about_calls_tried_or_due(run, make_user):
    u = make_user()
    bot = u.bot()
    _save(run, u.id, bot)
    meeting, job = _missed_confirmation(run, u, bot)

    async def tools(**kw):
        return await schedule.tools_for(u.id, bot, NUMBER, "num-1", **kw)
    rules = run(tools).rules()
    assert "Calls you made to this caller that didn't reach them" in rules
    assert "(the line was busy): to tell them their online meeting with" in rules and "tomorrow at 10:30 am is confirmed" in rules
    assert "Another try is planned today at" in rules or "Another try is planned tomorrow at" in rules
    assert "Returning your call is not asking to be called back." in rules
    assert run(tools, skip=job.id).open == []  # the call being made now isn't one they're returning

    # "I called back" isn't a call-back request: the first one asked for while they may be returning a call goes back to
    # the agent (tell them what the call was about); asked for again, it's booked.
    returning = run(tools)

    async def book(about):
        return await returning.run("schedule_callback", {"when": "in 30 minutes", "about": about})
    assert run(book, "call back").startswith("Wait: they may be returning the call you made.")
    assert run(book, "MBA fees").startswith("Booked:")
    assert [j.purpose for j in _jobs(run, bot, kind="callback")] == ["MBA fees"]

    # A missed campaign call is explained too, with every Schedule switch off (no functions, only what it was for).
    other = "+919800000077"
    campaign = _add(run, Campaign(user_id=u.id, bot_id=bot, name="Diwali offer", purpose="Tell {{name}} about 20% off the Gold plan"))
    _add(run, CallbackJob(user_id=u.id, bot_id=bot, e164=other, campaign_id=campaign.id, status="failed", attempts=2,
                          provider_call_id="CA_nobody", last_error="twilio: no-answer", consent_source="Campaign",
                          variables={"name": "Ravi"}),
         _call(u.id, bot, caller_e164=other, direction="outbound", outcome="no_answer", provider_call_id="CA_nobody",
               started_at=datetime.utcnow() - timedelta(hours=3)))
    _save(run, u.id, bot, callbacks={"enabled": False}, follow_ups={"enabled": False}, meetings={"enabled": False})

    async def campaign_tools():
        return await schedule.tools_for(u.id, bot, other, "num-1")
    quiet = run(campaign_tools)
    assert quiet.specs() == [] and "(no answer): the Diwali offer campaign: Tell Ravi about 20% off the Gold plan." in quiet.rules()
    assert "Another try" not in quiet.rules()  # it gave up


def test_the_analysis_names_only_the_calls_it_was_given(run, monkeypatch):
    prompts = []

    async def complete(bot, system, user, max_tokens=600, urgent=False):
        prompts.append(system)
        return '{"summary": "x", "handled": "call_2"}'
    monkeypatch.setattr(llm, "_complete", complete)
    transcript = [{"speaker": "caller", "text": "You called me?"}, {"speaker": "agent", "text": "Yes, about your meeting."}]
    given = [{"id": "call_1", "about": "the call back they asked for"}, {"id": "call_2", "about": "to tell them it's confirmed"}]
    assert run(llm.summarize, llm.Bot(bot_name="Desk"), transcript, None, "Asia/Kolkata", given)["handled"] == ["call_2"]
    assert "- call_2: to tell them it's confirmed" in prompts[0]
    assert run(llm.summarize, llm.Bot(bot_name="Desk"), transcript, None)["handled"] == []
    assert '"handled"' not in prompts[1] and "HANDLED" not in prompts[1] and 'never "today" or "tomorrow"' in prompts[1]
