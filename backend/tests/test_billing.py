"""Plans per assistant (BILLING_PLAN.md): Starter, Growth and Pro, monthly (renewing through Razorpay subscriptions) or
yearly (paid once a year); upgrades now, other changes from the end of the period; stopping and keeping renewal; the
webhook for renewals, failed charges and closed browsers; each payment once; reminders before a plan ends."""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import razorpay
from sqlalchemy.future import select

import payments
import subscriptions
from database import async_session
from backend.models import NotificationLog, Subscription, Transaction


class FakeRazorpay:
    """Razorpay as these tests need it: plans, subscriptions, orders, and every call made."""

    def __init__(self):
        self.calls, self.subs, self.orders, self.unavailable = [], {}, {}, False
        outer = self

        class Plans:
            def create(self, data):
                outer.calls.append(("plan.create", data))
                return {"id": f"plan_{uuid.uuid4().hex[:14]}"}

        class Subs:
            def create(self, data):
                if outer.unavailable:  # Subscriptions off for the account, or another refusal
                    raise razorpay.errors.BadRequestError(outer.unavailable if isinstance(outer.unavailable, str)
                                                          else "The requested URL was not found on the server.")
                sid = f"sub_{uuid.uuid4().hex[:14]}"
                outer.subs[sid] = {"id": sid, "status": "created", "notes": data["notes"], "plan_id": data["plan_id"],
                                   "current_end": None, "start_at": data.get("start_at"), "addons": data.get("addons")}
                outer.calls.append(("subscription.create", data))
                return outer.subs[sid]

            def fetch(self, sid):
                return outer.subs[sid]

            def cancel(self, sid, data):
                outer.calls.append(("subscription.cancel", sid))
                outer.subs[sid]["status"] = "cancelled"
                return outer.subs[sid]

        class Orders:
            def create(self, data):
                oid = f"order_{uuid.uuid4().hex[:14]}"
                outer.orders[oid] = {"id": oid, **data}
                outer.calls.append(("order.create", data))
                return outer.orders[oid]

            def fetch(self, oid):
                return outer.orders[oid]

        self.plan, self.subscription, self.order = Plans(), Subs(), Orders()

    def made(self, what):
        return [data for name, data in self.calls if name == what]


def _razorpay(monkeypatch) -> FakeRazorpay:
    fake = FakeRazorpay()
    monkeypatch.setattr(payments, "get_razorpay_client", lambda: fake)
    return fake


def _hmac(text: str) -> str:
    return hmac.new(b"test_secret", text.encode(), hashlib.sha256).hexdigest()


