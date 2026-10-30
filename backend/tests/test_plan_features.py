"""What each plan includes (BILLING_PLAN.md phase 2: the website's lists made real), with plan limits on: AI replies a
month, live chat, WhatsApp, call-backs and campaigns, transfers, Pro's call credits, and what a workspace shares
(integrations, business hours, team seats) by its best plan. The earlier 1/6/12 Month plans keep everything."""
import asyncio
import uuid
from datetime import datetime, timedelta

import pytest

import assist
import plans
import subscriptions
from database import async_session
from backend.models import AiReplyUsage, Subscription, WorkspaceSettings
from routers import chat as chat_router
from tests.test_voice_inbound import AGENT
from voice import router as voice_router
from voice import schedule


@pytest.fixture
def limits_on(monkeypatch):
    """Plan limits switched on, once a test's assistants exist (the free plan allows one)."""
    return lambda: monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")


def _plan(run, user, bot, tier=None, name=None):
    """An active plan for `bot`: a tier, or an earlier plan by `name`."""
    async def go():
        async with async_session() as db:
            db.add(Subscription(user_id=user.id, bot_id=bot, tier=tier, period="monthly" if tier else None,
                                plan_name=name or subscriptions.label(tier, "monthly"), price_paid=999, credits_granted=1,
                                start_date=datetime.utcnow() - timedelta(days=1), end_date=datetime.utcnow() + timedelta(days=29),
                                auto_renewal=False, status="active"))
            await db.commit()
    run(go)


def _includes(run, bot):
    async def go():
        async with async_session() as db:
            return await plans.includes(db, bot)
    return run(go)


def _say(client, bot, text, headers=None, demo=False):
    return client.post("/api/chat/message", json={"bot_id": bot, "message": text, "is_demo": demo,
                                                  "visitor_session_id": f"widget-session-ai-{uuid.uuid4().hex[:12]}"},
                       headers=headers or {}).json()


def test_each_plan_includes_what_the_website_lists(client, make_user, run, limits_on):
    u = make_user()
    free, starter, growth, pro, earlier = (u.bot(n) for n in ("Free", "Starter", "Growth", "Pro", "Earlier"))
    limits_on()
    for bot, tier in ((starter, "starter"), (growth, "growth"), (pro, "pro")):
        _plan(run, u, bot, tier)
    _plan(run, u, earlier, name="12 Month Plan")
    got = {name: _includes(run, bot) for name, bot in (("free", free), ("starter", starter), ("growth", growth), ("pro", pro),
                                                         ("earlier", earlier))}
    assert got["free"] == plans.NO_PLAN and got["earlier"].replies is None and got["earlier"].whatsapp
    assert [got[t].replies for t in ("starter", "growth", "pro")] == [2000, 10000, 25000]
    assert [got[t].seats for t in ("starter", "growth", "pro")] == [1, 3, 5]
    assert (got["starter"].whatsapp, got["growth"].whatsapp, got["growth"].schedule, got["pro"].schedule) == (False, True, False, True)
    assert got["pro"].call_credits == 300
    limits = client.get("/api/account/limits", headers=u.h()).json()
    assert limits["includes"]["tier"] in ("pro", "earlier") and limits["assistant_plans"][growth]["tier"] == "growth"
    assert limits["assistant_plans"][starter]["replies"] == 2000 and limits["assistant_plans"][starter]["replies_used"] == 0
    assert limits["used"]["seats"] == 1


