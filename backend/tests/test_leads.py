"""
The Leads section (instagram_plan.md, phase 1): one person is one lead however often they ask; a task finishes once; an agent reaches only their own
leads; turns hand each lead out once; what was won or lost stays; first steps nobody took move to the backup, once; and Erase leaves nothing behind.
"""
import asyncio
import csv
import io
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func
from sqlalchemy.future import select

from backend.models import CallbackJob, CallLog, Contact, Conversation, EmailJob, LeadDeal, LeadEvent, LeadIntake, LeadSettings, LeadSource, LeadTask, Meeting
from database import async_session
from leads import core


@pytest.fixture
def owner(make_user):
    user = make_user("Owner")
    user.desk = user.bot("Desk")
    return user


@pytest.fixture
def joined(client, make_user):
    """Someone on the owner's team."""
    def join(owner, role="agent", name="Seller"):
        member = make_user(name)
        invited = client.post("/api/team/invite", json={"email": member.email, "role": role}, headers=owner.h()).json()
        token = invited["invite_link_path"].split("token=")[1]
        assert client.post("/api/team/accept", json={"token": token}, headers=member.h()).status_code == 200
        return member
    return join


@pytest.fixture
def alerts(monkeypatch):
    sent = []

    async def alert(owner_id, person, subject, text, bot_id=None, contact_id=None):
        sent.append((owner_id, person, subject))
    monkeypatch.setattr(core, "_alert", alert)
    monkeypatch.setattr(core, "_last_pass", None)
    return sent


def number():
    return f"+9198{uuid.uuid4().int % 100_000_000:08d}"


def leave(client, owner, member):
    found = next(m for m in client.get("/api/team/members", headers=owner.h()).json() if m["email"] == member.email)
    assert client.delete(f"/api/team/members/{found['id']}", headers=owner.h()).status_code == 200


async def _contact(user, **values) -> str:
    async with async_session() as db:
        c = Contact(user_id=user.id, bot_id=user.desk, **{"e164": number(), "details": {}, "calls": 0, **values})
        db.add(c)
        await db.commit()
        return c.id


async def _rows(model, contact_id):
    async with async_session() as db:
        return (await db.execute(select(model).where(model.contact_id == contact_id))).scalars().all()


async def _get(model, key):
    async with async_session() as db:
        return await db.get(model, key)


def test_one_person_is_one_lead_however_often_they_ask(client, owner, run):
    code = uuid.uuid4().hex[:16]

    async def source():
        async with async_session() as db:
            db.add(LeadSource(bot_id=owner.desk, user_id=owner.id, code=code, enabled=True))
            await db.commit()
    run(source)
    for ask in ("2BHK in Anna Nagar", "A 3BHK this time", "Is parking included?"):
        assert client.post(f"/api/leads/in/{code}/form", json={"name": "Ravi Kumar", "phone": "98765 00051", "message": ask}).status_code == 200

    async def wait():
        for _ in range(100):
            async with async_session() as db:
                intakes = (await db.execute(select(LeadIntake).where(LeadIntake.bot_id == owner.desk))).scalars().all()
                events = (await db.execute(select(LeadEvent).where(LeadEvent.bot_id == owner.desk))).scalars().all()
            if len(intakes) == 3 and len(events) == 3:
                return intakes, events
            await asyncio.sleep(0.05)
        return intakes, events
    intakes, events = run(wait)
    assert len(intakes) == 3
    found = client.get("/api/crm/leads", headers=owner.h()).json()
    assert found["total"] == 1
    lead = client.get(f"/api/crm/leads/{found['items'][0]['id']}", headers=owner.h()).json()
    assert sum(1 for t in lead["timeline"] if t["kind"] == "submission") == 3   # every submission stays
    assert sorted(e.kind for e in events) == ["asked_again", "asked_again", "came_in"]
    assert len(lead["tasks"]) == 1                                              # and one thing to do


def test_the_same_submission_arriving_twice_counts_once(owner, run):
    lead = run(_contact, owner)
    run(core.came_in, owner.id, lead, "IndiaMART", "ref-1", "Bottles")
    run(core.came_in, owner.id, lead, "IndiaMART", "ref-1", "Bottles")
    assert [e.kind for e in run(_rows, LeadEvent, lead)] == ["came_in"]
    assert len(run(_rows, LeadTask, lead)) == 1


def test_leads_with_only_an_email_or_only_a_number(client, owner, run):
    h = owner.h()
    by_mail = client.post("/api/crm/leads", json={"bot_id": owner.desk, "email": "only.mail@buyers.in", "name": "Mala"}, headers=h).json()["id"]
    by_phone = client.post("/api/crm/leads", json={"bot_id": owner.desk, "phone": "98765 00061"}, headers=h).json()["id"]
    mail, phone = client.get(f"/api/crm/leads/{by_mail}", headers=h).json(), client.get(f"/api/crm/leads/{by_phone}", headers=h).json()
    assert mail["phone"] is None and mail["tasks"][0]["kind"] == "email" and mail["tasks"][0]["title"] == "Email Mala"
    assert phone["email"] is None and phone["tasks"][0]["kind"] == "call"
    # The same person again is the same lead, and anything else isn't a lead.
    assert client.post("/api/crm/leads", json={"bot_id": owner.desk, "email": "only.mail@buyers.in"}, headers=h).status_code == 409
    assert client.post("/api/crm/leads", json={"bot_id": owner.desk, "name": "Nobody"}, headers=h).status_code == 400
    assert client.post("/api/crm/leads", json={"bot_id": owner.desk, "phone": "12"}, headers=h).status_code == 400


async def _call(user, e164, **values):
    async with async_session() as db:
        call = CallLog(user_id=user.id, bot_id=user.desk, caller_e164=e164, **{"direction": "inbound", "outcome": "answered", "transcript": [{"speaker": "caller", "text": "What's the price?"}], **values})
        db.add(call)
        await db.commit()
        return call.id


def test_someone_who_rang_is_a_lead_the_assistant_has_answered(client, owner, run):
    e164 = number()
    lead = run(_contact, owner, e164=e164, name="Caller")
    run(core.after_call, run(_call, owner, e164))
    page = client.get(f"/api/crm/leads/{lead}", headers=owner.h()).json()
    assert page["enquiry_days_left"] == 7 and page["tasks"] == []                # the assistant has answered them: a person isn't owed a call yet
    assert run(_get, Contact, lead).first_response_at is not None
    assert [e.text for e in run(_rows, LeadEvent, lead)] == ["Phone call"]
    assert "Caller" in [x["name"] for x in client.get("/api/crm/queues", headers=owner.h()).json()["new"]]