def _unix(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def _buy(client, u, fake, bot, tier, period, payment_id=None):
    """Checkout, then pay as Razorpay would (a subscription that starts now is charged at checkout)."""
    resp = client.post("/api/payments/checkout", json={"bot_id": bot, "tier": tier, "period": period}, headers=u.h())
    assert resp.status_code == 200, resp.text
    co = resp.json()
    payment_id = payment_id or f"pay_{uuid.uuid4().hex[:10]}"
    if co["mode"] == "subscription":
        sub = fake.subs[co["subscription_id"]]
        if not sub["start_at"]:
            sub.update(status="active", current_end=_unix(subscriptions.add_months(datetime.utcnow(), 1)))
        else:
            sub["status"] = "authenticated"
        body = {"razorpay_payment_id": payment_id, "razorpay_subscription_id": co["subscription_id"],
                "razorpay_signature": _hmac(f"{payment_id}|{co['subscription_id']}")}
    else:
        body = {"razorpay_payment_id": payment_id, "razorpay_order_id": co["order_id"],
                "razorpay_signature": _hmac(f"{co['order_id']}|{payment_id}")}
    done = client.post("/api/payments/verify", json=body, headers=u.h())
    assert done.status_code == 200, done.text
    return co, done.json()["message"]


def _plan(client, u, bot):
    [row] = [a for a in client.get("/api/payments/plans", headers=u.h()).json()["assistants"] if a["bot_id"] == bot]
    return row["current"], row["next"]


def _rows(run, bot):
    async def go():
        async with async_session() as db:
            return (await db.execute(select(Subscription).where(Subscription.bot_id == bot)
                                     .order_by(Subscription.start_date))).scalars().all()
    return run(go)


def _add(run, *rows):
    async def go():
        async with async_session() as db:
            db.add_all(rows)
            await db.commit()
    run(go)
    return rows[0]


def _webhook(client, event: str, entity: dict, payment: dict | None = None):
    payload = json.dumps({"event": event, "payload": {"subscription": {"entity": entity},
                                                      **({"payment": {"entity": payment}} if payment else {})}}).encode()
    signed = hmac.new(b"hook_secret", payload, hashlib.sha256).hexdigest()
    return client.post("/api/payments/webhook", content=payload, headers={"x-razorpay-signature": signed})


# ─── what a choice means ──────────────────────────────────────────
def test_what_choosing_a_plan_means_for_an_assistant():
    now = datetime(2026, 11, 10, 12, 0)
    buy = lambda current, tier, period, later=None, **kw: subscriptions.plan_purchase(current, later, tier, period, now=now, **kw)
    fresh = buy(None, "starter", "monthly")
    assert (fresh.action, fresh.pay_now, fresh.renews, fresh.ends_at) == ("start", 999, True, datetime(2026, 12, 10, 12, 0))
    yearly = buy(None, "pro", "yearly")
    assert (yearly.pay_now, yearly.renews, yearly.ends_at) == (69990, False, datetime(2027, 11, 10, 12, 0))  # 10 months' price
    assert buy(None, "starter", "monthly", subscriptions=False).renews is False

    starter = Subscription(id="s1", tier="starter", period="monthly", end_date=now + timedelta(days=15), auto_renewal=True,
                           razorpay_subscription_id="sub_1", price_paid=999, plan_name="Starter monthly")
    try:
        buy(starter, "starter", "monthly")
        raise AssertionError("bought twice")
    except ValueError as e:
        assert "renews by itself" in str(e)
    up = buy(starter, "growth", "monthly")
    assert (up.action, up.pay_now, up.starts_at, up.ends_at, up.replaces) == ("upgrade", 750, now, starter.end_date, "s1")
    down = Subscription(id="s2", tier="pro", period="monthly", end_date=now + timedelta(days=15), auto_renewal=True,
                        razorpay_subscription_id="sub_2", price_paid=6999, plan_name="Pro monthly")
    later = buy(down, "growth", "monthly")
    assert (later.action, later.pay_now, later.starts_at, later.renews) == ("schedule", 0, down.end_date, True)
    to_yearly = buy(down, "pro", "yearly")
    assert (to_yearly.action, to_yearly.pay_now, to_yearly.starts_at) == ("schedule", 69990, down.end_date)
    year = Subscription(id="s3", tier="growth", period="yearly", end_date=now + timedelta(days=100), auto_renewal=False,
                        price_paid=24990, plan_name="Growth yearly")
    more = buy(year, "growth", "yearly")
    assert (more.action, more.pay_now, more.ends_at) == ("extend", 24990, subscriptions.add_months(year.end_date, 12))
    assert buy(year, "pro", "yearly").pay_now == 12329  # (69,990 - 24,990) for 100 of 365 days, rounded up
    earlier = Subscription(id="s4", tier=None, plan_name="12 Month Plan", end_date=now + timedelta(days=200), price_paid=999)
    follows = buy(earlier, "pro", "monthly")
    assert (follows.action, follows.starts_at, follows.pay_now) == ("schedule", earlier.end_date, 0)
    paid_ahead = Subscription(id="s5", tier="pro", period="yearly", start_date=now + timedelta(days=15),
                              end_date=now + timedelta(days=380), auto_renewal=False, price_paid=69990, plan_name="Pro yearly")
    try:
        buy(down, "starter", "monthly", later=paid_ahead)
        raise AssertionError("changed a paid plan")
    except ValueError as e:
        assert "already paid" in str(e)


# ─── buying ───────────────────────────────────────────────────────
def test_a_monthly_plan_renews_by_itself_and_a_yearly_one_is_paid_once(client, make_user, monkeypatch):
    fake = _razorpay(monkeypatch)
    u = make_user()
    desk, shop = u.bot("Desk"), u.bot("Shop")
    co, message = _buy(client, u, fake, desk, "starter", "monthly")
    assert co["mode"] == "subscription" and co["pay_now"] == 999 and "renews by itself" in message
    [plan] = fake.made("plan.create")
    assert (plan["period"], plan["item"]["amount"]) == ("monthly", 99900)
    [sub] = fake.made("subscription.create")
    assert sub["total_count"] == 120 and "start_at" not in sub and sub["notes"]["mode"] == "subscription"
    current, nxt = _plan(client, u, desk)
    assert (current["label"], current["state"], current["renews"], nxt) == ("Starter monthly", "renews", True, None)
    assert [b["plan"] for b in client.get("/api/bots", headers=u.h()).json() if b["id"] == desk] == ["Starter monthly"]

    co, message = _buy(client, u, fake, shop, "growth", "yearly")
    assert co["mode"] == "order" and fake.made("order.create")[-1]["amount"] == 2499000 and "is on until" in message
    current, _ = _plan(client, u, shop)
    assert (current["label"], current["state"]) == ("Growth yearly", "ends")
    _buy(client, u, fake, shop, "growth", "yearly")  # renew early: a year more, from its end
    assert _plan(client, u, shop)[0]["ends"][:4] == str(datetime.utcnow().year + 2)
    history = client.get("/api/payments/history", headers=u.h()).json()
    assert sorted((h["plan_name"], h["amount"]) for h in history) == [
        ("Growth yearly", 24990), ("Growth yearly", 24990), ("Starter monthly", 999)]
    assert len(fake.made("plan.create")) == 1  # Razorpay's plan is made once per price


def test_an_upgrade_starts_now_paying_the_difference_and_the_old_subscription_stops(client, make_user, monkeypatch, run):
    fake = _razorpay(monkeypatch)
    u = make_user()
    bot = u.bot()
    end = datetime.utcnow() + timedelta(days=15)
    fake.subs["sub_old"] = {"id": "sub_old", "status": "active", "notes": {}}
    _add(run, Subscription(user_id=u.id, bot_id=bot, plan_name="Starter monthly", tier="starter", period="monthly",
                           price_paid=999, start_date=datetime.utcnow() - timedelta(days=15), end_date=end,
                           auto_renewal=True, razorpay_subscription_id="sub_old", rzp_status="active"))
    quote = client.post("/api/payments/quote", json={"bot_id": bot, "tier": "growth", "period": "monthly"}, headers=u.h()).json()
    assert quote["action"] == "upgrade" and quote["pay_now"] == 750 and "15 days left" in quote["note"]
    co, message = _buy(client, u, fake, bot, "growth", "monthly")
    new = fake.made("subscription.create")[-1]
    assert new["addons"][0]["item"]["amount"] == 75000 and abs(new["start_at"] - _unix(end)) < 5  # charges from the old end
    assert ("subscription.cancel", "sub_old") in fake.calls
    current, _ = _plan(client, u, bot)
    assert current["label"] == "Growth monthly" and current["ends"][:16] == end.isoformat()[:16]
    old = [r for r in _rows(run, bot) if r.razorpay_subscription_id == "sub_old"][0]
    assert (old.status, old.rzp_status) == ("replaced", "cancelled")
    assert ("Growth monthly, the days left", 750) in [(h["plan_name"], h["amount"]) for h in
                                                     client.get("/api/payments/history", headers=u.h()).json()]


def test_a_lower_plan_or_the_other_period_starts_when_this_one_ends(client, make_user, monkeypatch, run):
    fake = _razorpay(monkeypatch)
    u = make_user()
    bot = u.bot()
    end = datetime.utcnow() + timedelta(days=10)
    fake.subs["sub_pro"] = {"id": "sub_pro", "status": "active", "notes": {}}
    _add(run, Subscription(user_id=u.id, bot_id=bot, plan_name="Pro monthly", tier="pro", period="monthly", price_paid=6999,
                           start_date=datetime.utcnow() - timedelta(days=20), end_date=end, auto_renewal=True,
                           razorpay_subscription_id="sub_pro", rzp_status="active"))
    co, message = _buy(client, u, fake, bot, "starter", "monthly")
    assert co["pay_now"] == 0 and "starts on" in message
    assert abs(fake.made("subscription.create")[-1]["start_at"] - _unix(end)) < 5
    current, nxt = _plan(client, u, bot)
    assert (current["label"], current["renews"], nxt["label"], nxt["renews"]) == ("Pro monthly", False, "Starter monthly", True)
    assert ("subscription.cancel", "sub_pro") in fake.calls  # Pro won't charge again; Starter takes over at its end
    # Changing the mind before then: the change set earlier is dropped (and its subscription stopped).
    co, _ = _buy(client, u, fake, bot, "growth", "monthly")
    _, nxt = _plan(client, u, bot)
    assert nxt["label"] == "Growth monthly"
    assert len([1 for r in _rows(run, bot) if r.status == "cancelled" and r.tier == "starter"]) == 1


def test_without_razorpay_subscriptions_a_month_is_paid_on_its_own(client, make_user, monkeypatch):
    fake = _razorpay(monkeypatch)
    u = make_user()
    for refusal in (True, "The plan amount exceeds the limit set for UPI"):  # off for the account, or any other refusal
        fake.unavailable = refusal
        bot = u.bot()
        co, message = _buy(client, u, fake, bot, "starter", "monthly")
        assert co["mode"] == "order" and fake.made("order.create")[-1]["amount"] == 99900
        current, _ = _plan(client, u, bot)
        assert (current["state"], current["renews"]) == ("ends", False)


def test_a_renewal_the_webhook_never_told_us_about_keeps_the_assistant_live(run, make_user, monkeypatch):
    """With Razorpay's webhook not set up (or lost), the plan would end while the customer had been charged: at its end,
    the plan asks Razorpay where its subscription is."""
    fake = _razorpay(monkeypatch)
    u = make_user()
    renewed_bot, halted_bot = u.bot("Renewed"), u.bot("Halted")
    now = datetime.utcnow()
    for bot, sid in ((renewed_bot, "sub_quiet"), (halted_bot, "sub_stopped")):
        _add(run, Subscription(user_id=u.id, bot_id=bot, plan_name="Growth monthly", tier="growth", period="monthly",
                               price_paid=2499, start_date=now - timedelta(days=30), end_date=now + timedelta(minutes=20),
                               auto_renewal=True, razorpay_subscription_id=sid, rzp_status="active"))
    renewed_to = subscriptions.add_months(now, 1)
    fake.subs["sub_quiet"] = {"id": "sub_quiet", "status": "active", "current_end": _unix(renewed_to), "notes": {}}
    fake.subs["sub_stopped"] = {"id": "sub_stopped", "status": "halted", "current_end": _unix(now + timedelta(minutes=20)), "notes": {}}
    run(payments.maintenance)
    [renewed], [halted] = _rows(run, renewed_bot), _rows(run, halted_bot)
    assert abs((subscriptions.naive(renewed.end_date) - renewed_to).total_seconds()) < 2 and renewed.auto_renewal
    assert (halted.auto_renewal, halted.rzp_status) == (False, "halted")


# ─── renewing, failing, stopping ──────────────────────────────────
def test_renewals_failed_charges_and_closed_browsers_come_from_the_webhook(client, make_user, monkeypatch, run):
    fake = _razorpay(monkeypatch)
    told = []

    async def send(to, subject, text, *a, **kw):
        told.append(subject)
        return True
    from notify import email
    monkeypatch.setattr(email, "send_email", send)
    u = make_user()
    bot = u.bot("Front Desk")
    co, _ = _buy(client, u, fake, bot, "growth", "monthly", payment_id="pay_first")
    entity = fake.subs[co["subscription_id"]]
    first_end = _plan(client, u, bot)[0]["ends"]
    renewed_to = subscriptions.add_months(datetime.utcnow(), 2)
    entity["current_end"] = _unix(renewed_to)
    charge = {"id": "pay_renew", "amount": 249900, "order_id": "order_inv"}
    for _ in range(2):  # Razorpay sends it again: applied once
        assert _webhook(client, "subscription.charged", entity, charge).status_code == 200
    assert _plan(client, u, bot)[0]["ends"][:10] == renewed_to.isoformat()[:10] > first_end[:10]
    paid = [h for h in client.get("/api/payments/history", headers=u.h()).json()]
    assert [(h["plan_name"], h["amount"]) for h in paid] == [("Growth monthly", 2499), ("Growth monthly", 2499)]

    entity["charge_at"] = _unix(renewed_to)
    _webhook(client, "subscription.pending", entity)
    _webhook(client, "subscription.pending", entity)  # retried the next day: one email
    assert _plan(client, u, bot)[0]["state"] == "payment_failed" and told == ["Payment failed for Front Desk's plan"]
    _webhook(client, "subscription.halted", entity)
    assert _plan(client, u, bot)[0]["state"] == "halted" and told[-1] == "Front Desk's plan stopped renewing"

    # A browser that closed after paying: the webhook makes the plan.
    other = u.bot("Shop")
    resp = client.post("/api/payments/checkout", json={"bot_id": other, "tier": "pro", "period": "monthly"}, headers=u.h()).json()
    closed = fake.subs[resp["subscription_id"]]
    closed.update(status="active", current_end=_unix(subscriptions.add_months(datetime.utcnow(), 1)))
    _webhook(client, "subscription.charged", closed, {"id": "pay_closed", "amount": 699900})
    current, _ = _plan(client, u, other)
    assert (current["label"], current["state"]) == ("Pro monthly", "renews")
    assert ("Pro monthly", 6999) in [(h["plan_name"], h["amount"]) for h in client.get("/api/payments/history", headers=u.h()).json()]


def test_stop_renewing_then_keep_renewing(client, make_user, monkeypatch):
    fake = _razorpay(monkeypatch)
    u = make_user()
    bot = u.bot()
    co, _ = _buy(client, u, fake, bot, "starter", "monthly")
    stopped = client.post("/api/payments/stop-renewal", json={"bot_id": bot}, headers=u.h())
    assert stopped.status_code == 200 and "won't renew" in stopped.json()["message"]
    assert ("subscription.cancel", co["subscription_id"]) in fake.calls
    current, _ = _plan(client, u, bot)
    assert (current["state"], current["renews"]) == ("ends", False)
    again, message = _buy(client, u, fake, bot, "starter", "monthly")
    assert again["pay_now"] == 0 and fake.made("subscription.create")[-1]["start_at"]  # from the end of this month
    current, nxt = _plan(client, u, bot)
    assert nxt["renews"] and nxt["starts"][:16] == current["ends"][:16]
    assert client.post("/api/payments/stop-renewal", json={"bot_id": bot}, headers=u.h()).status_code == 200
    assert _plan(client, u, bot)[1] is None  # the renewal set to start later is dropped


def test_a_payment_applies_once_when_the_check_and_the_webhook_arrive_together(run, make_user):
    import asyncio
    u = make_user()
    bot = u.bot()
    notes = {"kind": "plan", "mode": "order", "user_id": u.id, "bot_id": bot, "tier": "growth", "period": "yearly",
             "action": "start", "pay_now": "24990"}

    async def both():
        async def one():
            async with async_session() as db:
                return await subscriptions.apply_purchase(db, notes, payment_id="pay_twice", order_id="order_twice")
        return await asyncio.gather(one(), one(), return_exceptions=True)
    results = run(both)
    assert not [r for r in results if isinstance(r, Exception)]
    rows = [r for r in _rows(run, bot) if r.status == "active"]

    async def paid():
        async with async_session() as db:
            return (await db.execute(select(Transaction).where(Transaction.razorpay_payment_id == "pay_twice"))).scalars().all()
    assert len(rows) == 1 and len(run(paid)) == 1


# ─── reminders ────────────────────────────────────────────────────
def test_reminders_before_a_plan_ends_go_once_and_not_for_renewing_plans(run, make_user, monkeypatch):
    sent = []

    async def send(to, subject, text, *a, **kw):
        sent.append(subject)
        return True
    from notify import email
    monkeypatch.setattr(email, "send_email", send)
    u = make_user()
    yearly, renewing, ended = u.bot("Yearly"), u.bot("Renewing"), u.bot("Ended")
    now = datetime.utcnow()
    _add(run, Subscription(user_id=u.id, bot_id=yearly, plan_name="Growth yearly", tier="growth", period="yearly",
                           price_paid=24990, start_date=now - timedelta(days=362), end_date=now + timedelta(days=2, hours=20),
                           auto_renewal=False),
         Subscription(user_id=u.id, bot_id=renewing, plan_name="Pro monthly", tier="pro", period="monthly", price_paid=6999,
                      start_date=now - timedelta(days=28), end_date=now + timedelta(days=2), auto_renewal=True,
                      razorpay_subscription_id="sub_live", rzp_status="active"),
         Subscription(user_id=u.id, bot_id=ended, plan_name="6 Month Plan", price_paid=499,
                      start_date=now - timedelta(days=180), end_date=now - timedelta(hours=3), auto_renewal=True))
    run(payments.maintenance)
    run(payments.maintenance)
    assert sorted(sent) == ["Ended's plan has ended", "Yearly's plan ends in 2 days"]

    async def logged():
        async with async_session() as db:
            return (await db.execute(select(NotificationLog.kind).where(NotificationLog.user_id == u.id))).scalars().all()
    assert sorted(run(logged)) == ["plan_ended", "plan_ends_soon"]


def test_the_website_and_billing_charge_the_same_prices():
    """The website's pricing table and the billing page read dashboard/src/lib/plans.ts; payments charge these."""
    import os
    import re
    path = os.path.join(os.path.dirname(__file__), "..", "..", "dashboard", "src", "lib", "plans.ts")
    ts = open(path, encoding="utf-8").read()
    site = {tier: int(monthly) for tier, monthly in re.findall(r'id: "(\w+)", name: "\w+", monthly: (\d+)', ts)}
    assert site == {tier: v["monthly"] for tier, v in subscriptions.TIERS.items()}
    assert f"YEARLY_PAYS_FOR = {subscriptions.PERIODS['yearly']['pays_for']};" in ts