def test_ai_replies_stop_at_the_monthly_allowance_and_the_owner_hears(client, make_user, run, limits_on, monkeypatch):
    sent = []

    async def send(to, subject, text, *a, **kw):
        sent.append(subject)
        return True
    from notify import email
    monkeypatch.setattr(email, "send_email", send)
    monkeypatch.setattr(chat_router, "generate_ai_response", lambda *a, **k: "We open at 9.")
    u = make_user()
    bot = u.bot("Desk")
    limits_on()
    _plan(run, u, bot, "starter")

    async def used(n=None):
        async with async_session() as db:
            row = await db.get(AiReplyUsage, (bot, plans.this_month()))
            if n is not None:
                if row is None:
                    db.add(AiReplyUsage(bot_id=bot, month=plans.this_month(), replies=n))
                else:
                    row.replies = n
                await db.commit()
            return (await db.get(AiReplyUsage, (bot, plans.this_month()))).replies if n is None else n

    async def settle():
        await asyncio.sleep(0.3)
    assert _say(client, bot, "When do you open?")["answer"] == "We open at 9."
    run(settle)
    assert run(used) == 1
    run(used, 1599)
    _say(client, bot, "And on Sunday?")
    run(settle)
    assert sent == ["Desk has used 80% of its AI replies this month"]
    run(used, 1999)
    assert _say(client, bot, "Parking?")["answer"] == "We open at 9."  # the 2,000th
    run(settle)
    assert sent[-1] == "Desk has used all its AI replies this month"
    assert _say(client, bot, "Fees?")["answer"] == plans.REPLIES_USED_UP
    assert _say(client, bot, "Fees?", headers=u.h(), demo=True)["answer"] == "We open at 9."  # the business trying it
    run(settle)
    assert run(used) == 2000


def test_live_chat_and_the_call_back_offer_follow_the_plan(client, make_user, run, limits_on, monkeypatch):
    monkeypatch.setattr(chat_router, "generate_ai_response", lambda *a, **k: "Leave your number and we'll call you.")
    u = make_user()
    starter, growth = u.bot("Starter"), u.bot("Growth")
    limits_on()
    _plan(run, u, starter, "starter")
    _plan(run, u, growth, "growth")
    assert client.get(f"/api/bots/{starter}/config").json()["live_chat"] is False
    assert client.get(f"/api/bots/{growth}/config").json()["live_chat"] is True
    asked = _say(client, starter, "Can I talk to a person?")
    assert asked["answer"] == "Leave your number and we'll call you." and "handoff_status" not in asked
    handoff = {"bot_id": starter, "visitor_session_id": f"widget-session-human-{uuid.uuid4().hex[:12]}"}
    assert client.post("/api/chat/handoff", json=handoff).status_code == 403
    assert _say(client, growth, "Can I talk to a person?").get("handoff_status") == "pending"
    assert client.get(f"/api/bots/{growth}/config").json()["callbacks_enabled"] is False  # call-backs: Pro


def test_whatsapp_campaigns_schedule_and_transfers_need_their_plan(client, make_user, run, limits_on):
    from tests.test_voice_schedule import _raw
    u = make_user()
    starter, growth, pro = u.bot("Starter"), u.bot("Growth"), u.bot("Pro")
    limits_on()
    for bot, tier in ((starter, "starter"), (growth, "growth"), (pro, "pro")):
        _plan(run, u, bot, tier)
    wa = client.post("/api/whatsapp/numbers", json={"bot_id": starter, "phone_number_id": "1234567890", "access_token": "x" * 30},
                     headers=u.h())
    assert wa.status_code == 402 and wa.json()["detail"] == "WhatsApp comes with the Growth plan. Choose it for Starter on the Billing page."
    sched = client.put(f"/api/voice/schedule/settings/{growth}", json=_raw(), headers=u.h())
    assert sched.status_code == 402 and "come with the Pro plan" in sched.json()["detail"]
    assert client.put(f"/api/voice/schedule/settings/{growth}", json={}, headers=u.h()).status_code == 200  # off: fine
    assert client.put(f"/api/voice/schedule/settings/{pro}", json=_raw(), headers=u.h()).status_code == 200
    campaign = client.post("/api/voice/campaigns", json={"name": "Diwali", "bot_id": growth, "from_number_id": "n",
                                                         "purpose": "Tell them about the offer", "contacts": [], "consent": True},
                           headers=u.h())
    assert campaign.status_code == 402 and campaign.json()["detail"].startswith("Campaigns come with the Pro plan")
    transfer = client.put(f"/api/voice/agents/{growth}", json={**AGENT, "transfer_enabled": True, "transfer_number": "+919840012345"},
                          headers=u.h())
    assert transfer.status_code == 402 and "Transfers to your team come with the Pro plan" in transfer.json()["detail"]
    assert client.put(f"/api/voice/agents/{growth}", json=AGENT, headers=u.h()).status_code == 200  # the rest saves

    async def check(bot):
        async with async_session() as db:
            from backend.models import CallbackJob
            return await schedule.dial_check(db, CallbackJob(user_id=u.id, bot_id=bot, e164="+919800000001", kind="callback"))
    assert run(check, growth).stop == ("cancelled", "Call-backs and follow-up calls come with the Pro plan")
    assert run(check, pro).stop == ("failed", "No active number to call from")  # past the plan (this test has no number)


