"""Questions to answer, escalation, business hours, saved replies, notes, lead score and templates."""
from datetime import datetime, timezone

import assist
from routers import chat as chat_router
from voice import llm
from backend.models import VoiceAgent

WEEK = {d: {"open": True, "from": "09:00", "to": "18:00"} for d in assist.DAYS}


def _ask(client, user, bot, text, session="s-1"):
    r = client.post("/api/chat/message", json={"bot_id": bot, "message": text, "visitor_session_id": session,
                                               "history": [], "is_demo": True}, headers=user.h())
    assert r.status_code == 200, r.text
    return r.json()["answer"]


def _wait(predicate, timeout=3.0):
    """Background work (recording a question) runs on the app's loop; poll from the test thread."""
    import time
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_unanswered_questions_are_collected_answered_and_used(client, make_user, monkeypatch, run):
    u = make_user()
    bot = u.bot()
    contexts = []

    def fake_ai(system, context, question, **kw):
        contexts.append(system + context)  # the knowledge is part of the assistant's instructions
        return "I'm sorry, I don't have that information in my current knowledge base."
    monkeypatch.setattr(chat_router, "generate_ai_response", fake_ai)

    _ask(client, u, bot, "Do you have parking?")
    _ask(client, u, bot, "do you have PARKING", session="s-2")  # same question, other wording case
    assert _wait(lambda: client.get("/api/questions", headers=u.h()).json()["items"][:1]
                 and client.get("/api/questions", headers=u.h()).json()["items"][0]["count"] == 2)
    q = client.get("/api/questions", headers=u.h()).json()["items"][0]
    assert q["question"] == "Do you have parking?" and q["channel"] == "chat"

    r = client.post(f"/api/questions/{q['id']}/answer", json={"answer": "Yes, free parking for 40 cars."}, headers=u.h())
    assert r.status_code == 200
    _ask(client, u, bot, "Is there parking?", session="s-3")
    assert "Answers confirmed by the business" in contexts[-1] and "free parking for 40 cars" in contexts[-1]
    lists = client.get("/api/questions?status=answered", headers=u.h()).json()
    assert lists["counts"]["answered"] == 1 and lists["items"][0]["answer"].startswith("Yes")

    # Teach one in advance, and dismiss noise.
    assert client.post("/api/questions", json={"bot_id": bot, "question": "Do you deliver?", "answer": "Within 5 km."},
                       headers=u.h()).status_code == 200
    other = make_user()
    assert client.post(f"/api/questions/{q['id']}/dismiss", headers=other.h()).status_code == 404  # not theirs


