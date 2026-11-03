"""
Facebook and Instagram lead ads, connected directly (instagram_plan.md, phase 3), against a fake Graph API shaped like Meta's own documents: connecting, a Page in
one workspace only, forms routed to an assistant, the webhook signed and kept before it's answered, each lead once however Meta repeats, reorders or batches it,
nothing lost when a process stops, Meta is busy or a sign-in ends, the catch-up finding what the webhook missed, every answer kept, nobody contacted by a form
until its switches say so, past leads brought in quietly, Meta's deletion and removal callbacks, and no token or secret in an address or a log.
"""
import base64
import hashlib
import hmac
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.future import select

from backend.models import CallbackJob, Contact, EmailJob, LeadEvent, LeadIntake, LeadTask, MetaConnection, MetaEvent, MetaForm, MetaPage
from database import async_session
from meta_leads import core, graph
from notify import email
from tests.test_leads import joined  # noqa: F401  (a fixture)

SECRET = "meta-app-secret"


def big() -> str:
    """Meta's ids are long digits: some don't fit in a JavaScript number."""
    return str(10 ** 17 + uuid.uuid4().int % 10 ** 17)


class FakeGraph:
    """Graph v26.0 as Meta's documents show it: ids as numbers in webhooks and strings in answers, a lead's answers in field_data, tick boxes apart."""

    def __init__(self):
        self.page, self.form, self.other_form, self.me = big(), big(), big(), big()
        self.pages = {self.page: {"name": "Sunrise Homes", "token": f"PAGE-TOKEN-{self.page}", "tasks": ["ADVERTISE", "MANAGE"]}}
        self.forms = {self.page: [{"id": self.form, "name": "Site visit form", "status": "ACTIVE"}, {"id": self.other_form, "name": "Brochure form", "status": "ACTIVE"}]}
        self.leads: dict = {}
        self.order: list = []
        self.subscribed: set = set()
        self.granted = list(graph.SCOPES)
        self.fail: list = []       # (path pattern, status, error): each used once
        self.calls: list = []
        self.page_size = 100

    def lead(self, form_id=None, created=None, platform="ig", **answers) -> str:
        lid = big()
        at = created or datetime.now(timezone.utc)
        self.leads[lid] = {"id": lid, "created_time": at.strftime("%Y-%m-%dT%H:%M:%S+0000"), "form_id": form_id or self.form, "ad_id": "120330000000000001",
                           "ad_name": "2BHK carousel", "adset_id": "120330000000000002", "adset_name": "Chennai 25-45", "campaign_id": "120330000000000003",
                           "campaign_name": "Diwali offer", "platform": platform, "is_organic": False,
                           "field_data": [{"name": k, "values": v if isinstance(v, list) else [v]} for k, v in (answers or {"full_name": "Divya Menon", "phone_number": "+919876500311",
                                                                                                                              "email": "divya@buyers.in"}).items()],
                           "custom_disclaimer_responses": [{"checkbox_key": "optional_1", "is_checked": "1"}, {"checkbox_key": "optional_2", "is_checked": ""}]}
        self.order.append(lid)
        return lid

    def _json(self, status, body):
        return httpx.Response(status, json=body)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.split(f"/{graph.VERSION}/", 1)[1]
        params = dict(request.url.params)
        self.calls.append((request.method, path, params, request.headers.get("authorization")))
        for i, (pattern, status, error) in enumerate(self.fail):
            if re.fullmatch(pattern, path):
                self.fail.pop(i)
                return self._json(status, {"error": error})
        if path == "oauth/access_token":
            if params.get("grant_type") == "fb_exchange_token":
                return self._json(200, {"access_token": "LONG-USER-TOKEN", "token_type": "bearer", "expires_in": 5183944})
            return self._json(200, {"access_token": "SHORT-USER-TOKEN", "token_type": "bearer"} if params.get("code") else {"error": {"code": 100, "message": "No code"}})
        if path == "me":
            return self._json(200, {"id": self.me, "name": "Karthik"})
        if path == "me/permissions":
            return self._json(200, {"data": [{"permission": p, "status": "granted"} for p in self.granted]})
        if path == "me/accounts":
            return self._json(200, {"data": [{"id": k, "name": v["name"], "access_token": v["token"], "tasks": v["tasks"]} for k, v in self.pages.items()]})
        if m := re.fullmatch(r"(\d+)/subscribed_apps", path):
            if request.method == "POST":
                self.subscribed.add(m.group(1))
                return self._json(200, {"success": True})
            if request.method == "DELETE":
                self.subscribed.discard(m.group(1))
                return self._json(200, {"success": True})
            return self._json(200, {"data": [{"id": "777", "subscribed_fields": ["leadgen"]}] if m.group(1) in self.subscribed else []})
        if m := re.fullmatch(r"(\d+)/leadgen_forms", path):
            return self._json(200, {"data": self.forms.get(m.group(1), [])})
        if m := re.fullmatch(r"(\d+)/leads", path):
            since = json.loads(params.get("filtering") or "[]")
            after_time = next((f["value"] for f in since if f["field"] == "time_created" and f["operator"] == "GREATER_THAN"), 0)
            rows = [self.leads[i] for i in reversed(self.order) if self.leads[i]["form_id"] == m.group(1)
                    and datetime.strptime(self.leads[i]["created_time"], "%Y-%m-%dT%H:%M:%S%z").timestamp() > after_time]
            start = int(params.get("after") or 0)
            page = rows[start:start + self.page_size]
            paging = {"cursors": {"before": "0", "after": str(start + self.page_size)}}
            if start + self.page_size < len(rows):
                paging["next"] = "https://graph.facebook.com/next"
            return self._json(200, {"data": page, "paging": paging})
        if m := re.fullmatch(r"(\d+)", path):
            found = self.leads.get(m.group(1))
            return self._json(200, found) if found else self._json(400, {"error": {"code": 100, "error_subcode": 33, "message": "Object does not exist"}})
        return self._json(404, {"error": {"code": 803, "message": f"Unknown path {path}"}})


