"""Bring your own number (customer Twilio and Exotel accounts) and swapping a number bought in Nimmi."""
import base64
import hashlib
import hmac
from datetime import datetime, timedelta

from sqlalchemy.future import select

from database import async_session
from backend.models import CallbackSettings, PhoneNumber, TelephonyAccount
from voice import exotel, twilio

SID = "AC" + "1" * 32
TOKEN = "their-auth-token"


def _sign(token, url, params):
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def _fake_twilio_account(monkeypatch):
    seen = {"voice_urls": [], "placed": []}

    async def verify(creds):
        assert creds == (SID, TOKEN)
        return "Green Park Twilio"

    async def numbers(creds):
        return [{"sid": "PNmine", "phone_number": "+14155550123", "friendly_name": "Office", "voice_url": "https://old.example/voice",
                 "country": "US"}]

    async def set_url(number_sid, url, creds=None):
        seen["voice_urls"].append((number_sid, url, creds))

    async def place(to, frm, job_id, detect_voicemail=False, creds=None, hook=None):
        seen["placed"].append({"to": to, "from": frm, "creds": creds, "hook": hook})
        return "CA-own"
    monkeypatch.setattr(twilio, "verify_account", verify)
    monkeypatch.setattr(twilio, "list_numbers", numbers)
    monkeypatch.setattr(twilio, "set_voice_url", set_url)
    monkeypatch.setattr(twilio, "place_call", place)
    return seen


def test_connect_own_twilio_number_routes_calls_and_restores_webhook(client, make_user, monkeypatch, run):
    seen = _fake_twilio_account(monkeypatch)
    u = make_user()
    bot = u.bot()

    assert client.post("/api/voice/phone-accounts", json={"provider": "twilio", "account_sid": "nope", "auth_token": "x"},
                       headers=u.h()).status_code == 400
    r = client.post("/api/voice/phone-accounts", json={"provider": "twilio", "account_sid": SID, "auth_token": TOKEN}, headers=u.h())
    assert r.status_code == 200, r.text
    acc = r.json()
    assert TOKEN not in r.text and acc["account_sid"].startswith("AC1111") and acc["label"] == "Green Park Twilio"

    async def stored():
        async with async_session() as db:
            return (await db.execute(select(TelephonyAccount).where(TelephonyAccount.id == acc["id"]))).scalars().first()
    row = run(stored)
    assert TOKEN not in row.secrets  # encrypted at rest
    hook = row.webhook_token

    listed = client.get(f"/api/voice/phone-accounts/{acc['id']}/numbers", headers=u.h()).json()["numbers"]
    assert listed[0]["phone_number"] == "+14155550123" and not listed[0]["connected"] and listed[0]["has_other_webhook"]

    r = client.post(f"/api/voice/phone-accounts/{acc['id']}/numbers", json={"phone_numbers": ["+14155550123"], "bot_id": bot}, headers=u.h())
    assert r.status_code == 200, r.text
    num = r.json()["numbers"][0]
    assert num["source"] == "own" and num["monthly_fee"] == 0 and num["bot_id"] == bot
    assert seen["voice_urls"][-1] == ("PNmine", f"https://example.test/api/voice/twilio/incoming/{hook}", (SID, TOKEN))

    # Nobody else can connect the same number.
    other = make_user()
    client.post("/api/voice/phone-accounts", json={"provider": "twilio", "account_sid": SID, "auth_token": TOKEN}, headers=other.h())
    other_acc = client.get("/api/voice/phone-accounts", headers=other.h()).json()["accounts"][0]
    assert client.post(f"/api/voice/phone-accounts/{other_acc['id']}/numbers", json={"phone_numbers": ["+14155550123"]},
                       headers=other.h()).status_code == 409

    # Incoming call on their account: must be signed with their token; reaches the assistant.
    url = f"https://example.test/api/voice/twilio/incoming/{hook}"
    form = {"To": "+14155550123", "From": "+919876543210", "CallSid": "CA1"}
    assert client.post(f"/api/voice/twilio/incoming/{hook}", data=form, headers={"X-Twilio-Signature": "bad"}).status_code == 403
    ok = client.post(f"/api/voice/twilio/incoming/{hook}", data=form, headers={"X-Twilio-Signature": _sign(TOKEN, url, form)})
    assert ok.status_code == 200 and f"/api/voice/ws/twilio/{hook}" in ok.text and "<Connect" in ok.text
    # Their token can't reach numbers that aren't on their account.
    stray = {"To": "+15005550006", "From": "+1", "CallSid": "CA2"}
    r = client.post(f"/api/voice/twilio/incoming/{hook}", data=stray, headers={"X-Twilio-Signature": _sign(TOKEN, url, stray)})
    assert "isn't set up" in r.text

    # Outbound calls from it go through their account, with their webhook token.
    async def minutes():
        from voice import metering
        async with async_session() as db:
            wallet = await metering.get_wallet(db, u.id)
            wallet.topup_minutes = 30
            await db.commit()
    run(minutes)
    r = client.post("/api/voice/test-call", json={"bot_id": bot, "phone": "98765 43210"}, headers=u.h())
    assert r.status_code == 200, r.text
    assert seen["placed"][-1] == {"to": "+919876543210", "from": "+14155550123", "creds": (SID, TOKEN), "hook": hook}

    # Disconnecting puts their old webhook back and removes the number from Nimmi.
    r = client.delete(f"/api/voice/phone-accounts/{acc['id']}", headers=u.h())
    assert r.status_code == 200 and r.json()["numbers_removed"] == 1
    assert seen["voice_urls"][-1] == ("PNmine", "https://old.example/voice", (SID, TOKEN))
    assert client.get("/api/voice/numbers", headers=u.h()).json() == []