def test_a_call_on_a_plan_without_transfers_neither_transfers_nor_rings_the_team(run, make_user, monkeypatch, limits_on, client):
    from backend.models import CallbackJob, VoiceAgent
    u = make_user()
    bot = u.bot()
    limits_on()
    _plan(run, u, bot, "growth")

    async def setup():
        async with async_session() as db:
            db.add(VoiceAgent(bot_id=bot, user_id=u.id, enabled=True, voice_id="priya", language="en-IN", assistant_name="Nimmi",
                              company_name="Desk", greeting="How can I help?", transfer_enabled=True,
                              transfer_number="+919840012345", team_handoff=True))
            job = CallbackJob(user_id=u.id, bot_id=bot, e164="+919800000002", status="calling", consent_source="Asked on the website")
            db.add(job)
            await db.commit()
            return job.id
    job_id = run(setup)
    seen = []

    class Session:
        def __init__(self, s, transport):
            seen.append(s)

        async def run(self):
            return None
    monkeypatch.setattr(voice_router, "CallSession", Session)

    class Transport:
        async def hangup(self, reason):
            seen.append(reason)
    run(voice_router._route_and_run, Transport(), "CA-plan", None, None, job_id=job_id)
    [s] = seen
    assert (s.agent.transfer_enabled, s.agent.team_handoff) == (False, False)


def test_pro_brings_300_call_credits_a_month_at_once(client, make_user, run, limits_on):
    u = make_user()
    bot = u.bot()
    limits_on()
    before = client.get("/api/voice/overview", headers=u.h()).json()["credits_left"]

    async def buy():
        async with async_session() as db:
            await subscriptions.apply_purchase(db, {"kind": "plan", "mode": "order", "user_id": u.id, "bot_id": bot, "tier": "pro",
                                                    "period": "monthly", "action": "start", "pay_now": "6999"},
                                               payment_id=f"pay_{uuid.uuid4().hex[:8]}", order_id=f"order_{uuid.uuid4().hex[:8]}")
    run(buy)
    assert client.get("/api/voice/overview", headers=u.h()).json()["credits_left"] == before + 300