@pytest.fixture
def meta(monkeypatch):
    fake = FakeGraph()
    for name, value in (("META_APP_ID", "777"), ("META_APP_SECRET", SECRET), ("META_LOGIN_CONFIG_ID", "config-1"), ("META_LEADS_VERIFY_TOKEN", "verify-me")):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(graph, "client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler), timeout=5))
    monkeypatch.setattr(core, "_last_pass", None)
    monkeypatch.setattr(core, "_last_catch_up", None)
    return fake


@pytest.fixture
def sent(monkeypatch):
    """Email on, and kept here: nothing reaches a real provider."""
    out = []

    async def deliver(to, subject, text, html_body=None, **more):
        out.append({"to": to, "subject": subject})
        return email.Delivery(True, id=f"re_{len(out)}")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setattr(email, "is_configured", lambda: True)
    monkeypatch.setattr(email, "deliver", deliver)
    return out


BASE = {"email_alerts": True, "alert_email": "alerts@sunrise.in", "whatsapp_enabled": False, "whatsapp_template": "", "whatsapp_language": "en",
        "webhook_url": "", "leadsquared_enabled": False, "leadsquared_host": "", "leadsquared_access_key": "", "reply_to": "team@sunrise.in"}


def start(client, user) -> str:
    url = client.post("/api/meta/connect", headers=user.h()).json()["url"]
    return parse_qs(urlparse(url).query)["state"][0]


@pytest.fixture
def business(client, make_user, meta, run):
    def make(route=True):
        u = make_user()
        u.bot_id = u.bot("Sunrise")
        assert client.put("/api/integrations", json=BASE, headers=u.h()).status_code == 200
        r = client.post("/api/meta/connect/finish", json={"code": "CODE-1", "state": start(client, u)}, headers=u.h())
        assert r.status_code == 200, r.text
        assert client.post(f"/api/meta/pages/{meta.page}/subscribe", headers=u.h()).status_code == 200
        if route:
            assert client.put(f"/api/meta/forms/{meta.form}", json={"bot_id": u.bot_id}, headers=u.h()).status_code == 200
        run(_settled)  # routing starts a pass in the background: done before the test makes its leads
        return u
    return make


def signature(raw: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def webhook(client, *changes, secret=SECRET, page=None):
    """Meta's leadgen webhook: ids as numbers, as in its own sample."""
    body = {"object": "page", "entry": [{"id": int(page or changes[0][0]), "time": 1761945743, "changes": [
        {"field": "leadgen", "value": {"leadgen_id": int(lid), "page_id": int(pid), "form_id": int(fid), "adgroup_id": 12312312312, "ad_id": 12312312312, "created_time": 1761945743}}
        for pid, fid, lid in changes]}]}
    raw = json.dumps(body).encode()
    return client.post("/api/meta/webhook", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature(raw, secret)})


async def _settled():
    import asyncio
    import notify.events as ev
    while ev._background:
        await asyncio.gather(*list(ev._background), return_exceptions=True)


async def _all(model, **where):
    async with async_session() as db:
        q = select(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return (await db.execute(q)).scalars().all()


def alerts(sent):
    return [s for s in sent if s["subject"].startswith("New lead")]


# ─── connecting ──────────────────────────────────────────────────
def test_connecting_asks_facebook_for_the_lead_ads_permissions(client, make_user, meta):
    u = make_user()
    url = client.post("/api/meta/connect", headers=u.h()).json()["url"]
    query = parse_qs(urlparse(url).query)
    assert url.startswith(f"https://www.facebook.com/{graph.VERSION}/dialog/oauth?") and query["client_id"] == ["777"] and query["config_id"] == ["config-1"]
    assert query["redirect_uri"][0].endswith("/dashboard/leads/sources") and query["response_type"] == ["code"]


def test_only_who_started_it_can_finish_it(client, make_user, meta, joined):
    u, stranger = make_user(), make_user("Stranger")
    state = start(client, u)
    assert client.post("/api/meta/connect/finish", json={"code": "CODE", "state": state}, headers=stranger.h()).status_code == 403
    assert client.post("/api/meta/connect/finish", json={"code": "CODE", "state": "forged"}, headers=u.h()).status_code == 403
    seller = joined(u)
    assert client.post("/api/meta/connect", headers=seller.h(u.id)).status_code == 403          # managers connect


def test_a_connection_keeps_its_tokens_sealed_and_never_in_an_address(client, business, meta, run, caplog):
    caplog.set_level(logging.INFO, logger="httpx")
    u = business()
    [conn] = run(_all, MetaConnection, user_id=u.id)
    [page] = run(_all, MetaPage, user_id=u.id)
    assert (conn.name, conn.status, page.name, page.subscribed) == ("Karthik", "active", "Sunrise Homes", True)

    async def raw():
        from sqlalchemy import text
        async with async_session() as db:
            return (await db.execute(text("select token from meta_connections where id = :i"), {"i": conn.id})).scalar_one()
    assert run(raw).startswith("enc:v1:") and "LONG-USER-TOKEN" not in run(raw)               # sealed at rest
    assert all("access_token" not in params for _m, path, params, _a in meta.calls if path != "oauth/access_token")
    assert any(a == f"Bearer PAGE-TOKEN-{meta.page}" for *_x, a in meta.calls)                    # a Page's own token, in a header
    assert "meta-app-secret" not in caplog.text and "SHORT-USER-TOKEN" not in caplog.text and "CODE-1" not in caplog.text


def test_a_page_belongs_to_one_workspace(client, business, make_user, meta):
    business()
    other = make_user("Other business")
    r = client.post("/api/meta/connect/finish", json={"code": "CODE-2", "state": start(client, other)}, headers=other.h())
    assert r.status_code == 200 and r.json()["taken"] == ["Sunrise Homes"] and r.json()["pages"] == 0
    assert client.get("/api/meta", headers=other.h()).json()["pages"] == []
    assert client.post(f"/api/meta/pages/{meta.page}/subscribe", headers=other.h()).status_code == 404


def test_missing_permissions_are_named(client, make_user, meta, run):
    meta.granted = ["pages_show_list", "pages_manage_metadata"]
    u = make_user()
    r = client.post("/api/meta/connect/finish", json={"code": "C", "state": start(client, u)}, headers=u.h()).json()
    assert "leads_retrieval" in r["missing"]
    shown = client.get("/api/meta", headers=u.h()).json()["connections"][0]
    assert shown["status"] == "missing_permission" and "leads_retrieval" in shown["error"]


def test_forms_are_listed_and_wait_for_an_assistant(client, business, meta, run):
    u = business(route=False)
    forms = {f["form_id"]: f for f in client.get("/api/meta", headers=u.h()).json()["pages"][0]["forms"]}
    assert set(forms) == {meta.form, meta.other_form} and forms[meta.form]["bot_id"] is None and forms[meta.form]["settings"] == {"email": False, "call": False, "whatsapp_tick": None}
    lead = meta.lead()
    assert webhook(client, (meta.page, meta.form, lead)).status_code == 200
    run(_settled)
    assert [e.status for e in run(_all, MetaEvent, leadgen_id=lead)] == ["waiting"]               # kept, and waiting: nothing lost
    assert client.get("/api/meta", headers=u.h()).json()["pages"][0]["forms"][0]["waiting"] in ({"waiting": 1}, {})
    assert client.put(f"/api/meta/forms/{meta.form}", json={"bot_id": u.bot_id}, headers=u.h()).status_code == 200
    run(core.tick, datetime.utcnow() + timedelta(minutes=1))
    run(_settled)
    assert [c.name for c in run(_all, Contact, bot_id=u.bot_id)] == ["Divya Menon"]


def test_a_form_goes_only_to_your_own_assistant(client, business, make_user, meta):
    u = business(route=False)
    stranger = make_user("Stranger")
    theirs = stranger.bot("Theirs")
    assert client.put(f"/api/meta/forms/{meta.form}", json={"bot_id": theirs}, headers=u.h()).status_code == 404
    assert client.put(f"/api/meta/forms/{meta.form}", json={"bot_id": u.bot_id}, headers=stranger.h()).status_code == 404


# ─── the webhook ─────────────────────────────────────────────────
def test_meta_checks_the_address_with_the_verify_token(client, meta):
    ok = client.get("/api/meta/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "1158201444"})
    assert ok.status_code == 200 and ok.text == "1158201444"
    assert client.get("/api/meta/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"}).status_code == 403


def test_a_lead_comes_in_with_its_ad_and_every_answer(client, business, meta, run, sent):
    u = business()
    lead = meta.lead(full_name="Divya Menon", phone_number="+919876500311", email="divya@buyers.in", city="Chennai",
                     **{"which_project_interests_you?": "Sunrise Towers", "preferred_bedrooms": ["2BHK", "3BHK"]})
    r = webhook(client, (meta.page, meta.form, lead))
    assert r.status_code == 200 and r.json() == {"status": "received"}
    run(_settled)
    [c] = run(_all, Contact, bot_id=u.bot_id)
    assert (c.name, c.e164, c.email, c.source) == ("Divya Menon", "+919876500311", "divya@buyers.in", "Instagram lead ads")
    assert c.details["Place"] == "Chennai" and "Which project interests you?: Sunrise Towers" in c.details["Wants"] and "Preferred bedrooms: 2BHK, 3BHK" in c.details["Wants"]
    assert c.origin == {"channel": "meta_ads", "campaign_id": "120330000000000003", "campaign_name": "Diwali offer", "adset_id": "120330000000000002",
                        "adset_name": "Chennai 25-45", "ad_id": "120330000000000001", "ad_name": "2BHK carousel", "form_id": meta.form, "form_name": "Site visit form", "platform": "ig"}
    [row] = run(_all, LeadIntake, bot_id=u.bot_id)
    assert row.channel == "meta" and row.consents == [{"id": "optional_1", "agreed": True}, {"id": "optional_2", "agreed": False}]
    assert [a["subject"] for a in alerts(sent)] == ["New lead from Instagram lead ads (Sunrise)"]
    assert len(run(_all, LeadTask, contact_id=c.id)) == 1                                       # a first step for the team
    [event] = run(_all, MetaEvent, leadgen_id=lead)
    assert (event.status, event.intake_id) == ("done", row.id)


def test_a_forged_or_unsigned_webhook_is_refused_and_keeps_nothing(client, business, meta, run):
    business()
    lead = meta.lead()
    assert webhook(client, (meta.page, meta.form, lead), secret="not-the-secret").status_code == 403
    raw = json.dumps({"object": "page", "entry": []}).encode()
    assert client.post("/api/meta/webhook", content=raw, headers={"Content-Type": "application/json"}).status_code == 403
    run(_settled)
    assert run(_all, MetaEvent, leadgen_id=lead) == []


def test_a_page_nobody_connected_is_left_alone(client, business, meta, run):
    business()
    stranger_page, lead = big(), big()
    assert webhook(client, (stranger_page, big(), lead)).status_code == 200                      # Meta hears 200: it would only retry
    run(_settled)
    assert run(_all, MetaEvent, leadgen_id=lead) == []


def test_repeated_reordered_and_batched_webhooks_give_one_lead_each(client, business, meta, run, sent):
    u = business()
    first, second = meta.lead(full_name="Asha", phone_number="+919876500312"), meta.lead(full_name="Ravi", phone_number="+919876500313")
    assert webhook(client, (meta.page, meta.form, second), (meta.page, meta.form, first), (meta.page, meta.form, second)).status_code == 200
    assert webhook(client, (meta.page, meta.form, first)).status_code == 200                     # Meta's retry
    run(_settled)
    assert sorted(c.name for c in run(_all, Contact, bot_id=u.bot_id)) == ["Asha", "Ravi"]
    assert len(run(_all, LeadIntake, bot_id=u.bot_id)) == 2 and len(alerts(sent)) == 2


def test_a_process_that_stops_after_keeping_loses_nothing(client, business, meta, run, monkeypatch):
    u = business()
    lead = meta.lead()
    real = core.process

    async def stopped(event_id, at=None):
        return None                                                                              # the process went down before fetching
    monkeypatch.setattr(core, "process", stopped)
    assert webhook(client, (meta.page, meta.form, lead)).status_code == 200
    run(_settled)
    assert [e.status for e in run(_all, MetaEvent, leadgen_id=lead)] == ["new"]
    assert run(_all, Contact, bot_id=u.bot_id) == []                                             # a 200 to Meta isn't a lead in Leads
    monkeypatch.setattr(core, "process", real)
    core._last_pass, core._last_catch_up = None, datetime.utcnow()
    run(core.tick, datetime.utcnow() + timedelta(minutes=1))
    run(_settled)
    assert [c.name for c in run(_all, Contact, bot_id=u.bot_id)] == ["Divya Menon"]


def test_a_busy_meta_is_tried_again_later(client, business, meta, run):
    u = business()
    lead = meta.lead()
    meta.fail.append((lead, 500, {"code": 1, "message": "An unknown error occurred", "is_transient": True}))
    webhook(client, (meta.page, meta.form, lead))
    run(_settled)
    [event] = run(_all, MetaEvent, leadgen_id=lead)
    assert event.status == "new" and event.retry_at is not None and event.attempts == 1 and run(_all, Contact, bot_id=u.bot_id) == []
    run(core.tick, datetime.utcnow() + timedelta(minutes=2))
    run(_settled)
    assert [c.name for c in run(_all, Contact, bot_id=u.bot_id)] == ["Divya Menon"]


def test_tries_stop_after_a_few(client, business, meta, run):
    business()
    lead = meta.lead()
    meta.fail += [(lead, 503, {"code": 2, "message": "Service temporarily unavailable"})] * core.TRIES
    webhook(client, (meta.page, meta.form, lead))
    run(_settled)
    for n in range(1, core.TRIES):
        core._last_pass = None
        run(core.tick, datetime.utcnow() + timedelta(minutes=sum(core.BACKOFF[:n]) + 1))
        run(_settled)
    assert [e.status for e in run(_all, MetaEvent, leadgen_id=lead)] == ["failed"]


def test_an_ended_sign_in_shows_its_repair_and_nothing_is_lost(client, business, meta, run):
    u = business()
    lead = meta.lead()
    meta.fail.append((lead, 400, {"code": 190, "error_subcode": 463, "type": "OAuthException", "message": "Error validating access token: Session has expired"}))
    webhook(client, (meta.page, meta.form, lead))
    run(_settled)
    page = client.get("/api/meta", headers=u.h()).json()["pages"][0]
    assert page["status"] == "token" and "Connect again" in page["error"]
    assert [e.status for e in run(_all, MetaEvent, leadgen_id=lead)] == ["new"]
    assert client.post("/api/meta/connect/finish", json={"code": "CODE-3", "state": start(client, u)}, headers=u.h()).status_code == 200   # they connect again
    assert client.get("/api/meta", headers=u.h()).json()["pages"][0]["status"] == "active"
    core._last_pass = None
    run(core.tick, datetime.utcnow() + timedelta(minutes=1))
    run(_settled)
    assert [c.name for c in run(_all, Contact, bot_id=u.bot_id)] == ["Divya Menon"]


def test_a_missing_phone_and_odd_answers_still_make_a_lead(client, business, meta, run):
    u = business()
    lead = meta.lead(platform="fb", **{"full_name": "Mala", "email": "mala@buyers.in", "how_soon?": [], "budget": "60 lakh", "unknown_field": "kept"})
    webhook(client, (meta.page, meta.form, lead))
    run(_settled)
    [c] = run(_all, Contact, bot_id=u.bot_id)
    assert (c.name, c.e164, c.source, c.details["Budget"]) == ("Mala", None, "Facebook lead ads", "60 lakh") and "Unknown field: kept" in c.details["Wants"]


# ─── a form's switches ───────────────────────────────────────────
def test_the_tick_box_the_manager_names_is_their_yes_to_whatsapp(client, business, meta, run, sent):
    from backend.models import ChannelPermission
    u = business()
    webhook(client, (meta.page, meta.form, meta.lead()))  # a first lead shows which tick boxes the form has
    run(_settled)
    [form] = [f for p in client.get("/api/meta", headers=u.h()).json()["pages"] for f in p["forms"] if f["form_id"] == meta.form]
    assert form["ticks"] == ["optional_1", "optional_2"] and form["settings"]["whatsapp_tick"] is None
    assert client.put(f"/api/meta/forms/{meta.form}", json={"whatsapp_tick": "optional_2"}, headers=u.h()).status_code == 200
    webhook(client, (meta.page, meta.form, meta.lead(full_name="Ravi", phone_number="+919876500411", email="ravi4@buyers.in")))  # optional_2 left unticked
    run(_settled)
    assert client.put(f"/api/meta/forms/{meta.form}", json={"whatsapp_tick": "optional_1"}, headers=u.h()).status_code == 200
    webhook(client, (meta.page, meta.form, meta.lead(full_name="Mala", phone_number="+919876500412", email="mala4@buyers.in")))
    run(_settled)

    async def kept():
        async with async_session() as db:
            return (await db.execute(select(ChannelPermission).where(ChannelPermission.bot_id == u.bot_id))).scalars().all()
    [p] = run(kept)
    assert (p.channel, p.state, p.words) == ("whatsapp", "granted", 'Ticked "optional_1" on the Facebook form "Site visit form"')
    assert client.put(f"/api/meta/forms/{meta.form}", json={"whatsapp_tick": ""}, headers=u.h()).status_code == 200
    [form] = [f for p in client.get("/api/meta", headers=u.h()).json()["pages"] for f in p["forms"] if f["form_id"] == meta.form]
    assert form["settings"]["whatsapp_tick"] is None


def test_nobody_is_emailed_or_called_until_the_form_says_so(client, business, meta, run, sent):
    u = business()
    s = client.get(f"/api/voice/schedule/settings/{u.bot_id}", headers=u.h()).json()["settings"]
    s["callbacks"]["enabled"], s["callbacks"]["hours"] = True, ["00:00", "23:59"]
    assert client.put(f"/api/voice/schedule/settings/{u.bot_id}", json=s, headers=u.h()).status_code == 200
    assert client.put(f"/api/email/setup/{u.bot_id}", json={"settings": {"lead_call": {"enabled": True, "minutes": 5}}}, headers=u.h()).status_code == 200
    webhook(client, (meta.page, meta.form, meta.lead()))
    run(_settled)
    assert run(_all, CallbackJob, bot_id=u.bot_id) == [] and run(_all, EmailJob, bot_id=u.bot_id) == []     # the assistant's own switches don't reach lead ads
    assert client.put(f"/api/meta/forms/{meta.form}", json={"call": True, "email": True}, headers=u.h()).status_code == 200
    webhook(client, (meta.page, meta.form, meta.lead(full_name="Ravi", phone_number="+919876500314", email="ravi@buyers.in")))
    run(_settled)
    [job] = run(_all, CallbackJob, bot_id=u.bot_id)
    assert job.e164 == "+919876500314" and "Instagram lead ads" in job.consent_source
    assert [j.to_email for j in run(_all, EmailJob, bot_id=u.bot_id)] == ["ravi@buyers.in"]


# ─── catching up ─────────────────────────────────────────────────
def test_the_catch_up_finds_what_the_webhook_missed_once(client, business, meta, run, sent):
    u = business()
    seen = meta.lead(full_name="Seen", phone_number="+919876500315")
    webhook(client, (meta.page, meta.form, seen))
    run(_settled)
    missed = [meta.lead(full_name=f"Missed {n}", phone_number=f"+91987650032{n}") for n in range(3)]
    meta.page_size = 2                                                                            # two pages of answers
    for _ in range(2):
        core._last_pass, core._last_catch_up = None, None
        run(core.tick, datetime.utcnow() + timedelta(minutes=1))
        run(_settled)
    assert sorted(c.name for c in run(_all, Contact, bot_id=u.bot_id)) == ["Missed 0", "Missed 1", "Missed 2", "Seen"]
    assert len(run(_all, MetaEvent, page_id=meta.page)) == 4 and len(alerts(sent)) == 4
    assert {e.via for e in run(_all, MetaEvent, page_id=meta.page) if e.leadgen_id in missed} == {"catch_up"}
    [form] = [f for f in run(_all, MetaForm, page_id=meta.page) if f.form_id == meta.form]
    assert form.checked_through is not None
    asked = [p for m, path, p, _a in meta.calls if path == f"{meta.form}/leads"]
    assert json.loads(asked[-1]["filtering"])[0]["operator"] == "GREATER_THAN"


def test_past_leads_come_in_quietly(client, business, meta, run, sent):
    u = business()
    old = meta.lead(full_name="Old Lead", phone_number="+919876500330", created=datetime.now(timezone.utc) - timedelta(days=20))
    assert client.post(f"/api/meta/forms/{meta.form}/import", json={"days": 30}, headers=u.h()).json() == {"started": True}
    run(_settled)
    [c] = run(_all, Contact, bot_id=u.bot_id)
    assert (c.name, c.quality, c.last_enquiry_at) == ("Old Lead", "old", None) and sent == [] and run(_all, LeadTask, contact_id=c.id) == []
    assert [e.kind for e in run(_all, LeadEvent, contact_id=c.id)] == ["imported"]
    assert [e.via for e in run(_all, MetaEvent, leadgen_id=old)] == ["import"]
    assert client.post(f"/api/meta/forms/{meta.other_form}/import", json={"days": 30}, headers=u.h()).status_code == 409   # no assistant yet


# ─── Meta's calls about people ───────────────────────────────────
def _signed_request(data: dict, secret: str = SECRET) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"algorithm": "HMAC-SHA256", **data}).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{sig}.{payload}"


