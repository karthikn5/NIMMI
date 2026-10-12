"""Team workspaces and roles, one-time lead alerts, analytics, and the Exotel stream protocol."""
import asyncio
import base64
import json

from sqlalchemy.future import select

from database import async_session
from backend.models import NotificationLog
from voice.transports import ExotelTransport


def test_team_roles_and_workspace_switching(client, make_user):
    owner = make_user("Agency Owner")
    bot = owner.bot("Client Desk")
    invited = client.post("/api/team/invite", json={"email": "agent.person@example.com", "role": "agent"}, headers=owner.h()).json()
    assert invited["status"] == "invited"

    # The invitee signs up with the invited email: the invite activates on sign-in.
    import auth
    auth._hits.clear()
    signup = client.post("/api/auth/signup", json={"email": "agent.person@example.com", "name": "Agent", "password": "password123"}).json()
    agent_headers = {"Authorization": f"Bearer {signup['token']}", "X-Workspace": owner.id}

    spaces = client.get("/api/team/workspaces", headers={"Authorization": f"Bearer {signup['token']}"}).json()
    assert [s["role"] for s in spaces] == ["owner", "agent"]

    assert [b["id"] for b in client.get("/api/bots", headers=agent_headers).json()] == [bot]
    assert client.post("/api/bots/create", json={"name": "x"}, headers=agent_headers).status_code == 403
    assert client.get("/api/handoffs/pending", headers=agent_headers).status_code == 200

    member_id = client.get("/api/team/members", headers=owner.h()).json()[0]["id"]
    client.patch(f"/api/team/members/{member_id}", json={"role": "admin"}, headers=owner.h())
    assert client.post("/api/bots/create", json={"name": "By admin"}, headers=agent_headers).status_code == 200

    stranger = make_user()
    assert client.get("/api/bots", headers=stranger.h(owner.id)).status_code == 403
    assert client.get("/api/team/members", headers=agent_headers).status_code == 403  # owners only


def test_lead_alert_fires_once(client, make_user, run):
    u = make_user()
    bot = u.bot()
    for value in ("98765 43210", "98765 43210"):
        r = client.post("/api/chat/variables", json={"bot_id": bot, "visitor_session_id": "lead-1",
                                                      "variable_name": "phone", "variable_value": value})
        assert r.status_code == 200

    async def logs():
        # The alert runs in the background: wait for it to finish rather than a fixed delay.
        for _ in range(50):
            await asyncio.sleep(0.1)
            async with async_session() as db:
                rows = (await db.execute(select(NotificationLog).where(NotificationLog.user_id == u.id))).scalars().all()
            if rows and all(r.status != "sending" for r in rows):
                return rows
        return rows

    rows = run(logs)
    assert [r.kind for r in rows] == ["lead_email"]
    assert rows[0].status == "skipped"  # no email provider configured in tests


def test_analytics_counts_real_data(client, make_user):
    u = make_user()
    bot = u.bot("Clinic")
    client.post("/api/chat/variables", json={"bot_id": bot, "visitor_session_id": "a1", "variable_name": "email", "variable_value": "a@b.co"})
    client.post("/api/chat/handoff", json={"bot_id": bot, "visitor_session_id": "a2"})
    data = client.get("/api/analytics?days=7", headers=u.h()).json()
    assert data["totals"]["conversations"] == 2 and data["totals"]["leads"] == 1 and data["totals"]["handoffs"] == 1
    assert len(data["by_day"]) == 7 and data["by_bot"][0]["bot_name"] == "Clinic"


class FakeWs:
    def __init__(self, incoming):
        self.incoming = [json.dumps(m) for m in incoming]
        self.sent = []

    async def receive_text(self):
        if not self.incoming:
            raise RuntimeError("closed")
        return self.incoming.pop(0)

    async def send_text(self, text):
        self.sent.append(json.loads(text))

    async def close(self):
        pass


def test_exotel_protocol(run):
    pcm = b"\x01\x02" * 400
    ws = FakeWs([
        {"event": "connected"},
        {"event": "start", "start": {"stream_sid": "MZ1", "call_sid": "CA1", "from": "09876543210", "to": "04445678120"}},
        {"event": "media", "media": {"payload": base64.b64encode(pcm).decode()}},
        {"event": "stop"},
    ])

    async def scenario():
        t = ExotelTransport(ws)
        assert await t.wait_for_start()
        got = await t.receive()
        end = await t.receive()
        await ExotelTransport.play(t, b"\x00" * 1000)  # gets padded to 320-byte multiples
        return t, got, end

    t, got, end = run(scenario)
    assert (t.stream_sid, t.call_sid, t.from_number) == ("MZ1", "CA1", "09876543210")
    assert got == pcm and end is None
    t.closed = False
    run(lambda: t.play(b"\x00" * 1000))
    sizes = [len(base64.b64decode(m["media"]["payload"])) for m in ws.sent if m["event"] == "media"]
    assert all(s % 320 == 0 for s in sizes)


def test_supabase_headers_follow_key_style():
    import supa
    assert supa.headers("sb_secret_abc") == {"apikey": "sb_secret_abc"}  # new keys: never as Bearer
    legacy = supa.headers("eyJhbGciOi.x.y", "audio/wav")
    assert legacy["Authorization"] == "Bearer eyJhbGciOi.x.y" and legacy["Content-Type"] == "audio/wav"