@pytest.mark.parametrize("call", [
    {"direction": "outbound"}, {"outcome": "voicemail"}, {"outcome": "opted_out"}, {"outcome": "failed"}, {"channel": "browser"},
    {"transcript": [{"speaker": "agent", "text": "Hello?"}]}, {"transcript": [{"speaker": "caller", "text": "  "}]}])
def test_only_a_conversation_someone_started_is_an_enquiry(client, owner, run, call):
    e164 = number()
    lead = run(_contact, owner, e164=e164)
    run(core.after_call, run(_call, owner, e164, **call))
    assert run(_rows, LeadEvent, lead) == []
    assert run(_get, Contact, lead).last_enquiry_at is None


def test_a_call_from_someone_with_no_contact_makes_nothing(client, owner, run):
    run(core.after_call, run(_call, owner, number()))                            # Remember callers off
    assert client.get("/api/crm/leads", headers=owner.h()).json()["total"] == 0


def test_a_chat_that_gets_a_number_is_a_lead_with_a_first_step(client, owner, run):
    client.post("/api/chat/variables", json={"bot_id": owner.desk, "visitor_session_id": "lead-chat", "variable_name": "phone", "variable_value": "98765 00081"})
    client.post("/api/chat/variables", json={"bot_id": owner.desk, "visitor_session_id": "lead-chat", "variable_name": "name", "variable_value": "Chat Person"})

    async def wait():
        for _ in range(100):
            async with async_session() as db:
                found = (await db.execute(select(LeadEvent).where(LeadEvent.bot_id == owner.desk))).scalars().all()
            if found:
                return found
            await asyncio.sleep(0.05)
        return []
    assert [e.text for e in run(wait)] == ["Website chat"]
    lead = client.get("/api/crm/leads", headers=owner.h()).json()["items"][0]
    assert lead["next"]["kind"] == "call" and lead["source"] == "chat"


def test_a_waiting_call_or_meeting_is_a_next_step(client, owner, run):
    called, met, neither = number(), number(), number()
    for e164, name in ((called, "Called"), (met, "Met"), (neither, "Neither")):
        run(_contact, owner, e164=e164, name=name, assigned_to=owner.id)

    async def plan():
        async with async_session() as db:
            db.add(CallbackJob(user_id=owner.id, bot_id=owner.desk, e164=called, name="Called", status="queued", consent_source="test", next_attempt_at=datetime.utcnow() + timedelta(hours=2)))
            db.add(Meeting(user_id=owner.id, bot_id=owner.desk, e164=met, name="Met", topic="Visit", starts_at=datetime.utcnow() + timedelta(days=3), status="confirmed"))
            await db.commit()
    run(plan)
    assert [x["name"] for x in client.get("/api/crm/queues", headers=owner.h()).json()["no_next"]] == ["Neither"]


def test_a_task_finishes_once(client, owner, run):
    lead = run(_contact, owner)
    at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    task = client.post(f"/api/crm/leads/{lead}/tasks", json={"title": "Send the brochure", "due_at": at, "kind": "whatsapp"}, headers=owner.h()).json()

    async def both():
        async def press():
            async with async_session() as db:
                done = await core.finish_task(db, task["id"], owner.id, "Sent")
                await db.commit()
                return done
        return await asyncio.gather(press(), press(), press())
    assert sorted(run(both)) == [False, False, True]
    assert client.put(f"/api/crm/tasks/{task['id']}", json={"status": "done"}, headers=owner.h()).status_code == 409
    assert client.put(f"/api/crm/tasks/{task['id']}", json={"title": "Rewritten"}, headers=owner.h()).status_code == 409


def test_an_agent_reaches_only_their_own_leads(client, owner, joined, run):
    seller, other = joined(owner), joined(owner, name="Other seller")
    theirs = run(_contact, owner, assigned_to=seller.id, name="Mine")
    not_theirs = run(_contact, owner, assigned_to=other.id, name="Not mine")
    nobodys = run(_contact, owner, name="Nobody's")
    h = seller.h(owner.id)
    at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    task = client.post(f"/api/crm/leads/{not_theirs}/tasks", json={"title": "Their task", "due_at": at}, headers=owner.h()).json()

    assert [x["id"] for x in client.get("/api/crm/leads", headers=h).json()["items"]] == [theirs]
    assert client.get(f"/api/crm/leads/{theirs}", headers=h).status_code == 200
    for lead in (not_theirs, nobodys):
        assert client.get(f"/api/crm/leads/{lead}", headers=h).status_code == 404
        assert client.put(f"/api/crm/leads/{lead}", json={"notes": "x"}, headers=h).status_code == 404
        assert client.post(f"/api/crm/leads/{lead}/notes", json={"text": "x"}, headers=h).status_code == 404
        assert client.post(f"/api/crm/leads/{lead}/tasks", json={"title": "x", "due_at": at}, headers=h).status_code == 404
        assert client.post(f"/api/crm/leads/{lead}/result", json={"result": "reached"}, headers=h).status_code == 404
        assert client.post(f"/api/crm/leads/{lead}/close", json={"outcome": "won"}, headers=h).status_code == 404
        assert client.post(f"/api/crm/leads/{lead}/reopen", headers=h).status_code == 404
    assert client.put(f"/api/crm/tasks/{task['id']}", json={"status": "done"}, headers=h).status_code == 404
    # What's kept for managers.
    assert client.put(f"/api/crm/leads/{theirs}", json={"assigned_to": other.id}, headers=h).status_code == 403
    assert client.get("/api/crm/leads/export", headers=h).status_code == 403
    assert client.get(f"/api/crm/settings/{owner.desk}", headers=h).status_code == 403
    assert client.post("/api/crm/leads", json={"bot_id": owner.desk, "phone": "98765 00071"}, headers=h).status_code == 403
    # Their own lead is theirs to work, and a task they add is theirs, whoever they name.
    mine = client.post(f"/api/crm/leads/{theirs}/tasks", json={"title": "Call back", "due_at": at, "assigned_to": other.id}, headers=h).json()
    assert mine["assigned_to"] == seller.id
    async def waiting():
        async with async_session() as db:
            db.add(CallbackJob(user_id=owner.id, bot_id=owner.desk, e164=number(), name="Wants a person", kind="person", status="todo", consent_source="test"))
            db.add(Meeting(user_id=owner.id, bot_id=owner.desk, e164=number(), name="Wants a meeting", topic="Demo", starts_at=datetime.utcnow() + timedelta(days=1), status="requested"))
            await db.commit()
    run(waiting)
    queues = client.get("/api/crm/queues", headers=h).json()
    assert {x["id"] for q in ("overdue", "today", "new", "no_next") for x in queues[q]} == {theirs}
    assert queues["asked_for_person"] == [] and queues["meetings"] == []           # the team's to-dos and approvals are for managers
    assert client.get("/api/crm/reports", headers=h).json()["leads"] == 1
    # Someone who left can't keep working a lead.
    other_h = other.h(owner.id)
    assert client.get(f"/api/crm/leads/{not_theirs}", headers=other_h).status_code == 200
    leave(client, owner, other)
    assert client.get(f"/api/crm/leads/{not_theirs}", headers=other_h).status_code in (403, 404)