def test_meta_s_deletion_request_deletes_the_sign_in(client, business, meta, run):
    u = business()
    assert client.post("/api/meta/deletion", data={"signed_request": _signed_request({"user_id": meta.me}, "wrong")}).status_code == 400
    r = client.post("/api/meta/deletion", data={"signed_request": _signed_request({"user_id": meta.me})})
    assert r.status_code == 200 and r.json()["confirmation_code"] and r.json()["url"].endswith(f"/api/meta/deletion/{r.json()['confirmation_code']}")
    assert run(_all, MetaConnection, user_id=u.id) == [] and run(_all, MetaPage, user_id=u.id) == []
    assert client.get(f"/api/meta/deletion/{r.json()['confirmation_code']}").status_code == 200


def test_removing_the_app_in_facebook_forgets_the_sign_in(client, business, meta, run):
    u = business()
    assert client.post("/api/meta/deauthorize", data={"signed_request": _signed_request({"user_id": meta.me})}).status_code == 200
    assert run(_all, MetaConnection, user_id=u.id) == []


def test_disconnecting_stops_the_page_and_keeps_the_leads(client, business, meta, run):
    u = business()
    webhook(client, (meta.page, meta.form, meta.lead()))
    run(_settled)
    conn = client.get("/api/meta", headers=u.h()).json()["connections"][0]["id"]
    assert client.delete(f"/api/meta/connections/{conn}", headers=u.h()).status_code == 200
    assert meta.page not in meta.subscribed and run(_all, MetaPage, user_id=u.id) == []
    assert len(run(_all, Contact, bot_id=u.bot_id)) == 1


