"""Reply settings from the builder's Behaviour tab: stored, validated, and turned into prompt rules."""
import assist
import behaviour
from routers import chat as chat_router


def test_rules_only_apply_once_settings_are_saved():
    assert behaviour.rules(None) == ""
    assert behaviour.fallback(None) == "I'm sorry, I don't have that information."
    r = behaviour.rules({"reply_length": "short", "language": "ta", "ask_for_contact": True, "offer_human": False})
    assert "short" in r and "Tamil" in r and "phone number" in r and "Person" not in r


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
