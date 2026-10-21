"""
Recently deleted: a deleted assistant can be restored for 30 days.

Deleting a bot removes its conversations, voice settings, questions, campaigns and call-back
jobs (database cascade). Before that happens we save those rows in a DeletedItem, and restore
puts them back exactly. Payments and subscriptions are never deleted: they're detached from the
bot (financial records must be kept) and re-attached on restore. Call logs, phone numbers and the
WhatsApp link are re-attached too. The bot's knowledge vectors are kept until the 30 days pass.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import Text, insert, select, type_coerce, update

from backend.models import (Bot, CallbackJob, CallLog, Campaign, Conversation, DeletedItem, IntegrationSettings,
                            KnowledgeGap, Message, PhoneNumber, Subscription, Transaction, VoiceAgent)
from secretbox import EncryptedText

logger = logging.getLogger(__name__)

KEEP_DAYS = 30
# Removed with the bot, so saved in full (in insert order).
OWNED = [Bot, Conversation, Message, VoiceAgent, KnowledgeGap, Campaign, CallbackJob]
# Kept, but pointing at the bot: re-attached on restore. (model, column, key column)
LINKED = [(CallLog, "bot_id", "id"), (PhoneNumber, "bot_id", "id"), (IntegrationSettings, "whatsapp_bot_id", "user_id"),
          (Subscription, "bot_id", "id"), (Transaction, "bot_id", "id")]


async def _rows(db, model, where) -> list[dict]:
    from ops.backup import _plain
    table = model.__table__
    cols = [type_coerce(c, Text).label(c.name) if isinstance(c.type, EncryptedText) else c for c in table.columns]
    return [{c.name: _plain(v) for c, v in zip(table.columns, row)} for row in (await db.execute(select(*cols).where(where))).all()]


async def archive_bot(db, bot: Bot, deleted_by: str) -> DeletedItem:
    """Save everything that goes away with this bot. Call before deleting it (same transaction)."""
    conv_ids = (await db.execute(select(Conversation.conversation_id).where(Conversation.bot_id == bot.bot_id))).scalars().all()
    tables = {
        "bots": await _rows(db, Bot, Bot.bot_id == bot.bot_id),
        "conversations": await _rows(db, Conversation, Conversation.bot_id == bot.bot_id),
        "messages": await _rows(db, Message, Message.conversation_id.in_(conv_ids)) if conv_ids else [],
        "voice_agents": await _rows(db, VoiceAgent, VoiceAgent.bot_id == bot.bot_id),
        "knowledge_gaps": await _rows(db, KnowledgeGap, KnowledgeGap.bot_id == bot.bot_id),
        "campaigns": await _rows(db, Campaign, Campaign.bot_id == bot.bot_id),
        "callback_jobs": await _rows(db, CallbackJob, CallbackJob.bot_id == bot.bot_id),
    }
    links = {}
    for model, column, key in LINKED:
        col = getattr(model, column)
        links[model.__tablename__] = [str(k) for k in (await db.execute(select(getattr(model, key)).where(col == bot.bot_id))).scalars().all()]
    # Payment records outlive the bot: detach them so the delete cascade can't remove them.
    for model in (Subscription, Transaction):
        await db.execute(update(model).where(model.bot_id == bot.bot_id).values(bot_id=None))
    item = DeletedItem(user_id=bot.user_id, kind="bot", ref_id=bot.bot_id, label=bot.bot_name, deleted_by=deleted_by,
                       payload={"tables": tables, "links": links}, expires_at=datetime.utcnow() + timedelta(days=KEEP_DAYS))
    db.add(item)
    return item


async def restore_bot(db, item: DeletedItem) -> str:
    """Put a deleted bot back with everything that was saved. Returns the bot id."""
    from ops.restore import _value
    if (await db.execute(select(Bot.bot_id).where(Bot.bot_id == item.ref_id))).first():
        raise ValueError("That assistant already exists")
    tables = (item.payload or {}).get("tables", {})
    for model in OWNED:
        rows = tables.get(model.__tablename__) or []
        if rows:
            table = model.__table__
            await db.execute(insert(table), [{c.name: _value(c, r.get(c.name)) for c in table.columns if c.name in r} for r in rows])
    for model, column, key in LINKED:
        ids = ((item.payload or {}).get("links") or {}).get(model.__tablename__) or []
        if ids:
            col = getattr(model, column)
            await db.execute(update(model).where(getattr(model, key).in_(ids), col.is_(None)).values({column: item.ref_id}))
    await db.delete(item)
    return item.ref_id


async def purge_expired() -> int:
    """Forget items deleted more than 30 days ago, and their knowledge vectors. Called by the scheduler."""
    import asyncio
    from database import async_session
    from vector_store import delete_bot_knowledge

    async with async_session() as db:
        items = (await db.execute(select(DeletedItem).where(DeletedItem.expires_at < datetime.utcnow()))).scalars().all()
        for item in items:
            if item.kind == "bot" and not (await db.execute(select(Bot.bot_id).where(Bot.bot_id == item.ref_id))).first():
                try:
                    await asyncio.to_thread(delete_bot_knowledge, item.ref_id)
                except Exception as e:
                    logger.warning(f"Couldn't remove knowledge vectors for a purged assistant: {e}")
            await db.delete(item)
        await db.commit()
    return len(items)