def test_not_offered_until_nimmis_meta_app_is_set_up(client, make_user, monkeypatch):
    monkeypatch.delenv("META_APP_ID", raising=False)
    u = make_user()
    assert client.get("/api/meta", headers=u.h()).json()["available"] is False
    assert client.post("/api/meta/connect", headers=u.h()).status_code == 409


def test_the_lead_page_s_link_is_safe_from_big_ids():
    found, came, _ = core.from_lead({"id": "9" * 19, "form_id": "8" * 19, "campaign_id": "7" * 19, "field_data": [{"name": "full_name", "values": ["X"]}]}, "Form")
    assert came["form_id"] == "8" * 19 and came["campaign_id"] == "7" * 19 and found["name"] == "X"


def test_only_page_leadgen_webhooks_are_read(client, business, meta, run):
    business()
    lead = meta.lead()
    raw = json.dumps({"object": "whatsapp_business_account", "entry": [{"id": meta.page, "changes": [{"field": "leadgen", "value": {"leadgen_id": int(lead), "page_id": int(meta.page)}}]}]}).encode()
    assert client.post("/api/meta/webhook", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature(raw)}).status_code == 200
    run(_settled)
    assert run(_all, MetaEvent, leadgen_id=lead) == []


def test_four_processes_fetch_a_lead_once(client, business, meta, run):
    business()
    lead = meta.lead()
    [event_id] = run(core.keep, {"object": "page", "entry": [{"id": meta.page, "changes": [{"field": "leadgen", "value": {"leadgen_id": lead, "page_id": meta.page, "form_id": meta.form}}]}]})

    async def together():
        import asyncio
        await asyncio.gather(*(core.process(event_id) for _ in range(4)))
    run(together)
    assert sum(1 for m, path, *_ in meta.calls if path == lead) == 1


