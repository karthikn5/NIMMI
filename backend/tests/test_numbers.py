"""Self-serve numbers: Nimmi balance, buying through Twilio, monthly renewal, pausing and releasing."""
import hashlib
import hmac
from datetime import datetime, timedelta

import pytest
from sqlalchemy.future import select

import balance
import payments
from database import async_session
from backend.models import BalanceEntry, PhoneNumber
from voice import scheduler, twilio


@pytest.fixture
def fake_twilio(monkeypatch):
    calls = {"bought": [], "released": []}

    async def search(country, number_type, area_code="", contains=""):
        return [{"phone_number": "+14155550101", "friendly_name": "(415) 555-0101", "locality": "San Francisco",
                 "region": "CA", "address_required": False}]

    async def price(country, number_type):
        return 1.15  # USD/month -> ceil(1.15 * 85 * 2 / 10) * 10 = Rs 200

    async def buy(phone_number, friendly_name, address_sid=None):
        calls["bought"].append(phone_number)
        return "PN123"

    async def release(sid):
        calls["released"].append(sid)

    monkeypatch.setattr(twilio, "search_numbers", search)
    monkeypatch.setattr(twilio, "monthly_price_usd", price)
    monkeypatch.setattr(twilio, "buy_number", buy)
    monkeypatch.setattr(twilio, "release_number", release)
    return calls


def _topup(client, user, monkeypatch, rupees, order_id):
    async def fetch(oid):
        return {"amount": rupees * 100, "notes": {"kind": "balance_topup", "user_id": user.id}}
    monkeypatch.setattr(payments, "_fetch_order", fetch)
    sig = hmac.new(b"test_secret", f"{order_id}|pay_{order_id}".encode(), hashlib.sha256).hexdigest()
    body = {"razorpay_order_id": order_id, "razorpay_payment_id": f"pay_{order_id}", "razorpay_signature": sig}
    for _ in range(2):  # replaying the same payment must not credit twice
        assert client.post("/api/payments/verify", json=body, headers=user.h()).status_code == 200


def test_balance_charge_is_atomic_and_once(make_user, run):
    u = make_user()

    async def scenario():
        async with async_session() as db:
            await balance.credit(db, u.id, 50000, "topup", "t-1")
            assert not await balance.credit(db, u.id, 50000, "topup", "t-1")  # same ref: ignored
            assert await balance.charge(db, u.id, 20000, "number_rental", "r-1")
            assert not await balance.charge(db, u.id, 20000, "number_rental", "r-1")
            with pytest.raises(balance.InsufficientBalance):
                await balance.charge(db, u.id, 40000, "number_rental", "r-2")
            return (await balance.get(db, u.id)).balance_paise
    assert run(scenario) == 30000


def test_search_buy_and_release(client, make_user, monkeypatch, fake_twilio, run):
    u = make_user()
    bot = u.bot()
    found = client.get("/api/voice/numbers/available?country=US&type=local", headers=u.h()).json()
    assert found["monthly_fee"] == 200 and found["numbers"][0]["phone_number"] == "+14155550101"
    assert client.get("/api/voice/numbers/available?country=IN&type=local", headers=u.h()).status_code == 400

    buy = {"phone_number": "+14155550101", "country": "US", "type": "local", "bot_id": bot}
    r = client.post("/api/voice/numbers/buy", json=buy, headers=u.h())
    assert r.status_code == 402 and "balance" in r.json()["detail"].lower()
    assert client.get("/api/voice/numbers", headers=u.h()).json() == []  # nothing left behind

    _topup(client, u, monkeypatch, 500, "order_bal1")
    assert client.get("/api/billing/balance", headers=u.h()).json()["balance"] == 500

    r = client.post("/api/voice/numbers/buy", json=buy, headers=u.h())
    assert r.status_code == 200, r.text
    bought = r.json()
    assert bought["status"] == "active" and bought["bot_id"] == bot and fake_twilio["bought"] == ["+14155550101"]
    bal = client.get("/api/billing/balance", headers=u.h()).json()
    assert bal["balance"] == 300 and bal["monthly_commitment"] == 200

    assert client.delete(f"/api/voice/numbers/{bought['id']}", headers=u.h()).status_code == 200
    assert fake_twilio["released"] == ["PN123"]


def test_failed_purchase_is_refunded(client, make_user, monkeypatch, fake_twilio):
    u = make_user()
    _topup(client, u, monkeypatch, 500, "order_bal2")

    async def broken(phone_number, friendly_name, address_sid=None):
        raise twilio.TwilioError("Number no longer available")
    monkeypatch.setattr(twilio, "buy_number", broken)
    r = client.post("/api/voice/numbers/buy", json={"phone_number": "+14155550101", "country": "US", "type": "local"},
                    headers=u.h())
    assert r.status_code == 502 and "haven't been charged" in r.json()["detail"]
    assert client.get("/api/billing/balance", headers=u.h()).json()["balance"] == 500


def test_monthly_renewal_pause_and_release(client, make_user, monkeypatch, fake_twilio, run):
    u = make_user()
    _topup(client, u, monkeypatch, 500, "order_bal3")
    num = client.post("/api/voice/numbers/buy", json={"phone_number": "+14155550101", "country": "US", "type": "local"},
                      headers=u.h()).json()  # Rs 200 charged, Rs 300 left

    async def make_due(days_ago, days_suspended=None):
        # Each month's rent has its own reference (by due date), so use distinct dates.
        async with async_session() as db:
            n = (await db.execute(select(PhoneNumber).where(PhoneNumber.id == num["id"]))).scalars().first()
            n.next_charge_at = datetime.utcnow() - timedelta(days=days_ago, minutes=1)
            if days_suspended is not None:
                n.suspended_at = datetime.utcnow() - timedelta(days=days_suspended)
            await db.commit()

    async def state():
        async with async_session() as db:
            n = (await db.execute(select(PhoneNumber).where(PhoneNumber.id == num["id"]))).scalars().first()
            return n.status if n else "released"

    run(make_due, 0)
    run(scheduler.renew_numbers)  # Rs 300 -> Rs 100, still active
    assert run(state) == "active"
    assert client.get("/api/billing/balance", headers=u.h()).json()["balance"] == 100

    run(make_due, 1)
    run(scheduler.renew_numbers)  # Rs 100 < Rs 200: paused
    assert run(state) == "suspended"
    incoming = client.post("/api/voice/twilio/incoming/tw-secret", data={"To": "+14155550101", "From": "+15555550100"})
    assert "isn't set up" in incoming.text  # a paused number doesn't answer

    run(make_due, 2, 8)
    run(scheduler.renew_numbers)  # past the 7-day grace: released
    assert run(state) == "released" and fake_twilio["released"] == ["PN123"]

    async def rent_entries():
        async with async_session() as db:
            return (await db.execute(select(BalanceEntry).where(BalanceEntry.user_id == u.id,
                                                                BalanceEntry.kind == "number_rental"))).scalars().all()
    assert len(run(rent_entries)) == 2  # first month + one renewal


def test_missing_columns_are_added_to_existing_tables(tmp_path):
    from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect
    from database import _add_missing_columns
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    old = MetaData()
    Table("things", old, Column("id", Integer, primary_key=True))
    old.create_all(engine)
    new = MetaData()
    Table("things", new, Column("id", Integer, primary_key=True), Column("label", String, nullable=True))
    with engine.begin() as conn:
        _add_missing_columns(conn, new)
    assert "label" in {c["name"] for c in inspect(engine).get_columns("things")}