def test_what_a_workspace_shares_follows_its_best_plan(client, make_user, run, limits_on):
    u = make_user()
    bot = u.bot()
    limits_on()
    hours = {"business_hours": {"enabled": True, "days": {d: {"open": True, "from": "09:00", "to": "18:00"} for d in assist.DAYS}},
             "escalate_upset": True}
    assert client.put("/api/integrations", json={"email_alerts": True}, headers=u.h()).status_code == 402  # free
    assert client.post("/api/team/invite", json={"email": "a@example.com", "role": "agent"}, headers=u.h()).status_code == 402

    _plan(run, u, bot, "growth")
    assert client.put("/api/integrations", json={"email_alerts": True}, headers=u.h()).status_code == 200
    hook = client.put("/api/integrations", json={"email_alerts": True, "webhook_url": "https://example.com/hook"}, headers=u.h())
    assert hook.status_code == 402 and hook.json()["detail"].startswith("Webhooks, LeadSquared and Google Sheets come with the Pro plan")
    open_hours = client.put("/api/workspace/settings", json=hours, headers=u.h())
    assert open_hours.status_code == 402 and open_hours.json()["detail"].startswith("Business hours come with the Pro plan")
    for n in range(2):
        assert client.post("/api/team/invite", json={"email": f"m{n}@example.com", "role": "agent"}, headers=u.h()).status_code == 200
    third = client.post("/api/team/invite", json={"email": "m3@example.com", "role": "agent"}, headers=u.h())
    assert third.status_code == 402 and "3 team seats" in third.json()["detail"]

    # Hours saved earlier (a plan that had them): kept, but not applied without Pro.
    async def saved_hours():
        async with async_session() as db:
            db.add(WorkspaceSettings(user_id=u.id, business_hours={**hours["business_hours"], "days": {
                d: {"open": False, "from": "09:00", "to": "18:00"} for d in assist.DAYS}}))
            await db.commit()
    run(saved_hours)
    assert run(assist.workspace, u.id).business_hours["enabled"] is False and run(assist.away_reply, u.id) is None
    _plan(run, u, u.bot("Second"), "pro")
    assert run(assist.workspace, u.id).business_hours["enabled"] is True
    assert client.put("/api/workspace/settings", json=hours, headers=u.h()).status_code == 200


def test_lead_alerts_and_webhooks_follow_the_plan(client, make_user, run, limits_on, monkeypatch):
    from backend.models import Conversation, IntegrationSettings
    from notify import channels, email, events
    sent, hooks = [], []

    async def send(to, subject, text, *a, **kw):
        sent.append(subject)
        return True

    async def hook(url, secret, event, data):
        hooks.append(event)
    monkeypatch.setattr(email, "send_email", send)
    monkeypatch.setattr(channels, "post_webhook", hook)
    u = make_user()
    starter, growth, pro = u.bot("Starter"), u.bot("Growth"), u.bot("Pro")
    limits_on()

    async def lead(bot):
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id=f"s-{uuid.uuid4().hex[:8]}",
                                captured_data={"Name": "Priya", "Phone": "+919876543210"})
            db.add(conv)
            await db.commit()
            return conv.conversation_id

    async def setup():
        async with async_session() as db:
            db.add(IntegrationSettings(user_id=u.id, email_alerts=True, webhook_url="https://example.com/hook"))
            await db.commit()
    run(setup)
    _plan(run, u, starter, "starter")
    run(events.lead_captured, run(lead, starter))
    assert (sent, hooks) == ([], [])  # Starter: neither
    _plan(run, u, growth, "growth")
    run(events.lead_captured, run(lead, growth))
    assert (sent, hooks) == (["New lead from Growth"], [])  # Growth: the alert, no webhook
    _plan(run, u, pro, "pro")
    run(events.lead_captured, run(lead, pro))
    assert sent[-1] == "New lead from Pro" and hooks == ["lead.captured"]  # Pro: both (the workspace's best plan)


def test_earlier_plans_keep_everything_until_they_end(client, make_user, run, limits_on):
    u = make_user()
    bot = u.bot()
    limits_on()
    _plan(run, u, bot, name="6 Month Plan")
    got = _includes(run, bot)
    assert got.tier == "earlier" and got.replies is None and all((got.whatsapp, got.live_chat, got.schedule, got.campaigns,
                                                                 got.integrations, got.business_hours, got.transfers))


    async def after_many_replies():
        async with async_session() as db:
            db.add(AiReplyUsage(bot_id=bot, month=plans.this_month(), replies=99_999))
            await db.commit()
            return await plans.can_reply(db, bot)
    assert run(after_many_replies) is True  # no allowance to run out of