def test_a_manager_on_the_team_reaches_every_lead(client, owner, joined, run):
    admin = joined(owner, "admin", "Admin")
    lead = run(_contact, owner, name="Anyone's")
    assert client.get(f"/api/crm/leads/{lead}", headers=admin.h(owner.id)).status_code == 200
    assert client.get("/api/crm/leads/export", headers=admin.h(owner.id)).status_code == 200


def test_turns_hand_out_each_lead_once(client, owner, joined, run):
    a, b = joined(owner), joined(owner, name="B")
    assert client.put(f"/api/crm/settings/{owner.desk}", json={"assign": "turns", "people": [a.id, b.id], "respond_minutes": 15}, headers=owner.h()).status_code == 200
    leads = [run(_contact, owner) for _ in range(8)]

    async def together():
        await asyncio.gather(*(core.came_in(owner.id, lead, "Form", lead) for lead in leads))
    run(together)

    async def owners():
        async with async_session() as db:
            return (await db.execute(select(Contact.assigned_to).where(Contact.id.in_(leads)))).scalars().all()
    given = run(owners)
    assert given.count(a.id) == 4 and given.count(b.id) == 4
    task = run(_rows, LeadTask, leads[0])[0]
    assert task.assigned_to in (a.id, b.id) and task.origin == "rule"
    told = sorted(run(_rows, LeadEvent, leads[0]), key=lambda e: e.at)
    assert [e.kind for e in told] == ["came_in", "assigned"]                                   # their story in the order it happened


def test_someone_who_left_the_team_gets_no_more_leads(client, owner, joined, run):
    a, b = joined(owner), joined(owner, name="B")
    assert client.put(f"/api/crm/settings/{owner.desk}", json={"assign": "turns", "people": [a.id, b.id]}, headers=owner.h()).status_code == 200
    held = run(_contact, owner, assigned_to=b.id)
    at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    task = client.post(f"/api/crm/leads/{held}/tasks", json={"title": "Theirs", "due_at": at}, headers=owner.h()).json()
    leave(client, owner, b)
    leads = [run(_contact, owner) for _ in range(3)]
    for lead in leads:
        run(core.came_in, owner.id, lead, "Form", lead)
    assert {run(_get, Contact, lead).assigned_to for lead in leads} == {a.id}
    # What they were looking after waits for a manager.
    assert run(_get, Contact, held).assigned_to is None and run(_get, LeadTask, task["id"]).assigned_to is None


def test_a_lead_goes_only_to_someone_on_the_team(client, owner, make_user, run):
    lead = run(_contact, owner)
    stranger = make_user("Stranger")
    assert client.put(f"/api/crm/leads/{lead}", json={"assigned_to": stranger.id}, headers=owner.h()).status_code == 400
    at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    assert client.post(f"/api/crm/leads/{lead}/tasks", json={"title": "x", "due_at": at, "assigned_to": stranger.id}, headers=owner.h()).status_code == 400
    assert client.put(f"/api/crm/leads/{lead}", json={"assigned_to": owner.id}, headers=owner.h()).status_code == 200
    assert client.put(f"/api/crm/leads/{lead}", json={"assigned_to": ""}, headers=owner.h()).status_code == 200
    assert run(_get, Contact, lead).assigned_to is None


def test_the_rules_are_checked(client, owner, joined):
    h = owner.h()
    stranger = uuid.uuid4().hex
    url = f"/api/crm/settings/{owner.desk}"
    assert client.put(url, json={"assign": "turns", "people": []}, headers=h).status_code == 400
    assert client.put(url, json={"assign": "one", "people": [stranger]}, headers=h).status_code == 400
    assert client.put(url, json={"assign": "off", "backup": stranger}, headers=h).status_code == 400
    assert client.put(url, json={"assign": "maybe"}, headers=h).status_code == 400
    assert client.get(url, headers=h).json()["settings"]["assign"] == "off"


def test_a_lead_someone_looks_after_stays_with_them(client, owner, joined, run):
    a, b = joined(owner), joined(owner, name="B")
    client.put(f"/api/crm/settings/{owner.desk}", json={"assign": "one", "people": [b.id]}, headers=owner.h())
    lead = run(_contact, owner, assigned_to=a.id)
    run(core.came_in, owner.id, lead, "Form", "again")
    assert run(_get, Contact, lead).assigned_to == a.id


