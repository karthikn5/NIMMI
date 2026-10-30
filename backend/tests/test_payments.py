"""Plan and minute-pack payments: signatures, order notes as the source of truth, idempotency."""
import hashlib
import hmac
import json

import payments


def sign(order_id, payment_id):
    return hmac.new(b"test_secret", f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def fake_orders(monkeypatch, orders: dict):
    async def fetch(order_id):
        return orders[order_id]
    monkeypatch.setattr(payments, "_fetch_order", fetch)


def test_bad_signature_is_rejected(client, make_user):
    u = make_user()
    body = {"razorpay_order_id": "order_1", "razorpay_payment_id": "pay_1", "razorpay_signature": "nope"}
    assert client.post("/api/payments/verify", json=body, headers=u.h()).status_code == 400


def test_plan_comes_from_the_order_not_the_browser(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    # Paid for the 1 Month plan, then claims the 12 Month plan in the request body.
    fake_orders(monkeypatch, {"order_a": {"amount": 99900, "notes": {"kind": "plan", "user_id": u.id, "bot_id": bot, "plan_name": "1 Month Plan"}}})
    body = {"razorpay_order_id": "order_a", "razorpay_payment_id": "pay_a", "razorpay_signature": sign("order_a", "pay_a"),
            "plan_name": "12 Month Plan"}
    assert client.post("/api/payments/verify", json=body, headers=u.h()).status_code == 200
    listed = client.get("/api/bots", headers=u.h()).json()[0]
    assert listed["plan"] == "1 Month Plan" and 28 <= listed["days_remaining"] <= 30


def test_replaying_a_payment_does_not_extend_twice(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    fake_orders(monkeypatch, {"order_b": {"amount": 49900, "notes": {"kind": "plan", "user_id": u.id, "bot_id": bot, "plan_name": "6 Month Plan"}}})
    body = {"razorpay_order_id": "order_b", "razorpay_payment_id": "pay_b", "razorpay_signature": sign("order_b", "pay_b")}
    for _ in range(3):
        assert client.post("/api/payments/verify", json=body, headers=u.h()).status_code == 200
    days = client.get("/api/bots", headers=u.h()).json()[0]["days_remaining"]
    assert days < 181  # one 180-day plan, not three
    assert len(client.get("/api/payments/history", headers=u.h()).json()) == 1


def test_a_month_costs_what_the_plan_says_and_history_names_what_was_bought(client, make_user, monkeypatch):
    """The 1 Month plan cost Rs 1 on live from 12 to 30 Oct 2026 (a test price). Now Rs 999, the same as the 12 Month
    plan: the history names the plan from the payment's own order, not from the amount."""
    u = make_user()
    bot = u.bot()
    assert payments.PLANS["1 Month Plan"]["price"] == 999
    fake_orders(monkeypatch, {"order_y": {"amount": 99900, "notes": {"kind": "plan", "user_id": u.id, "bot_id": bot, "plan_name": "12 Month Plan"}}})
    body = {"razorpay_order_id": "order_y", "razorpay_payment_id": "pay_y", "razorpay_signature": sign("order_y", "pay_y")}
    assert client.post("/api/payments/verify", json=body, headers=u.h()).status_code == 200
    [paid] = client.get("/api/payments/history", headers=u.h()).json()
    assert (paid["plan_name"], paid["amount"]) == ("12 Month Plan", 999)


def test_amount_must_match_the_plan(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    fake_orders(monkeypatch, {"order_c": {"amount": 100, "notes": {"kind": "plan", "user_id": u.id, "bot_id": bot, "plan_name": "12 Month Plan"}}})
    body = {"razorpay_order_id": "order_c", "razorpay_payment_id": "pay_c", "razorpay_signature": sign("order_c", "pay_c")}
    assert client.post("/api/payments/verify", json=body, headers=u.h()).status_code == 400


def test_someone_elses_payment_cannot_be_claimed(client, make_user, monkeypatch):
    owner, thief = make_user(), make_user()
    bot = owner.bot()
    fake_orders(monkeypatch, {"order_d": {"amount": 99900, "notes": {"kind": "plan", "user_id": owner.id, "bot_id": bot, "plan_name": "1 Month Plan"}}})
    body = {"razorpay_order_id": "order_d", "razorpay_payment_id": "pay_d", "razorpay_signature": sign("order_d", "pay_d")}
    assert client.post("/api/payments/verify", json=body, headers=thief.h()).status_code == 403


def test_credit_pack_credits_once(client, make_user, monkeypatch):
    u = make_user()
    created = {}

    class FakeOrders:
        def create(self, data):
            created["order"] = {"id": "order_v", **data}
            return created["order"]

    class FakeClient:
        order = FakeOrders()

    monkeypatch.setattr(payments, "get_razorpay_client", lambda: FakeClient())
    resp = client.post("/api/payments/create-minutes-order", json={"pack_id": "p_100"}, headers=u.h())
    assert resp.status_code == 200 and resp.json()["credits"] == 100

    fake_orders(monkeypatch, {"order_v": created["order"]})
    before = client.get("/api/voice/overview", headers=u.h()).json()["credits_left"]
    body = {"razorpay_order_id": "order_v", "razorpay_payment_id": "pay_v", "razorpay_signature": sign("order_v", "pay_v")}
    assert client.post("/api/payments/verify", json=body, headers=u.h()).json()["message"] == "Added 100 voice credits"
    client.post("/api/payments/verify", json=body, headers=u.h())
    after = client.get("/api/voice/overview", headers=u.h()).json()["credits_left"]
    assert after - before == 100
    assert client.get("/api/payments/history", headers=u.h()).json()[0]["plan_name"] == "100 voice credits"


def test_webhook_requires_signature_and_activates(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    fake_orders(monkeypatch, {"order_w": {"amount": 99900, "notes": {"kind": "plan", "user_id": u.id, "bot_id": bot, "plan_name": "1 Month Plan"}}})
    payload = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_w", "order_id": "order_w"}}}}).encode()
    assert client.post("/api/payments/webhook", content=payload, headers={"x-razorpay-signature": "bad"}).status_code == 400
    good = hmac.new(b"hook_secret", payload, hashlib.sha256).hexdigest()
    assert client.post("/api/payments/webhook", content=payload, headers={"x-razorpay-signature": good}).status_code == 200
    assert client.get("/api/bots", headers=u.h()).json()[0]["status"] == "Active"