def test_a_catch_up_cut_short_moves_on_only_past_what_it_read(client, business, meta, run, monkeypatch):
    u = business()

    def through():
        return next(f.checked_through for f in run(_all, MetaForm, page_id=meta.page) if f.form_id == meta.form)
    before = through()
    for n in range(3):
        meta.lead(full_name=f"Late {n}", phone_number=f"+91987650034{n}")
    meta.page_size = 1
    meta.fail.append((f"{meta.form}/leads", 500, {"code": 2, "message": "Service temporarily unavailable"}))
    run(core.catch_up_form, meta.form, meta.page)
    assert through() == before                                                                    # Meta failed: nothing read
    monkeypatch.setattr(core, "CATCH_UP_PAGES", 1)
    assert len(run(core.catch_up_form, meta.form, meta.page)) == 1                                # one page of three this pass
    assert through() == before                                                                    # so it starts from the same place next time
    monkeypatch.setattr(core, "CATCH_UP_PAGES", 10)
    assert len(run(core.catch_up_form, meta.form, meta.page)) == 2 and through() != before         # the rest, then it moves on


def test_the_overlap_finds_a_lead_meta_shows_late(client, business, meta, run):
    u = business()
    [form] = [f for f in run(_all, MetaForm, page_id=meta.page) if f.form_id == meta.form]
    late = meta.lead(full_name="Shown late", phone_number="+919876500350", created=core._utc(form.checked_through) - timedelta(minutes=10))
    assert run(core.catch_up_form, meta.form, meta.page) and [e.leadgen_id for e in run(_all, MetaEvent, leadgen_id=late)] == [late]


