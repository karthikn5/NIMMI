"""Reply settings from the builder's Behaviour tab: stored, validated, and turned into prompt rules."""
import assist
import behaviour
from routers import chat as chat_router


def test_rules_only_apply_once_settings_are_saved():
    assert behaviour.rules(None) == ""
    assert behaviour.fallback(None) == "I'm sorry, I don't have that information."
    # The old one-line contact rule only applies when detail collection is turned off.
    r = behaviour.rules({"reply_length": "short", "language": "ta", "ask_for_contact": True, "offer_human": False,
                         "collect": {"enabled": False}})
    assert "short" in r and "Tamil" in r and "phone number" in r and "Person" not in r
    assert "phone number" not in behaviour.rules({"ask_for_contact": True})  # collection (on by default) covers it


def test_custom_follow_up_still_counts_as_unanswered():
    said = behaviour.fallback({"fallback_followup": "Call us on 044 4567 8900."})
    assert said.endswith("Call us on 044 4567 8900.")
    assert assist.is_unanswered(said)


def test_invalid_values_fall_back_to_defaults():
    b = behaviour.clean({"reply_length": "huge", "language": "xx", "offer_human": "yes", "fallback_followup": "x" * 400})
    assert b["reply_length"] == "balanced" and b["language"] == "match" and b["offer_human"] is True
    assert len(b["fallback_followup"]) == 300


def test_saved_from_builder_and_used_in_the_prompt(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    assert client.get(f"/api/bots/{bot}/config", headers=u.h()).json()["behaviour"]["language"] == "match"

    r = client.patch(f"/api/bots/{bot}", json={"behaviour": {"reply_length": "short", "language": "hi",
                                                              "fallback_followup": "Call us.", "junk": 1}}, headers=u.h())
    assert r.status_code == 200, r.text
    saved = client.get(f"/api/bots/{bot}/config", headers=u.h()).json()["behaviour"]
    assert saved["language"] == "hi" and "junk" not in saved
    assert "behaviour" not in client.get(f"/api/bots/{bot}/config").json()  # not public

    prompts = []

    def fake_ai(system, context, question, **kw):
        prompts.append(system)
        return "Namaste!"
    monkeypatch.setattr(chat_router, "generate_ai_response", fake_ai)
    r = client.post("/api/chat/message", json={"bot_id": bot, "message": "Hello", "visitor_session_id": "s-b",
                                               "history": [], "is_demo": True}, headers=u.h())
    assert r.status_code == 200, r.text
    assert "Always reply in Hindi." in prompts[-1] and "I don't have that information. Call us." in prompts[-1]

    monkeypatch.setenv("LOCAL_DEV", "false")  # check real ownership rules, not the local-dev shortcut
    other = make_user()
    assert client.patch(f"/api/bots/{bot}", json={"behaviour": {}}, headers=other.h()).status_code in (403, 404)


def test_asking_for_a_person_hands_over(client, make_user):
    u = make_user()
    bot = u.bot()
    r = client.post("/api/chat/message", json={"bot_id": bot, "message": "Can I talk to a person please?", "visitor_session_id": "s-h",
                                               "history": [], "is_demo": True}, headers=u.h())
    assert r.status_code == 200, r.text
    assert r.json().get("handoff_status") == "pending"


def test_only_a_request_for_a_person_hands_over(client, make_user, monkeypatch):
    """"agent" anywhere used to hand over, so NIMMI (selling an AI voice agent) passed most questions to the team."""
    from routers import chat
    for asked in ("Can I talk to a person please?", "I want to speak to someone", "connect me to an agent", "talk to agent",
                  "Can I chat with your team?", "real person please", "human", "Agent please!", "I need a human",
                  "customer care", "बात करनी है", "ஆள் வேண்டும்"):
        assert chat.asks_for_person(asked), asked
    for question in ("Which languages can your voice agent speak?", "I'm a travel agent, can I use this?", "Does it sound human?",
                     "Can it replace our customer care team?", "How does it talk to customers?", "AI agent pricing",
                     "Do you offer personal support?", "What does the human handover cost?"):
        assert not chat.asks_for_person(question), question
    u = make_user()
    bot = u.bot()
    monkeypatch.setattr(chat, "generate_ai_response", lambda *a, **k: "English, Hindi, Tamil and eight more.")
    monkeypatch.setattr(chat, "generate_ai_response_stream", lambda *a, **k: iter(["English, Hindi, Tamil and eight more."]))
    r = client.post("/api/chat/message", json={"bot_id": bot, "message": "Which languages can your voice agent speak?",
                                               "visitor_session_id": "s-agent", "history": [], "is_demo": True}, headers=u.h())
    assert r.status_code == 200, r.text
    assert r.json().get("handoff_status") != "pending"