def test_closing_and_reopening_keeps_the_evidence(client, owner, run):
    lead = run(_contact, owner, source="IndiaMART")
    run(core.came_in, owner.id, lead, "IndiaMART", "r1")
    h = owner.h()
    assert client.post(f"/api/crm/leads/{lead}/close", json={"outcome": "lost"}, headers=h).status_code == 400     # lost needs a reason
    assert client.put(f"/api/crm/leads/{lead}", json={"stage": "customer"}, headers=h).status_code == 400            # and Won is how a sale is recorded
    assert client.post(f"/api/crm/leads/{lead}/close", json={"outcome": "won", "amount": 45000}, headers=h).status_code == 200
    assert client.post(f"/api/crm/leads/{lead}/close", json={"outcome": "won", "amount": 45000}, headers=h).status_code == 409
    closed = client.get(f"/api/crm/leads/{lead}", headers=h).json()
    assert closed["stage"] == "customer" and closed["status"] == "customer" and closed["tasks"] == []
    assert client.post(f"/api/crm/leads/{lead}/reopen", headers=h).status_code == 200
    again = client.get(f"/api/crm/leads/{lead}", headers=h).json()
    assert again["stage"] == "contacted" and again["status"] == "warm"
    assert [(d["outcome"], d["amount"], d["source"], d["reopened"]) for d in again["deals"]] == [("won", 45000, "IndiaMART", True)]   # on record, and marked
    report = client.get("/api/crm/reports", headers=h).json()
    assert (report["won"], report["value"]) == (0, 0)                                          # a reopened sale isn't counted
    assert [e["kind"] for e in again["timeline"] if e["kind"] in ("won", "reopened")] == ["reopened", "won"]   # newest first, in the order they happened
    # The task that was cancelled is still on record.
    assert [t.status for t in run(_rows, LeadTask, lead)] == ["cancelled"]


def test_someone_who_bought_and_asks_again_gets_new_work_and_keeps_the_sale(client, owner, run):
    lead = run(_contact, owner, source="Form")
    h = owner.h()
    client.post(f"/api/crm/leads/{lead}/close", json={"outcome": "won", "amount": 999}, headers=h)
    run(core.came_in, owner.id, lead, "Form", "second")
    back = client.get(f"/api/crm/leads/{lead}", headers=h).json()
    assert back["stage"] == "customer" and len(back["deals"]) == 1 and len(back["tasks"]) == 1
    client.post(f"/api/crm/leads/{lead}/close", json={"outcome": "lost", "reason": "Bought elsewhere"}, headers=h)    # this time they didn't buy
    client.post(f"/api/crm/leads/{lead}/reopen", headers=h)                                     # a correction: only that outcome is reopened
    deals = {d["outcome"]: d["reopened"] for d in client.get(f"/api/crm/leads/{lead}", headers=h).json()["deals"]}
    assert deals == {"won": False, "lost": True} and client.get("/api/crm/reports", headers=h).json()["value"] == 999


def test_someone_lost_who_asks_again_is_new_again(client, owner, run):
    lead = run(_contact, owner)
    h = owner.h()
    client.post(f"/api/crm/leads/{lead}/result", json={"result": "not_interested"}, headers=h)
    assert client.get(f"/api/crm/leads/{lead}", headers=h).json()["status"] == "not_interested"
    run(core.came_in, owner.id, lead, "Form", "changed their mind")
    back = client.get(f"/api/crm/leads/{lead}", headers=h).json()
    assert (back["stage"], back["status"]) == ("new", "new")
    assert [d["outcome"] for d in back["deals"]] == ["lost"] and len(back["tasks"]) == 1


def test_how_a_call_went_decides_what_comes_next(client, owner, run):
    h = owner.h()
    lead = run(_contact, owner, name="Asha")
    run(core.came_in, owner.id, lead, "Form", "r1")
    assert client.post(f"/api/crm/leads/{lead}/result", json={"result": "maybe"}, headers=h).status_code == 400
    assert client.post(f"/api/crm/leads/{lead}/result", json={"result": "later"}, headers=h).status_code == 400

    assert client.post(f"/api/crm/leads/{lead}/result", json={"result": "no_answer"}, headers=h).status_code == 200
    after = client.get(f"/api/crm/leads/{lead}", headers=h).json()
    assert [t["title"] for t in after["tasks"]] == ["Try Asha again"] and after["stage"] == "new"
    assert run(_get, Contact, lead).first_response_at is not None        # a try is a try

    later = (datetime.utcnow() + timedelta(days=2)).isoformat() + "Z"
    assert client.post(f"/api/crm/leads/{lead}/result", json={"result": "later", "next_at": later}, headers=h).status_code == 200
    assert [t["title"] for t in client.get(f"/api/crm/leads/{lead}", headers=h).json()["tasks"]] == ["Call Asha again"]

    assert client.post(f"/api/crm/leads/{lead}/result", json={"result": "reached"}, headers=h).status_code == 200
    reached = client.get(f"/api/crm/leads/{lead}", headers=h).json()
    assert reached["stage"] == "contacted" and reached["tasks"] == []

    wrong = run(_contact, owner)
    assert client.post(f"/api/crm/leads/{wrong}/result", json={"result": "wrong_number"}, headers=h).status_code == 200
    gone = client.get(f"/api/crm/leads/{wrong}", headers=h).json()
    assert gone["stage"] == "lost" and gone["quality"] == "wrong_number" and gone["deals"][0]["reason"] == "Wrong number"


def test_a_reminder_goes_once_to_whoever_has_the_task(client, owner, joined, run, alerts):
    seller = joined(owner)
    lead = run(_contact, owner, assigned_to=seller.id, name="Asha")
    at = datetime.utcnow()

    async def task():
        async with async_session() as db:
            contact = await db.get(Contact, lead)
            db.add(core.add_task(db, contact, "Call Asha", at - timedelta(minutes=1), "call", owner.id))
            await db.commit()
    run(task)

    async def twice():
        core._last_pass = None
        await core.tick(at)
        core._last_pass = None
        await core.tick(at + timedelta(minutes=5))
    run(twice)
    assert [(p, s) for o, p, s in alerts if o == owner.id] == [(seller.id, "Due now: Call Asha")]


def test_four_processes_send_one_reminder_and_move_a_task_once(client, owner, joined, run, alerts):
    seller, backup = joined(owner), joined(owner, name="Backup")
    client.put(f"/api/crm/settings/{owner.desk}", json={"assign": "one", "people": [seller.id], "backup": backup.id, "respond_minutes": 10}, headers=owner.h())
    lead = run(_contact, owner)
    run(core.came_in, owner.id, lead, "Form", "r1")
    task = run(_rows, LeadTask, lead)[0].id
    at = datetime.utcnow() + timedelta(minutes=25)

    async def together():
        await asyncio.gather(*(core._remind(task, at) for _ in range(4)))
        await asyncio.gather(*(core._escalate(task, at) for _ in range(4)))
    run(together)
    mine = [s.split(":")[0] for o, _p, s in alerts if o == owner.id]
    assert mine.count("Due now") == 1 and mine.count("Passed to you") == 1


