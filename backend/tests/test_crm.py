"""HubSpot and Zoho CRM (mail plan, phase 9): leads and calls become records there, found by email or phone; email events become notes; Zoho's data centres; what's shown and kept."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import text, update
from sqlalchemy.future import select

from backend.models import Bot, CallLog, Conversation, IntegrationEvent, IntegrationSettings, NotificationLog
from database import async_session
from mail import outbox
from notify import channels, crm, events


class Crm:
    """HubSpot and Zoho, as far as Nimmi talks to them."""

    def __init__(self):
        self.calls, self.contacts, self.notes, self.leads, self.zoho_notes, self.revoked = [], {}, [], {}, [], []
        self.refused = None    # (status, text)
        self.token_answer = {"access_token": "zoho-access", "refresh_token": "zoho-refresh", "api_domain": "https://www.zohoapis.in", "expires_in": 3600}
        self.refreshes = 0
        self.record_status = "success"

    def __call__(self, r: httpx.Request) -> httpx.Response:
        path, host = r.url.path, r.url.host
        self.calls.append(f"{r.method} {host}{path}")
        if self.refused and "oauth" not in path:
            return httpx.Response(self.refused[0], text=self.refused[1])
        return self._hubspot(r, path) if host == "api.hubapi.com" else self._zoho(r, path)

    def _hubspot(self, r, path) -> httpx.Response:
        assert r.headers["authorization"] == "Bearer pat-secret"
        body = json.loads(r.content) if r.content else {}
        if path.endswith("/contacts/batch/upsert"):
            one = body["inputs"][0]
            assert one["idProperty"] == "email"
            self.contacts.setdefault(one["id"], {}).update(one["properties"])
            return httpx.Response(200, json={"results": [{"id": f"hs-{one['id']}"}]})
        if path.endswith("/contacts/search"):
            wanted = body["filterGroups"][0]["filters"][0]["value"]
            found = [{"id": f"hs-{k}"} for k, v in self.contacts.items() if v.get("phone") == wanted]
            return httpx.Response(200, json={"results": found})
        if path.endswith("/objects/contacts"):
            key = body["properties"]["phone"]
            self.contacts[key] = body["properties"]
            return httpx.Response(201, json={"id": f"hs-{key}"})
        if "/objects/contacts/" in path:
            key = path.rsplit("hs-", 1)[1]
            self.contacts[key].update(body["properties"])
            return httpx.Response(200, json={"id": f"hs-{key}"})
        if path.endswith("/objects/notes"):
            self.notes.append(body)
            return httpx.Response(201, json={"id": "note-1"})
        return httpx.Response(404, text=path)

    def _zoho(self, r, path) -> httpx.Response:
        if path.endswith("/oauth/v2/token/revoke"):
            self.revoked.append(r.url.params.get("token"))
            return httpx.Response(200, json={})
        if path.endswith("/oauth/v2/token"):
            form = {k: v[0] for k, v in parse_qs(r.content.decode()).items()}
            if form["grant_type"] == "refresh_token":
                self.refreshes += 1
                return httpx.Response(200, json={"access_token": f"zoho-access-{self.refreshes}", "expires_in": 3600})
            return httpx.Response(200, json=self.token_answer)
        assert r.url.host == "www.zohoapis.in", "the account's own data centre"
        assert r.headers["authorization"].startswith("Zoho-oauthtoken zoho-access")
        if path.endswith("/Leads/upsert"):
            body = json.loads(r.content)
            record = body["data"][0]
            assert body["duplicate_check_fields"] == ["Email", "Phone"]
            key = record.get("Email") or record.get("Phone")
            self.leads.setdefault(key, {}).update(record)
            return httpx.Response(200, json={"data": [{"code": "SUCCESS", "status": self.record_status, "message": "no", "details": {"id": f"z-{key}"}}]})
        if path.endswith("/Leads/search"):
            address = r.url.params.get("email")
            return httpx.Response(200, json={"data": [{"id": f"z-{address}"}]}) if address in self.leads else httpx.Response(204)
        if path.endswith("/Notes"):
            self.zoho_notes.append({"lead": path.split("/")[-2], **json.loads(r.content)["data"][0]})
            return httpx.Response(201, json={"data": [{"code": "SUCCESS", "status": "success"}]})
        return httpx.Response(404, text=path)


@pytest.fixture
def fake(monkeypatch):
    service = Crm()
    monkeypatch.setenv("ZOHO_CLIENT_ID", "zoho-id")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "zoho-secret")
    monkeypatch.delenv("CRM_API_URL", raising=False)
    monkeypatch.setattr(crm, "client", lambda timeout=15: httpx.AsyncClient(transport=httpx.MockTransport(service)))
    return service


def base(client, u) -> dict:
    return {k: v for k, v in client.get("/api/integrations", headers=u.h()).json().items() if k in ("alert_email", "reply_to", "sender_name")}


def hubspot_on(client, u, token="pat-secret"):
    return client.put("/api/integrations", json={**base(client, u), "hubspot_enabled": True, "hubspot_token": token}, headers=u.h())


def zoho_on(client, u, server="https://accounts.zoho.in"):
    url = client.post("/api/integrations/zoho/start", headers=u.h()).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    return client.post("/api/integrations/zoho/finish", json={"code": "good", "state": state, "accounts_server": server}, headers=u.h())


def event(run, u, name="email.replied", **data):
    async def go():
        async with async_session() as db:
            await outbox.emit(db, u.id, name, {"to": "asha@example.com", "lead": "asha@example.com", "subject": "About your home", "at": datetime.now(timezone.utc).isoformat(), **data})
            await db.commit()
    run(go)


def rows_of(run, u):
    async def go():
        async with async_session() as db:
            return (await db.execute(select(IntegrationEvent).where(IntegrationEvent.user_id == u.id))).scalars().all()
    return run(go)


# ─── HubSpot ─────────────────────────────────────────────────────
def test_hubspot_needs_a_token_and_never_shows_it(client, make_user, fake, run):
    u = make_user()
    assert client.put("/api/integrations", json={**base(client, u), "hubspot_enabled": True}, headers=u.h()).status_code == 400
    saved = hubspot_on(client, u).json()
    assert saved["hubspot_enabled"] and saved["hubspot_has_token"] and "pat-secret" not in json.dumps(saved)
    async def raw():
        async with async_session() as db:
            return (await db.execute(text("select hubspot_token from integration_settings where user_id = :u"), {"u": u.id})).scalar_one()
    assert "pat-secret" not in run(raw)


def test_an_older_dashboard_saving_leaves_hubspot_as_it_is(client, make_user, fake):
    u = make_user()
    hubspot_on(client, u)
    assert client.put("/api/integrations", json=base(client, u), headers=u.h()).json()["hubspot_enabled"] is True


def test_a_lead_with_an_email_is_upserted_and_what_they_said_is_a_note(fake, run):
    run(crm.hubspot_lead, "pat-secret", {"name": "Asha Rao", "email": "asha@example.com", "phone": "+919876500001", "summary": "Budget: 45 lakh"})
    assert fake.contacts["asha@example.com"] == {"firstname": "Asha", "lastname": "Rao", "phone": "+919876500001", "email": "asha@example.com"}
    note = fake.notes[0]
    assert note["properties"]["hs_note_body"] == "Budget: 45 lakh" and note["associations"][0]["to"]["id"] == "hs-asha@example.com"
    assert note["associations"][0]["types"] == [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]


def test_a_lead_with_only_a_phone_is_found_by_it_not_made_twice(fake, run):
    run(crm.hubspot_lead, "pat-secret", {"name": "Ravi", "phone": "+919876500002"})
    run(crm.hubspot_lead, "pat-secret", {"name": "Ravi Kumar", "phone": "+919876500002"})
    assert list(fake.contacts) == ["+919876500002"] and fake.contacts["+919876500002"]["lastname"] == "Kumar"
    assert fake.calls.count("POST api.hubapi.com/crm/v3/objects/contacts") == 1, "made once, then found"


def test_nothing_to_find_them_by_is_an_error_not_a_blank_contact(fake, run):
    with pytest.raises(channels.ChannelError):
        run(crm.hubspot_lead, "pat-secret", {"name": "Nobody"})
    with pytest.raises(channels.ChannelError):
        run(crm.zoho_lead, "x", {"name": "Nobody"})
    assert fake.contacts == {}


def test_hubspot_refusing_says_to_connect_it_again(fake, run):
    fake.refused = (401, "expired")
    with pytest.raises(channels.ChannelError, match="connect it again"):
        run(crm.hubspot_lead, "pat-secret", {"email": "asha@example.com"})


def test_a_new_chat_lead_reaches_hubspot_once(client, make_user, fake, run, monkeypatch):
    u = make_user()
    bot = u.bot("Sunrise")
    hubspot_on(client, u)
    async def lead():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id=f"s-{uuid.uuid4().hex}", captured_data={"Name": "Asha Rao", "Email": "asha@example.com", "Wants": "A 2BHK"})
            db.add(conv)
            await db.commit()
            return conv.conversation_id
    conversation = run(lead)
    run(events.lead_captured, conversation)
    run(events.lead_captured, conversation)
    assert "asha@example.com" in fake.contacts and len(fake.notes) == 1 and "2BHK" in fake.notes[0]["properties"]["hs_note_body"]


def test_email_events_become_notes_on_the_contact_with_retries(client, make_user, fake, run):
    u = make_user()
    hubspot_on(client, u)
    event(run, u, detail="Is parking included?")
    event(run, u, "email.sent")  # too many: not sent to CRMs
    rows = rows_of(run, u)
    assert [r.target for r in rows] == ["hubspot"]
    fake.refused = (500, "down")
    run(outbox._one, rows[0].id, datetime.utcnow())
    row = rows_of(run, u)[0]
    assert row.status == "new" and row.attempts == 1 and "500" in row.error
    fake.refused = None
    run(outbox._one, rows[0].id, datetime.utcnow())
    assert rows_of(run, u)[0].status == "sent"
    assert "Replied to an email" in fake.notes[-1]["properties"]["hs_note_body"] and "Is parking included?" in fake.notes[-1]["properties"]["hs_note_body"]


def test_the_plan_decides_whether_events_are_kept_for_a_crm(client, make_user, fake, run, monkeypatch):
    u = make_user()
    hubspot_on(client, u)
    import plans
    monkeypatch.setattr(plans, "ENFORCED", True, raising=False)
    async def no_integrations(db, owner_id):
        return plans.includes_of(None)
    monkeypatch.setattr(plans, "workspace_includes", no_integrations)
    event(run, u)
    assert rows_of(run, u) == []


# ─── Zoho ────────────────────────────────────────────────────────
def test_zoho_isnt_offered_until_nimmi_has_a_client(client, make_user, monkeypatch):
    monkeypatch.delenv("ZOHO_CLIENT_ID", raising=False)
    u = make_user()
    assert client.get("/api/integrations", headers=u.h()).json()["zoho"]["available"] is False
    assert client.post("/api/integrations/zoho/start", headers=u.h()).status_code == 409


def test_connecting_zoho_stays_on_its_own_data_centre_and_keeps_tokens_sealed(client, make_user, fake, run):
    u = make_user()
    url = client.post("/api/integrations/zoho/start", headers=u.h()).json()["url"]
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://accounts.zoho.com/oauth/v2/auth") and q["access_type"] == ["offline"] and q["prompt"] == ["consent"] and q["redirect_uri"][0].endswith("/dashboard/integrations")
    assert "ZohoCRM.modules.leads.ALL" in q["scope"][0] and "settings" not in q["scope"][0]
    assert zoho_on(client, u).status_code == 200
    assert any(c.startswith("POST accounts.zoho.in/oauth/v2/token") for c in fake.calls)
    state = client.get("/api/integrations", headers=u.h()).json()
    assert state["zoho"] == {"available": True, "connected": True, "enabled": True, "data_centre": "https://accounts.zoho.in"}
    assert "zoho-refresh" not in json.dumps(state)
    async def raw():
        async with async_session() as db:
            return (await db.execute(text("select zoho_refresh_token, zoho_access_token from integration_settings where user_id = :u"), {"u": u.id})).one()
    assert all("zoho-" not in value for value in run(raw))


def test_only_zohos_own_servers_are_believed(client, make_user, fake):
    u = make_user()
    for server in ("https://evil.example.com", "https://accounts.zoho.in.evil.com", "http://accounts.zoho.in", "https://accounts.zoho.in/../evil"):
        assert zoho_on(client, u, server).status_code == 400, server
    fake.token_answer = {**fake.token_answer, "api_domain": "https://evil.example.com"}
    assert zoho_on(client, u).status_code == 400
    assert client.get("/api/integrations", headers=u.h()).json()["zoho"]["connected"] is False


def test_a_zoho_link_someone_else_started_doesnt_work(client, make_user, fake):
    u, other = make_user(), make_user()
    url = client.post("/api/integrations/zoho/start", headers=u.h()).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    answer = client.post("/api/integrations/zoho/finish", json={"code": "good", "state": state, "accounts_server": "https://accounts.zoho.in"}, headers=other.h())
    assert answer.status_code == 403 and client.get("/api/integrations", headers=other.h()).json()["zoho"]["connected"] is False


def test_a_lead_is_upserted_by_email_then_phone(client, make_user, fake, run):
    u = make_user()
    zoho_on(client, u)
    run(crm.zoho_lead, u.id, {"name": "Asha Rao", "email": "asha@example.com", "phone": "+919876500001", "summary": "Budget: 45 lakh"})
    assert fake.leads["asha@example.com"] == {"Last_Name": "Rao", "First_Name": "Asha", "Email": "asha@example.com", "Phone": "+919876500001", "Description": "Budget: 45 lakh"}
    run(crm.zoho_lead, u.id, {"name": "Ravi", "phone": "+919876500002"})
    assert fake.leads["+919876500002"]["Last_Name"] == "Ravi", "Zoho needs a last name"


def test_a_record_zoho_refuses_is_an_error(client, make_user, fake, run):
    u = make_user()
    zoho_on(client, u)
    fake.record_status = "error"
    with pytest.raises(channels.ChannelError, match="Zoho CRM"):
        run(crm.zoho_lead, u.id, {"email": "asha@example.com"})


def test_the_access_token_is_kept_for_its_hour_then_renewed(client, make_user, fake, run):
    u = make_user()
    zoho_on(client, u)
    run(crm.zoho_lead, u.id, {"email": "a@example.com"})
    assert fake.refreshes == 0
    async def expire():
        async with async_session() as db:
            await db.execute(update(IntegrationSettings).where(IntegrationSettings.user_id == u.id).values(zoho_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
            await db.commit()
    run(expire)
    run(crm.zoho_lead, u.id, {"email": "b@example.com"})
    run(crm.zoho_lead, u.id, {"email": "c@example.com"})
    assert fake.refreshes == 1, "Zoho limits how often a refresh token is used"


def test_email_events_become_notes_on_the_lead_making_it_if_needed(client, make_user, fake, run):
    u = make_user()
    zoho_on(client, u)
    event(run, u, name="email.clicked", link="https://example.com/prices")
    rows = rows_of(run, u)
    assert [r.target for r in rows] == ["zoho"]
    run(outbox._one, rows[0].id, datetime.utcnow())
    assert rows_of(run, u)[0].status == "sent", rows_of(run, u)[0].error
    assert fake.leads["asha@example.com"]["Last_Name"] == "asha@example.com"
    note = fake.zoho_notes[0]
    assert note["lead"] == "z-asha@example.com" and note["Note_Title"] == "Clicked a link in an email" and "prices" in note["Note_Content"]


def test_disconnecting_zoho_forgets_it_and_takes_the_permission_back(client, make_user, fake, run):
    u = make_user()
    zoho_on(client, u)
    assert client.delete("/api/integrations/zoho", headers=u.h()).status_code == 200
    assert fake.revoked == ["zoho-refresh"] and client.get("/api/integrations", headers=u.h()).json()["zoho"]["connected"] is False
    event(run, u)
    assert rows_of(run, u) == []
    with pytest.raises(channels.ChannelError, match="isn't connected"):
        run(crm.zoho_lead, u.id, {"email": "a@example.com"})


def test_a_test_lead_goes_to_each(client, make_user, fake):
    u = make_user()
    hubspot_on(client, u)
    zoho_on(client, u)
    assert client.post("/api/integrations/test", json={"channel": "hubspot"}, headers=u.h()).status_code == 200
    assert client.post("/api/integrations/test", json={"channel": "zoho"}, headers=u.h()).status_code == 200
    assert fake.contacts and fake.leads
