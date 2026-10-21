"""Deleted assistants can be restored for 30 days; payment records are never deleted with them."""
from datetime import datetime, timedelta

from sqlalchemy.future import select

import recycle
import vector_store
from database import async_session
from backend.models import (Bot, CallLog, Campaign, Conversation, DeletedItem, Message, PhoneNumber, Subscription,
                            Transaction, VoiceAgent)


def test_delete_then_restore_brings_everything_back(client, make_user, run):
    owner, other = make_user(), make_user()
    bot = owner.bot("Front desk")
    client.post(f"/api/bots/{bot}/config", json={"aiApiKey": "sk-keep-me"}, headers=owner.h())

    async def seed():
        async with async_session() as db:
            conv = Conversation(bot_id=bot, visitor_session_id="s-restore", captured_data={"Name": "Asha"})
            db.add(conv)
            await db.flush()
            db.add_all([
                Message(conversation_id=conv.conversation_id, role="user", content="Do you open on Sunday?"),
                VoiceAgent(bot_id=bot, user_id=owner.id, greeting="Hello"),
                Campaign(user_id=owner.id, bot_id=bot, name="October list"),
                Subscription(user_id=owner.id, bot_id=bot, plan_name="1 Month Plan", price_paid=999,
                             end_date=datetime.utcnow() + timedelta(days=20)),
                Transaction(user_id=owner.id, bot_id=bot, amount=999, status="success"),
                CallLog(user_id=owner.id, bot_id=bot, summary="Asked about hours"),
                PhoneNumber(user_id=owner.id, number="+1 415 555 0123", e164="+14155550123", status="active", bot_id=bot),
            ])
            await db.commit()
    run(seed)

    assert client.delete(f"/api/bots/{bot}", headers=owner.h()).json()["restorable_days"] == 30

    async def state():
        async with async_session() as db:
            one = lambda q: db.execute(q)
            return {
                "bot": (await one(select(Bot.bot_id).where(Bot.bot_id == bot))).first() is not None,
                "conversations": len((await one(select(Conversation).where(Conversation.bot_id == bot))).scalars().all()),
                "messages": len((await one(select(Message).join(Conversation, Conversation.conversation_id == Message.conversation_id)
                                           .where(Conversation.bot_id == bot))).scalars().all()),
                "payments": len((await one(select(Transaction).where(Transaction.user_id == owner.id))).scalars().all()),
                "plan_linked": (await one(select(Subscription.bot_id).where(Subscription.user_id == owner.id))).scalar() == bot,
                "call_linked": (await one(select(CallLog.bot_id).where(CallLog.user_id == owner.id))).scalar() == bot,
                "number_linked": (await one(select(PhoneNumber.bot_id).where(PhoneNumber.user_id == owner.id))).scalar() == bot,
                "key": (await one(select(Bot.ai_api_key).where(Bot.bot_id == bot))).scalar(),
            }
    gone = run(state)
    assert gone["bot"] is False and gone["conversations"] == 0
    assert gone["payments"] == 1 and gone["plan_linked"] is False  # the payment survives, detached

    listed = client.get("/api/bots/deleted", headers=owner.h()).json()
    assert [(i["name"], i["conversations"]) for i in listed] == [("Front desk", 1)]
    item = listed[0]["id"]
    assert client.get("/api/bots/deleted", headers=other.h()).json() == []
    assert client.post(f"/api/bots/deleted/{item}/restore", headers=other.h()).status_code == 404

    assert client.post(f"/api/bots/deleted/{item}/restore", headers=owner.h()).json()["bot_id"] == bot
    back = run(state)
    assert back == {"bot": True, "conversations": 1, "messages": 1, "payments": 1, "plan_linked": True,
                    "call_linked": True, "number_linked": True, "key": "sk-keep-me"}
    assert client.get("/api/bots/deleted", headers=owner.h()).json() == []
    assert client.post(f"/api/bots/deleted/{item}/restore", headers=owner.h()).status_code == 404


def test_deleted_items_are_purged_after_30_days(client, make_user, run, monkeypatch):
    removed = []
    monkeypatch.setattr(vector_store, "delete_bot_knowledge", lambda bot_id: removed.append(bot_id))
    u = make_user()
    bot = u.bot()
    client.delete(f"/api/bots/{bot}", headers=u.h())

    async def age():
        async with async_session() as db:
            for item in (await db.execute(select(DeletedItem).where(DeletedItem.user_id == u.id))).scalars().all():
                item.expires_at = datetime.utcnow() - timedelta(minutes=1)
            await db.commit()
    run(age)
    assert run(recycle.purge_expired) >= 1
    assert client.get("/api/bots/deleted", headers=u.h()).json() == [] and bot in removed