def test_a_backup_who_left_gets_nothing(client, owner, joined, run, alerts):
    seller, backup = joined(owner), joined(owner, name="Backup")
    client.put(f"/api/crm/settings/{owner.desk}", json={"assign": "one", "people": [seller.id], "backup": backup.id, "respond_minutes": 10}, headers=owner.h())
    leave(client, owner, backup)
    lead = run(_contact, owner)
    run(core.came_in, owner.id, lead, "Form", "r1")

    async def tick():
        core._last_pass = None
        await core.tick(datetime.utcnow() + timedelta(minutes=25))
    run(tick)
    assert run(_get, Contact, lead).assigned_to == seller.id


def test_reminders_come_with_team_alerts_on_the_plan(client, owner, joined, run, alerts, monkeypatch):
    monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")
    lead = run(_contact, owner, assigned_to=owner.id)

    async def task():
        async with async_session() as db:
            contact = await db.get(Contact, lead)
            db.add(core.add_task(db, contact, "Call them", datetime.utcnow() - timedelta(minutes=1), "call", owner.id))
            await db.commit()
    run(task)
    run(core.tick)
    assert not [a for a in alerts if a[0] == owner.id]                           # the free plan has none; the task still shows in Needs attention
    assert client.get("/api/crm/queues", headers=owner.h()).json()["overdue"]


def test_a_reminded_task_isnt_picked_again(owner, run, monkeypatch):
    monkeypatch.setattr(core, "BATCH", 100_000)
    lead = run(_contact, owner, assigned_to=owner.id)

    async def tasks():
        async with async_session() as db:
            contact = await db.get(Contact, lead)
            old = core.add_task(db, contact, "Reminded already", datetime.utcnow() - timedelta(minutes=30), "call", owner.id)
            old.reminded_at = datetime.utcnow() - timedelta(minutes=29)
            new = core.add_task(db, contact, "Due now", datetime.utcnow() - timedelta(minutes=1), "call", owner.id)
            await db.commit()
            return old.id, new.id
    old, new = run(tasks)

    async def due():
        async with async_session() as db:
            return await core._due(db, datetime.utcnow())
    found = run(due)
    assert new in found and old not in found


def test_a_lead_given_back_after_the_backup_got_it_stays(client, owner, joined, run, alerts):
    seller, backup = joined(owner), joined(owner, name="Backup")
    client.put(f"/api/crm/settings/{owner.desk}", json={"assign": "one", "people": [seller.id], "backup": backup.id, "respond_minutes": 10}, headers=owner.h())
    lead = run(_contact, owner)
    run(core.came_in, owner.id, lead, "Form", "r1")
    task = run(_rows, LeadTask, lead)[0].id
    at = datetime.utcnow() + timedelta(minutes=25)
    run(core._escalate, task, at)
    assert run(_get, Contact, lead).assigned_to == backup.id
    assert client.put(f"/api/crm/leads/{lead}", json={"assigned_to": seller.id}, headers=owner.h()).status_code == 200   # a manager gives it back
    run(core._escalate, task, at + timedelta(minutes=5))                                                                     # another process acting late
    assert run(_get, Contact, lead).assigned_to == seller.id
    assert [s.split(":")[0] for o, _p, s in alerts if o == owner.id].count("Passed to you") == 1


def test_the_end_of_a_call_brings_the_caller_into_leads(owner, run, monkeypatch):
    from mail import after_call as after_call_email
    from tests.test_pipeline import FakeStt, FakeTransport, _setup, fake_summary, fake_tts, replier_saying
    from voice import memory, pipeline, schedule

    async def nothing(*_a):
        return None
    for module, name in ((memory, "remember_call"), (schedule, "after_call"), (after_call_email, "queue")):
        monkeypatch.setattr(module, name, nothing)
    e164 = number()
    lead = run(_contact, owner, e164=e164)
    call_id = run(_call, owner, e164)

    async def finish():
        session = pipeline.CallSession(await _setup(owner.id, owner.desk), FakeTransport(), stt_factory=lambda *a: FakeStt([]), tts=fake_tts,
                                       replier=replier_saying("x"), summarizer=fake_summary)
        session.call_id = call_id
        await session._remember_and_plan()
    run(finish)
    assert [e.text for e in run(_rows, LeadEvent, lead)] == ["Phone call"]


def test_old_tasks_are_not_reminded_of_all_at_once(client, owner, run, alerts):
    lead = run(_contact, owner, assigned_to=owner.id)

    async def task():
        async with async_session() as db:
            contact = await db.get(Contact, lead)
            db.add(core.add_task(db, contact, "Long ago", datetime.utcnow() - timedelta(days=3), "call", owner.id))
            await db.commit()
    run(task)
    run(core.tick)
    assert not [a for a in alerts if a[0] == owner.id]


def test_a_first_step_nobody_took_moves_to_the_backup_once(client, owner, joined, run, alerts):
    seller, backup = joined(owner), joined(owner, name="Backup")
    client.put(f"/api/crm/settings/{owner.desk}", json={"assign": "one", "people": [seller.id], "backup": backup.id, "respond_minutes": 10}, headers=owner.h())
    lead = run(_contact, owner, name="Asha")
    run(core.came_in, owner.id, lead, "Form", "r1")
    task = run(_rows, LeadTask, lead)[0]
    assert task.assigned_to == seller.id

    async def tick(minutes):
        core._last_pass = None
        await core.tick(datetime.utcnow() + timedelta(minutes=minutes))
    run(tick, 12)                                     # due, not yet late: a reminder to the seller
    assert run(_get, Contact, lead).assigned_to == seller.id
    run(tick, 21)                                     # past the time again: the backup's now
    run(tick, 22)
    moved = run(_get, Contact, lead)
    task = run(_get, LeadTask, task.id)
    assert moved.assigned_to == backup.id and task.assigned_to == backup.id
    mine = [(p, s.split(":")[0]) for o, p, s in alerts if o == owner.id]
    assert mine.count((seller.id, "Due now")) == 1 and mine.count((backup.id, "Passed to you")) == 1
    assert [e.text for e in sorted(run(_rows, LeadEvent, lead), key=lambda e: e.at) if e.kind == "assigned"][-1].startswith("Now with")   # in time order: Postgres keeps none