def test_connect_exotel_account_gives_flow_urls(client, make_user, monkeypatch):
    async def verify(creds):
        assert creds["subdomain"] == "api.in.exotel.com"
    monkeypatch.setattr(exotel, "verify", verify)
    u = make_user()
    r = client.post("/api/voice/phone-accounts", json={"provider": "exotel", "account_sid": "greenpark1", "api_key": "k",
                                                      "api_token": "t", "subdomain": "api.in.exotel.com"}, headers=u.h())
    assert r.status_code == 200, r.text
    acc = r.json()
    assert acc["setup"]["voicebot"].startswith("wss://example.test/api/voice/ws/exotel/") and acc["app_id"] == ""
    assert client.patch(f"/api/voice/phone-accounts/{acc['id']}", json={"app_id": "12345"}, headers=u.h()).json()["app_id"] == "12345"
    r = client.post(f"/api/voice/phone-accounts/{acc['id']}/numbers", json={"phone_numbers": ["044 4567 8900"]}, headers=u.h())
    assert r.status_code == 200 and r.json()["numbers"][0]["provider"] == "exotel"
    # Exotel webhooks accept the account's own token, and nothing else.
    token = acc["setup"]["after_bot"].split("secret=")[1]
    assert client.get("/api/voice/exotel/after-bot", params={"secret": token, "CallSid": "x"}).status_code in (200, 302)
    assert client.get("/api/voice/exotel/after-bot", params={"secret": "w" * 30, "CallSid": "x"}).status_code == 403


def test_swap_a_number_bought_in_nimmi(client, make_user, monkeypatch, run):
    released, bought = [], []

    async def price(country, number_type):
        return 1.15

    async def buy(phone_number, friendly_name, address_sid=None):
        bought.append(phone_number)
        return "PNnew"

    async def release(sid):
        released.append(sid)
    monkeypatch.setattr(twilio, "monthly_price_usd", price)
    monkeypatch.setattr(twilio, "buy_number", buy)
    monkeypatch.setattr(twilio, "release_number", release)

    u = make_user()
    bot = u.bot()
    renews = datetime.utcnow() + timedelta(days=12)

    async def setup():
        async with async_session() as db:
            n = PhoneNumber(user_id=u.id, number="+1 415 555 0101", e164="+14155550101", kind="local", city="US", country="US",
                            status="active", provider="twilio", provider_sid="PNold", monthly_fee=200, bot_id=bot, next_charge_at=renews)
            db.add(n)
            await db.flush()
            db.add(CallbackSettings(user_id=u.id, enabled=True, from_number_id=n.id))
            await db.commit()
            return n.id
    old_id = run(setup)
    assert client.get("/api/voice/numbers", headers=u.h()).json()[0]["can_replace"] is True

    r = client.post(f"/api/voice/numbers/{old_id}/replace", json={"phone_number": "+14155550199"}, headers=u.h())
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["number"] != "+1 415 555 0101" and new["bot_id"] == bot and new["can_replace"] is False
    assert bought == ["+14155550199"] and released == ["PNold"]
    assert client.get("/api/voice/callbacks", headers=u.h()).json()["from_number_id"] == new["id"]
    assert new["next_charge_at"][:10] == renews.isoformat()[:10]  # the paid month carries over
    again = client.post(f"/api/voice/numbers/{new['id']}/replace", json={"phone_number": "+14155550177"}, headers=u.h())
    assert again.status_code == 400  # once per billing period