def test_lead_ads_come_with_growth(client, business, meta, monkeypatch):
    u = business(route=False)
    monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")
    r = client.put(f"/api/meta/forms/{meta.form}", json={"bot_id": u.bot_id}, headers=u.h())
    assert r.status_code == 402


def test_a_page_role_that_cant_advertise_is_named(client, make_user, meta):
    meta.pages[meta.page]["tasks"] = ["ANALYZE"]
    u = make_user()
    client.post("/api/meta/connect/finish", json={"code": "C", "state": start(client, u)}, headers=u.h())
    page = client.get("/api/meta", headers=u.h()).json()["pages"][0]
    assert page["status"] == "permission" and "advertise" in page["error"]


def test_no_verify_token_set_verifies_nothing(client, meta, monkeypatch):
    monkeypatch.delenv("META_LEADS_VERIFY_TOKEN")
    assert client.get("/api/meta/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"}).status_code == 403


def test_the_same_webhook_on_two_processes_at_once_keeps_one(client, business, meta, run):
    business()
    lead = meta.lead()
    payload = {"object": "page", "entry": [{"id": meta.page, "changes": [{"field": "leadgen", "value": {"leadgen_id": lead, "page_id": meta.page, "form_id": meta.form}}]}]}

    async def together():
        import asyncio
        return await asyncio.gather(*(core.keep(payload) for _ in range(3)), return_exceptions=True)
    results = run(together)
    assert not [r for r in results if isinstance(r, Exception)] and sum(len(r) for r in results) == 1   # Meta always hears 200
    assert len(run(_all, MetaEvent, leadgen_id=lead)) == 1