def test_a_task_someone_finished_doesnt_move(client, owner, joined, run, alerts):
    seller, backup = joined(owner), joined(owner, name="Backup")
    client.put(f"/api/crm/settings/{owner.desk}", json={"assign": "one", "people": [seller.id], "backup": backup.id, "respond_minutes": 10}, headers=owner.h())
    lead = run(_contact, owner)
    run(core.came_in, owner.id, lead, "Form", "r1")
    client.post(f"/api/crm/leads/{lead}/result", json={"result": "reached"}, headers=owner.h())

    async def tick():
        core._last_pass = None
        await core.tick(datetime.utcnow() + timedelta(minutes=25))
    run(tick)
    assert run(_get, Contact, lead).assigned_to == seller.id
    assert not [a for a in alerts if a[0] == owner.id]


def test_needs_attention_shows_what_needs_someone(client, owner, joined, run):
    h = owner.h()
    late = run(_contact, owner, name="Late")
    due = run(_contact, owner, name="Due")
    fresh = run(_contact, owner, name="Fresh")
    stuck = run(_contact, owner, name="Stuck", assigned_to=owner.id)
    done = run(_contact, owner, name="Done", stage="customer")
    old = run(_contact, owner, name="Old", created_at=datetime.utcnow() - timedelta(days=60))
    now = datetime.utcnow()
    client.post(f"/api/crm/leads/{late}/tasks", json={"title": "Late one", "due_at": (now - timedelta(hours=2)).isoformat() + "Z"}, headers=h)
    client.post(f"/api/crm/leads/{due}/tasks", json={"title": "Soon", "due_at": (now + timedelta(minutes=2)).isoformat() + "Z"}, headers=h)

    async def asked():
        async with async_session() as db:
            db.add(CallbackJob(user_id=owner.id, bot_id=owner.desk, e164=number(), name="Wants a person", kind="person", status="todo", consent_source="test", purpose="About prices"))
            db.add(Meeting(user_id=owner.id, bot_id=owner.desk, e164=number(), name="Wants a meeting", topic="Demo", starts_at=now + timedelta(days=1), status="requested"))
            await db.commit()
    run(asked)
    q = client.get("/api/crm/queues", headers=h).json()
    names = {k: [x["name"] for x in q[k]] for k in q}
    assert names["overdue"] == ["Late"] and names["today"] == ["Due"]
    assert "Fresh" in names["new"] and "Stuck" not in names["new"]
    assert "Stuck" in names["no_next"] and "Fresh" not in names["no_next"]   # once is enough
    assert "Done" not in names["no_next"] + names["new"] and "Old" not in names["no_next"] + names["new"]
    assert names["asked_for_person"] == ["Wants a person"] and names["meetings"] == ["Wants a meeting"]
    assert done and old and fresh and stuck


def test_all_leads_can_be_searched_filtered_and_paged(client, owner, joined, run):
    seller = joined(owner)
    h = owner.h()
    asha = run(_contact, owner, name="Asha Rao", e164="+919876512345", email="asha@buyers.in", assigned_to=seller.id, source="IndiaMART")
    ravi = run(_contact, owner, name="Ravi", stage="interested", source="chat")
    both = [asha, ravi]
    ids = lambda **q: [x["id"] for x in client.get("/api/crm/leads", params=q, headers=h).json()["items"]]
    assert ids(q="asha") == [asha] and ids(q="BUYERS") == [asha] and ids(q="12345") == [asha] and ids(q="zzz") == []
    assert ids(stage="interested") == [ravi] and asha in ids(stage="new")
    assert ids(owner=seller.id) == [asha] and ids(owner="nobody") == [ravi] and ids(source="IndiaMART") == [asha]
    assert ids(due="none") and set(ids(due="none")) == set(both) and ids(due="overdue") == []
    page = client.get("/api/crm/leads", params={"limit": 1, "offset": 1}, headers=h).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get("/api/crm/leads", params={"limit": 100000}, headers=h).status_code == 200


def test_the_export_can_run_nothing_and_says_who_took_it(client, owner, run):
    run(_contact, owner, name='=HYPERLINK("http://bad.example","x")', email="plain@buyers.in", tags=["@tag"], source="+1+1")
    run(_contact, owner, name="-2+3", e164="+919876512399", source="\tTabbed")
    out = client.get("/api/crm/leads/export", headers=owner.h())
    assert out.status_code == 200 and out.headers["content-type"].startswith("text/csv")
    rows = {r["Email"] or r["Name"]: r for r in csv.DictReader(io.StringIO(out.text))}
    first = rows["plain@buyers.in"]
    assert first["Name"].startswith("'=") and first["Tags"] == "'@tag" and first["Source"] == "'+1+1"
    assert rows["'-2+3"]["Source"] == "'\tTabbed" and rows["'-2+3"]["Phone"].replace(" ", "") == "+919876512399"

    async def logged():
        from backend.models import NotificationLog
        async with async_session() as db:
            return (await db.execute(select(NotificationLog).where(NotificationLog.user_id == owner.id, NotificationLog.kind == "leads_export"))).scalars().all()
    assert [r.error for r in run(logged)] == ["2 leads"]


