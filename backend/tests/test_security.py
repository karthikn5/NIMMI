"""Auth, workspace isolation and the security fixes from the review."""
from routers import auth_routes


def test_signup_login_and_profile(client, make_user):
    u = make_user("Karthi")
    assert client.get("/api/auth/profile").status_code == 401
    assert client.get("/api/auth/profile", headers=u.h()).json()["email"] == u.email

    login = client.post("/api/auth/login", json={"email": u.email.upper(), "password": "password123"})
    assert login.status_code == 200 and login.json()["token"]
    assert client.post("/api/auth/login", json={"email": u.email, "password": "wrong-pass"}).status_code == 401


def test_bad_token_is_rejected(client):
    assert client.get("/api/bots", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_social_login_requires_proof(client, monkeypatch):
    # The old endpoint logged in anyone who posted an email. Now a Supabase token is required.
    assert client.post("/api/auth/social", json={"email": "victim@example.com"}).status_code == 422

    async def fake_supabase(token):
        if token != "good":
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="expired")
        return {"email": "google.user@example.com", "user_metadata": {"full_name": "Google User"}}

    monkeypatch.setattr(auth_routes, "_supabase_user", fake_supabase)
    assert client.post("/api/auth/social", json={"access_token": "bad"}).status_code == 401
    ok = client.post("/api/auth/social", json={"access_token": "good"})
    assert ok.status_code == 200 and ok.json()["email"] == "google.user@example.com"


def test_users_cannot_touch_each_others_bots(client, make_user):
    alice, bob = make_user(), make_user()
    bot = alice.bot("Alice Desk")

    assert [b["id"] for b in client.get("/api/bots", headers=bob.h()).json()] == []
    assert client.delete(f"/api/bots/{bot}", headers=bob.h()).status_code == 404
    assert client.get(f"/api/bots/{bot}/leads", headers=bob.h()).status_code == 404
    assert client.post(f"/api/bots/{bot}/config", json={"botName": "pwned"}, headers=bob.h()).status_code == 404
    assert client.delete(f"/api/bots/{bot}").status_code == 401
    assert client.get(f"/api/bots/{bot}/leads", headers=alice.h()).status_code == 200


def test_public_config_hides_private_fields(client, make_user):
    alice = make_user()
    bot = alice.bot()
    client.post(f"/api/bots/{bot}/config", json={"aiApiKey": "sk-secret-123", "systemPrompt": "internal"}, headers=alice.h())

    public = client.get(f"/api/bots/{bot}/config").json()
    assert "ai_api_key" not in public and "system_prompt" not in public

    own = client.get(f"/api/bots/{bot}/config", headers=alice.h()).json()
    assert own["has_ai_api_key"] is True and own["ai_api_key"] == ""  # never echoed back
    assert own["system_prompt"] == "internal"

    # Saving with an empty key keeps the stored one.
    client.post(f"/api/bots/{bot}/config", json={"aiApiKey": ""}, headers=alice.h())
    assert client.get(f"/api/bots/{bot}/config", headers=alice.h()).json()["has_ai_api_key"] is True


def test_demo_mode_needs_the_owner(client, make_user):
    alice = make_user()
    bot = alice.bot()
    body = {"bot_id": bot, "message": "hi", "visitor_session_id": "s1", "is_demo": True}
    # A stranger claiming demo mode doesn't skip the plan check.
    assert client.post("/api/chat/message", json=body).json().get("expired") is True


def test_live_chat_queue_is_scoped(client, make_user):
    alice, bob = make_user(), make_user()
    bot = alice.bot()
    client.post("/api/chat/handoff", json={"bot_id": bot, "visitor_session_id": "widget-session-human-1"})
    assert len(client.get("/api/handoffs/pending", headers=alice.h()).json()) == 1
    assert client.get("/api/handoffs/pending", headers=bob.h()).json() == []
    conv = client.get("/api/handoffs/pending", headers=alice.h()).json()[0]["conversation_id"]
    assert client.post(f"/api/handoffs/{conv}/accept", headers=bob.h()).status_code == 404
    assert client.post(f"/api/handoffs/{conv}/accept", headers=alice.h()).status_code == 200
    assert client.post(f"/api/handoffs/{conv}/close", headers=alice.h()).status_code == 200


def test_http_node_cannot_reach_internal_addresses(client):
    for url in ("http://127.0.0.1:8000/api/test", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd", "http://10.0.0.5/"):
        assert "error" in client.post("/api/chat/proxy-http", json={"url": url}).json(), url


def test_google_sheets_needs_a_configured_sheet(client, make_user):
    alice = make_user()
    bot = alice.bot()
    resp = client.post("/api/integrations/google-sheets", json={"bot_id": bot, "spreadsheet_id": "someone-elses", "data": {"a": 1}})
    assert resp.status_code == 403


def test_uploads_check_type_and_owner(client, make_user):
    alice, bob = make_user(), make_user()
    bot = alice.bot()
    files = {"file": ("x.exe", b"MZ...", "application/octet-stream")}
    assert client.post(f"/api/bots/{bot}/logo", files=files, headers=alice.h()).status_code == 400
    png = {"file": ("logo.png", b"\x89PNG\r\n", "image/png")}
    assert client.post(f"/api/bots/{bot}/logo", files=png, headers=bob.h()).status_code == 404