def test_upset_customers_are_handed_to_a_person(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    monkeypatch.setattr(chat_router, "generate_ai_response", lambda *a, **k: "Happy to help.")
    reply = _ask(client, u, bot, "This is the WORST service, totally useless")
    assert reply.startswith("I'm sorry about this")
    assert client.get("/api/handoffs/pending", headers=u.h()).json()[0]["lead"]["label"] in ("cold", "warm", "hot")

    settings = client.get("/api/workspace/settings", headers=u.h()).json()
    client.put("/api/workspace/settings", json={"business_hours": settings["business_hours"], "escalate_upset": False}, headers=u.h())
    assert _ask(client, u, bot, "worst service ever", session="s-9") == "Happy to help."


def test_business_hours_logic():
    hours = {**assist.DEFAULT_HOURS, "enabled": True, "days": {**WEEK, "sun": {"open": False, "from": "09:00", "to": "18:00"}},
             "holidays": ["2026-10-20"]}
    ist = lambda y, mo, d, h, mi: datetime(y, mo, d, h, mi, tzinfo=assist.IST).astimezone(timezone.utc)  # noqa: E731
    assert assist.is_open(hours, ist(2026, 10, 14, 10, 0))          # Wednesday 10:00
    assert not assist.is_open(hours, ist(2026, 10, 14, 19, 0))      # after closing
    assert assist.next_open(hours, ist(2026, 10, 14, 19, 0)) == "tomorrow at 9:00 AM"
    assert assist.next_open(hours, ist(2026, 10, 14, 7, 30)) == "today at 9:00 AM"
    assert assist.next_open(hours, ist(2026, 10, 17, 19, 0)) == "on Monday at 9:00 AM"   # Saturday night, Sunday closed
    assert not assist.is_open(hours, ist(2026, 10, 20, 11, 0))      # holiday
    assert assist.is_open({**hours, "enabled": False}, ist(2026, 10, 18, 3, 0))  # off: always open


def test_after_hours_handoff_and_settings_validation(client, make_user):
    u = make_user()
    bot = u.bot()
    today = datetime.now(assist.IST).strftime("%Y-%m-%d")
    bad = {"business_hours": {"enabled": True, "days": {**WEEK, "mon": {"open": True, "from": "18:00", "to": "09:00"}}},
           "escalate_upset": True}
    assert client.put("/api/workspace/settings", json=bad, headers=u.h()).status_code == 400
    ok = {"business_hours": {"enabled": True, "days": WEEK, "holidays": [today], "away_message": "We're closed. Back {next_open}."},
          "escalate_upset": True}
    s = client.put("/api/workspace/settings", json=ok, headers=u.h()).json()
    assert s["open_now"] is False and s["next_open"]
    r = client.post("/api/chat/handoff", json={"bot_id": bot, "visitor_session_id": "widget-session-human-x"}).json()
    assert r["away"] is True and r["message"].startswith("We're closed. Back ")


def test_voice_after_hours_takes_a_message_instead_of_transferring():
    agent = VoiceAgent(assistant_name="Nimmi", company_name="Acme", language="en-IN", transfer_enabled=True,
                       transfer_number="+919840012345", transfer_when="they ask for a person", team_handoff=False)

    class B:
        bot_name, system_prompt = "Acme", ""
    open_prompt = llm.system_prompt(agent, B(), "", "inbound", None)
    closed_prompt = llm.system_prompt(agent, B(), "", "inbound", None, after_hours="tomorrow at 9:00 AM")
    assert llm.TRANSFER in open_prompt and llm.TRANSFER not in closed_prompt
    assert "back tomorrow at 9:00 AM" in closed_prompt
    # With the team rung in the dashboard (the default), the AI asks for a person through its tool instead: it says who
    # can join, the team or the number, at that moment.
    team = VoiceAgent(assistant_name="Nimmi", company_name="Acme", language="en-IN", transfer_enabled=True,
                      transfer_number="+919840012345", transfer_when="they ask for a person")
    team_prompt = llm.system_prompt(team, B(), "", "inbound", None)
    assert "use ask_for_person" in team_prompt and llm.TRANSFER not in team_prompt


def test_saved_replies(client, make_user):
    u, other = make_user(), make_user()
    r = client.post("/api/workspace/replies", json={"title": "Timings", "body": "We're open 9 to 6, Monday to Saturday."}, headers=u.h())
    assert r.status_code == 200
    rid = r.json()["id"]
    assert client.put(f"/api/workspace/replies/{rid}", json={"title": "Hours", "body": "9 to 6."}, headers=u.h()).json()["title"] == "Hours"
    assert [x["title"] for x in client.get("/api/workspace/replies", headers=u.h()).json()] == ["Hours"]
    assert client.get("/api/workspace/replies", headers=other.h()).json() == []
    assert client.delete(f"/api/workspace/replies/{rid}", headers=other.h()).status_code == 404
    assert client.delete(f"/api/workspace/replies/{rid}", headers=u.h()).status_code == 200


def test_internal_notes_stay_internal(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    monkeypatch.setattr(chat_router, "generate_ai_response", lambda *a, **k: "Sure.")
    _ask(client, u, bot, "I want to talk to a human", session="widget-session-human-n1")
    conv = client.get("/api/handoffs/pending", headers=u.h()).json()[0]
    r = client.post(f"/api/handoffs/{conv['conversation_id']}/notes", json={"text": "VIP customer, offer 10% off"}, headers=u.h())
    assert r.status_code == 200 and r.json()["author"] == "Test User"
    msgs = client.get(f"/api/handoffs/{conv['conversation_id']}/messages", headers=u.h()).json()
    note = [m for m in msgs if m["role"] == "note"]
    assert note and note[0]["content"] == "VIP customer, offer 10% off" and note[0]["author"] == "Test User"
    assert client.post(f"/api/handoffs/{conv['conversation_id']}/notes", json={"text": "x"}, headers=make_user().h()).status_code == 404


def test_a_team_reply_reaches_the_widget_without_the_socket(client, make_user):
    """The reply is sent over HTTP and the widget also checks for replies, so it arrives even when the team's
    socket and the visitor's are on different server processes (production runs several)."""
    u = make_user()
    bot = u.bot()
    session = "widget-session-human-r1"
    assert client.post("/api/chat/handoff", json={"bot_id": bot, "visitor_session_id": session}).json()["earlier"] == []
    conv = client.get("/api/handoffs/pending", headers=u.h()).json()[0]["conversation_id"]

    r = client.post(f"/api/handoffs/{conv}/reply", json={"text": "Hi, this is Meena. How can I help?"}, headers=u.h())
    assert r.status_code == 200 and r.json()["sender"] == "agent"
    reply_id = r.json()["id"]
    live = client.get(f"/api/chat/live/{bot}/{session}").json()
    assert live["status"] == "human" and live["messages"] == [{"id": reply_id, "text": "Hi, this is Meena. How can I help?"}]
    assert client.get(f"/api/handoffs/{conv}/messages", headers=u.h()).json()[-1]["content"].startswith("Hi, this is Meena")

    # The same visitor asks for a person again later: the earlier reply is marked seen, not shown as new.
    client.post(f"/api/handoffs/{conv}/close", headers=u.h())
    earlier = client.post("/api/chat/handoff", json={"bot_id": bot, "visitor_session_id": session}).json()["earlier"]
    assert reply_id in earlier

    # Another workspace can't reply, and a session id that isn't a person chat isn't readable.
    assert client.post(f"/api/handoffs/{conv}/reply", json={"text": "x"}, headers=make_user().h()).status_code == 404
    assert client.get(f"/api/chat/live/{bot}/widget-session-ai-r1").status_code == 404
    assert client.get(f"/api/chat/live/{bot}/widget-session-human-nobody").json() == {"status": "ai", "messages": []}


def test_lead_score():
    hot = assist.lead_score({"Name": "Ravi", "Phone": "9876543210", "Budget": "65"}, successful=True, sentiment="positive")
    assert hot["label"] == "hot" and hot["score"] >= 60 and "Goal met" in hot["reasons"]
    assert assist.lead_score({"Email": "a@b.co"})["label"] == "cold"
    assert assist.lead_score({"Phone": "9876543210"}, sentiment="negative")["score"] == 10


def test_templates(client, make_user):
    u = make_user()
    catalog = client.get("/api/bots/templates").json()
    assert {"real_estate", "clinic", "ecommerce"} <= {t["id"] for t in catalog}
    r = client.post("/api/bots/create", json={"name": "Green Homes", "template": "real_estate"}, headers=u.h())
    assert r.status_code == 200 and r.json()["template"] == "real_estate"
    agent = client.get(f"/api/voice/agents/{r.json()['id']}", headers=u.h()).json()
    assert agent["call_goal"].startswith("The caller books a site visit")
    assert [f["label"] for f in agent["collect_fields"]][:2] == ["Name", "Phone number"]
    assert agent["company_name"] == "Green Homes" and agent["enabled"] is False
    assert client.post("/api/bots/create", json={"name": "X", "template": "nope"}, headers=u.h()).status_code == 400


def test_unanswered_detection():
    assert assist.is_unanswered("I'm sorry, I don't have that information in my current knowledge base.")
    assert assist.is_unanswered("I don’t have that information right now, but I can connect you to our team.")
    assert assist.is_unanswered("Let me have the team follow up on that.")
    assert not assist.is_unanswered("We have parking for 40 cars.")
    assert assist.is_upset("Ye bakwas service hai") and assist.is_upset("WHY IS MY ORDER LATE AGAIN")
    assert not assist.is_upset("Is the travel agent discount available?")