def test_one_leads_page_tells_the_whole_story(client, owner, run):
    e164, address = number(), "story@buyers.in"
    lead = run(_contact, owner, e164=e164, email=address, name="Story", notes="Prefers mornings")
    h = owner.h()

    async def seed():
        async with async_session() as db:
            now = datetime.utcnow()
            db.add(CallLog(user_id=owner.id, bot_id=owner.desk, caller_e164=e164, summary="Asked about the price", started_at=now - timedelta(hours=3)))
            db.add(Meeting(user_id=owner.id, bot_id=owner.desk, e164=e164, name="Story", topic="Visit", starts_at=now + timedelta(days=3), status="confirmed"))  # past any reminder pass
            db.add(EmailJob(user_id=owner.id, bot_id=owner.desk, kind="welcome", ref_id=uuid.uuid4().hex, to_email=address.upper(), subject="Welcome", body="Hi", status="sent", sent_at=now - timedelta(hours=2), send_at=now))
            db.add(LeadIntake(user_id=owner.id, bot_id=owner.desk, contact_id=lead, channel="form", source="Website", ref=uuid.uuid4().hex, status="done", found={"name": "Story", "wants": "2BHK"}, origin={"utm_source": "google"},
                              consents=[{"text": "Call me about this", "agreed": True}]))
            await db.commit()
    run(seed)
    client.post(f"/api/crm/leads/{lead}/notes", json={"text": "Spoke on the way in"}, headers=h)
    made = client.post(f"/api/crm/leads/{lead}/tasks", json={"title": "Send the plan", "due_at": datetime.utcnow().isoformat() + "Z", "kind": "email"}, headers=h).json()
    client.put(f"/api/crm/tasks/{made['id']}", json={"status": "done", "result": "Sent"}, headers=h)
    page = client.get(f"/api/crm/leads/{lead}", headers=h).json()
    kinds = {t["kind"] for t in page["timeline"]}
    assert {"call", "meeting", "email", "submission", "note", "task"} <= kinds
    assert page["timeline"] == sorted(page["timeline"], key=lambda t: t["at"], reverse=True)
    form = next(t for t in page["timeline"] if t["kind"] == "submission")
    assert form["found"]["wants"] == "2BHK" and form["origin"] == {"utm_source": "google"} and form["consents"][0]["agreed"]
    assert page["notes"] == "Prefers mornings" and page["stage"] == "new"
    assert run(_get, Contact, lead).first_response_at is not None


def test_the_story_stays_within_the_assistant(client, owner, run):
    """One account can run several businesses: the same person's calls with another one aren't this lead's."""
    e164, address = number(), "two.shops@buyers.in"
    lead = run(_contact, owner, e164=e164, email=address)
    other = owner.bot("Other shop")

    async def seed():
        async with async_session() as db:
            now = datetime.utcnow()
            db.add(CallLog(user_id=owner.id, bot_id=other, caller_e164=e164, summary="About the other shop", started_at=now))
            db.add(Meeting(user_id=owner.id, bot_id=other, e164=e164, name="x", topic="Other", starts_at=now + timedelta(days=3), status="confirmed"))
            db.add(EmailJob(user_id=owner.id, bot_id=other, kind="welcome", ref_id=uuid.uuid4().hex, to_email=address, subject="Other shop", body="Hi", status="sent", sent_at=now, send_at=now))
            await db.commit()
    run(seed)
    assert client.get(f"/api/crm/leads/{lead}", headers=owner.h()).json()["timeline"] == []


def test_the_days_an_enquiry_allows_are_counted_from_their_last_one(client, owner, run):
    h = owner.h()
    fresh = run(_contact, owner, last_enquiry_at=datetime.utcnow() - timedelta(days=2))
    old = run(_contact, owner, created_at=datetime.utcnow() - timedelta(days=30), last_enquiry_at=datetime.utcnow() - timedelta(days=9))
    from_a_list = run(_contact, owner, created_at=datetime.utcnow() - timedelta(days=1))    # never asked anything: nothing to count from
    assert client.get(f"/api/crm/leads/{fresh}", headers=h).json()["enquiry_days_left"] == 5
    assert client.get(f"/api/crm/leads/{old}", headers=h).json()["enquiry_days_left"] == 0
    assert client.get(f"/api/crm/leads/{from_a_list}", headers=h).json()["enquiry_days_left"] is None


def test_the_report_counts_by_source_and_by_person(client, owner, run):
    h = owner.h()
    now = datetime.utcnow()
    a = run(_contact, owner, source="IndiaMART", stage="contacted", created_at=now - timedelta(minutes=30), first_response_at=now - timedelta(minutes=27), assigned_to=owner.id)
    b = run(_contact, owner, source="IndiaMART", created_at=now - timedelta(hours=3), first_response_at=now - timedelta(hours=1))
    c = run(_contact, owner, source="chat", created_at=now - timedelta(hours=1))
    run(_contact, owner, source="chat", created_at=now - timedelta(days=45))                 # too old for this report
    client.post(f"/api/crm/leads/{a}/close", json={"outcome": "won", "amount": 12000}, headers=h)
    client.post(f"/api/crm/leads/{b}/close", json={"outcome": "lost", "reason": "Too expensive", "amount": 30000}, headers=h)    # what it would have been worth
    r = client.get("/api/crm/reports?days=30", headers=h).json()
    by = {s["source"]: s for s in r["sources"]}
    assert r["leads"] == 3 and (r["won"], r["lost"], r["value"]) == (1, 1, 12000)
    assert by["IndiaMART"]["leads"] == 2 and by["IndiaMART"]["won"] == 1 and by["IndiaMART"]["lost"] == 1 and by["IndiaMART"]["value"] == 12000 and by["chat"]["leads"] == 1
    assert r["first_response"]["within_5"] == 1 and r["first_response"]["not_tried"] == 1 and r["first_response"]["measured"] == 2
    assert r["lost_reasons"] == [{"reason": "Too expensive", "count": 1}]
    assert next(p for p in r["team"] if p["id"] == owner.id)["won"] == 1
    assert c


def test_the_board_closing_a_lead_records_it_like_the_lead_page(client, owner, run):
    lead = run(_contact, owner, source="chat")
    assert client.put(f"/api/email/board/leads/{lead}", json={"stage": "customer"}, headers=owner.h()).status_code == 200
    assert [d.outcome for d in run(_rows, LeadDeal, lead)] == ["won"]
    assert client.put(f"/api/email/board/leads/{lead}", json={"stage": "interested"}, headers=owner.h()).status_code == 200   # moved back: reopened
    assert [d.reopened_at is not None for d in run(_rows, LeadDeal, lead)] == [True]


def test_erase_leaves_nothing_of_the_lead(client, owner, run):
    e164 = number()
    lead = run(_contact, owner, e164=e164)
    run(core.came_in, owner.id, lead, "Form", "r1")
    client.post(f"/api/crm/leads/{lead}/close", json={"outcome": "won", "amount": 5}, headers=owner.h())
    assert client.post("/api/voice/erase", json={"number": e164}, headers=owner.h()).status_code == 200
    assert client.get(f"/api/crm/leads/{lead}", headers=owner.h()).status_code == 404
    for model in (LeadTask, LeadEvent, LeadDeal):
        assert run(_rows, model, lead) == []


def test_erase_works_for_someone_known_only_by_email(client, owner, run):
    address = f"mail.{uuid.uuid4().hex[:8]}@buyers.in"
    lead = run(_contact, owner, e164=None, email=address)
    run(core.came_in, owner.id, lead, "Form", "r1")
    other = run(_contact, owner, e164=None, email="someone.else@buyers.in", name="Keep me")

    async def seed():
        async with async_session() as db:
            db.add(EmailJob(user_id=owner.id, bot_id=owner.desk, kind="welcome", ref_id=uuid.uuid4().hex, to_email=address, subject="Hi", body="Hi", status="sent", send_at=datetime.utcnow()))
            db.add(LeadIntake(user_id=owner.id, bot_id=owner.desk, contact_id=lead, channel="form", source="Website", ref=uuid.uuid4().hex, status="done", found={"email": address}))
            db.add(Conversation(bot_id=owner.desk, visitor_session_id=f"s-{uuid.uuid4().hex[:8]}", captured_data={"Email": address}))
            await db.commit()
    run(seed)
    assert client.post("/api/voice/erase", json={"number": address.upper()}, headers=owner.h()).json()["chats_deleted"] == 1
    assert client.get(f"/api/crm/leads/{lead}", headers=owner.h()).status_code == 404
    assert client.get(f"/api/crm/leads/{other}", headers=owner.h()).status_code == 200

    async def left():
        async with async_session() as db:
            return ((await db.execute(select(func.count()).select_from(EmailJob).where(EmailJob.to_email == address))).scalar_one(),
                    (await db.execute(select(func.count()).select_from(LeadIntake).where(LeadIntake.contact_id == lead))).scalar_one())
    assert run(left) == (0, 0)
    assert run(_rows, LeadTask, lead) == []


def test_erase_by_email_goes_by_their_number_when_there_is_one(client, owner, run):
    e164, address = number(), "both@buyers.in"
    lead = run(_contact, owner, e164=e164, email=address)

    async def call():
        async with async_session() as db:
            db.add(CallLog(user_id=owner.id, bot_id=owner.desk, caller_e164=e164))
            await db.commit()
    run(call)
    assert client.post("/api/voice/erase", json={"number": address}, headers=owner.h()).json()["calls_deleted"] == 1
    assert client.get(f"/api/crm/leads/{lead}", headers=owner.h()).status_code == 404


def test_a_bad_erase_is_refused(client, owner):
    assert client.post("/api/voice/erase", json={"number": "12"}, headers=owner.h()).status_code == 400


def test_a_lead_arriving_never_fails_even_if_the_database_does(owner, run, monkeypatch):
    from notify import events

    async def down(*a):
        raise RuntimeError("The database went away")
    monkeypatch.setattr(events, "_once", down)
    run(core.came_in, owner.id, str(uuid.uuid4()), "Form", "r1")


def test_two_submissions_at_the_same_moment_make_one_first_step(owner, run):
    leads = [run(_contact, owner) for _ in range(3)]

    async def together():
        await asyncio.gather(*(core.came_in(owner.id, lead, "Form", f"{lead}:{n}") for lead in leads for n in (1, 2)))
    run(together)
    for lead in leads:
        assert sorted(e.kind for e in run(_rows, LeadEvent, lead)) == ["asked_again", "came_in"]
        assert len(run(_rows, LeadTask, lead)) == 1


def test_a_turn_is_read_where_it_is_kept(client, owner, joined, run):
    """Another process gave out a lead after this one last read the rules: the next lead still goes to the next person."""
    a, b = joined(owner), joined(owner, name="B")
    client.put(f"/api/crm/settings/{owner.desk}", json={"assign": "turns", "people": [a.id, b.id]}, headers=owner.h())

    async def interleaved():
        async with async_session() as first:
            held = await first.get(LeadSettings, owner.desk)       # this process read the turn a moment ago, and holds it
            async with async_session() as second:
                one = await core._next_person(second, owner.desk, await core.settings_of(second, owner.desk))
                await second.commit()
            two = await core._next_person(first, owner.desk, await core.settings_of(first, owner.desk))
            await first.commit()
            assert held is not None
        return one, two
    assert set(run(interleaved)) == {a.id, b.id}


def test_a_lead_arriving_never_fails_because_of_this(owner, run, monkeypatch):
    async def broken(*a):
        raise RuntimeError("The database went away")
    monkeypatch.setattr(core, "_came_in", broken)
    run(core.came_in, owner.id, str(uuid.uuid4()), "Form", "r1")


def test_nothing_about_a_lead_is_written_for_a_contact_that_is_gone(owner, run):
    run(core.came_in, owner.id, str(uuid.uuid4()), "Form", "r1")


def test_rules_row_is_made_once(client, owner):
    url = f"/api/crm/settings/{owner.desk}"
    client.put(url, json={"assign": "one", "people": [owner.id]}, headers=owner.h())
    client.put(url, json={"assign": "turns", "people": [owner.id]}, headers=owner.h())
    assert client.get(url, headers=owner.h()).json()["settings"]["assign"] == "turns"


def test_nimmi_opens_a_lead_only_if_they_may_reach_it(client, owner, joined, make_user, run):
    from agent import registry
    from auth import AuthContext
    seller, stranger = joined(owner), make_user("Stranger")
    mine, not_mine = run(_contact, owner, assigned_to=seller.id), run(_contact, owner)
    as_seller = registry.ToolContext(ctx=AuthContext(seller.id, owner.id, "agent"), run_id="r", thread_id="t", screen={})
    opened = run(registry.run, as_seller, "go_to", {"page": "leads_lead", "lead_id": mine})
    assert opened.ok and f"/dashboard/leads/{mine}" in opened.text
    assert not run(registry.run, as_seller, "go_to", {"page": "leads_lead", "lead_id": not_mine}).ok
    assert not run(registry.run, as_seller, "go_to", {"page": "leads_lead"}).ok
    assert not run(registry.run, as_seller, "lead_details", {"lead_id": not_mine}).ok
    outsider = registry.ToolContext(ctx=AuthContext(stranger.id, stranger.id, "owner"), run_id="r", thread_id="t", screen={})
    assert not run(registry.run, outsider, "go_to", {"page": "leads_lead", "lead_id": mine}).ok
