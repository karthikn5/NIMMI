"""
What Meta's Instagram webhooks bring, kept before Meta is told "received" (a crash means Meta sends it again, never a lost message):

- a DM: saved in the person's chat (each Meta id once, whichever server process gets it), shown in the Inbox, and the assistant's answer made due
  (replies.py). A first DM makes them a lead and reads their profile, as Meta allows once they've written (contacts.py);
- a tap on a quick reply or an ice breaker: their answer, as if typed;
- echoes, what the account sent: Nimmi's own sends are recognised (outbound.py keeps each one before Meta answers); anything else was written in the
  Instagram app, so the assistant leaves that chat to the person for a while and an echo is never answered;
- reactions, "seen", edits and unsends: shown on the messages;
- the ad or ig.me link that opened a chat: kept once on the conversation; an ad's first message opens Instagram's 7-day window.
"""
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from backend.models import InstagramAccount, InstagramChat, InstagramMessage, Message
from database import async_session
from instagram import accounts, chats, live, settings
from leads import origin as lead_origin
from notify.events import fire_and_forget
from realtime import notify_owner

logger = logging.getLogger(__name__)

# Meta's attachment types (webhook examples, read 3 November 2026), as the conversation shows them and as kept.
PLACEHOLDER = {"image": "(photo)", "video": "(video)", "audio": "(voice message)", "file": "(file)", "share": "(shared a post)", "ig_post": "(shared a post)",
               "ig_reel": "(shared a reel)", "reel": "(shared a reel)", "story_mention": "(mentioned you in their story)", "story": "(shared a story)",
               "ig_story": "(shared a story)", "media": "(sent a photo or video)",
               "ephemeral": "(sent a photo or video that disappears: it can't be seen here)"}
KINDS = {"image": "image", "video": "video", "audio": "audio", "file": "file", "share": "share", "ig_post": "share", "ig_reel": "reel", "reel": "reel",
         "story_mention": "story_mention", "story": "share", "ig_story": "share", "media": "image", "ephemeral": "unsupported"}
OWN_ECHO = timedelta(minutes=2)  # an echo this soon after one of Nimmi's own sends with no id yet is that send


def describe(message: dict) -> tuple[str, str, Optional[dict], Optional[str]]:
    """(kind, text for the conversation, file details, the message or story it answers). Files are only described here: replies.py fetches and
    understands them when it answers. A shared post's address is kept with it for the team, not put in the text (Meta's CDN addresses expire)."""
    text = str(message.get("text") or "").strip()
    reply = message.get("reply_to") if isinstance(message.get("reply_to"), dict) else {}
    story = reply.get("story") if isinstance(reply.get("story"), dict) else None
    reply_to = str((story or {}).get("id") or reply.get("mid") or "")[:255] or None
    if message.get("is_unsupported"):
        return "unsupported", "(a kind of message Instagram can't show here)", None, reply_to
    if isinstance(message.get("quick_reply"), dict):
        return "choice", text or "(tapped a choice)", None, reply_to
    found = message.get("attachments")
    found = [found] if isinstance(found, dict) else [a for a in (found or []) if isinstance(a, dict)]
    if found:
        first = found[0]
        raw = str(first.get("type") or "media")
        url = str((first.get("payload") or {}).get("url") or "")[:2000] if isinstance(first.get("payload"), dict) else ""
        label = PLACEHOLDER.get(raw, "(sent something Instagram can't show here)")
        if len(found) > 1:
            label += f" (and {len(found) - 1} more)"
        return KINDS.get(raw, "unsupported"), f"{label} {text}".strip(), {"type": raw, **({"url": url} if url else {})}, reply_to
    if story is not None:
        return "story_reply", f"(replied to your story) {text}".strip(), None, reply_to
    return "text", text or "(empty message)", None, reply_to


async def handle(account: InstagramAccount, event: dict) -> None:
    """One item of a webhook entry's "messaging" list."""
    if not isinstance(event, dict):
        return
    sender = str((event.get("sender") or {}).get("id") or "")
    recipient = str((event.get("recipient") or {}).get("id") or "")
    msg = event.get("message")
    if isinstance(msg, dict):
        if msg.get("is_self"):
            return  # a test message to the account itself
        if msg.get("is_echo") or (sender and sender == account.ig_id):
            await echo(account, recipient, msg)
        elif msg.get("is_deleted"):
            await unsent(account, sender, msg)
        else:
            await message(account, sender, msg)
    elif isinstance(event.get("postback"), dict):  # an ice breaker or a button
        p = event["postback"]  # an ig.me link's ref comes with the first tap in a new chat (Meta's ig.me page)
        await message(account, sender, {"mid": p.get("mid") or f"postback:{sender}:{event.get('timestamp')}",
                                        "text": p.get("title") or p.get("payload") or "(tapped a button)", "quick_reply": {"payload": p.get("payload")},
                                        **({"referral": p["referral"]} if isinstance(p.get("referral"), dict) else {})})
    elif isinstance(event.get("reaction"), dict):
        await reaction(account, sender, event["reaction"], event.get("timestamp"))
    elif isinstance(event.get("read"), dict):
        await seen(account, sender, event["read"])
    elif isinstance(event.get("message_edit"), dict):
        await edited(account, event["message_edit"])
    elif isinstance(event.get("referral"), dict):
        await referral(account, sender, event["referral"])


async def _known(mid: str) -> bool:
    async with async_session() as db:
        return (await db.execute(select(InstagramMessage.id).where(InstagramMessage.mid == mid))).first() is not None


async def message(account: InstagramAccount, igsid: str, msg: dict) -> Optional[str]:
    """Keep their DM. Returns its chat's id when it was new, None for a repeat or one without a sender."""
    mid = str(msg.get("mid") or "")[:255]
    if not mid or not igsid or await _known(mid):
        return None
    kind, text, media, reply_to = describe(msg)
    chat = await chats.find_or_create(account, igsid)
    async with async_session() as db:
        chat = await db.get(InstagramChat, chat.id)
        account = await db.get(InstagramAccount, account.id)
        bot = await accounts.assistant(db, account)
        if bot is None:
            logger.warning(f"Instagram account {account.ig_id} has no assistant to answer")
            return None
        conv, new = await chats.conversation(db, chat, bot)
        at = chats.now()
        came = lead_origin.from_instagram(msg.get("referral"))
        if came and not conv.origin:  # kept once: what brought them stays theirs
            conv.origin = came
        if came and came.get("channel") == "instagram_ad":  # Meta: a first message after a Click-to-Direct ad gives up to 7 days
            chat.ad_window_until = at + chats.AD_WINDOW
        m = Message(conversation_id=conv.conversation_id, role="user", content=text[:8000], timestamp=at)
        db.add(m)
        await db.flush()
        w = InstagramMessage(chat_id=chat.id, message_id=m.id, mid=mid, direction="in", kind=kind, sent_by="customer", media=media, reply_to=reply_to,
                             status="received", handled=False, created_at=at)
        db.add(w)
        chat.last_inbound_at = chat.last_message_at = at
        chat.unread = (chat.unread or 0) + 1
        chat.status = "open"
        account.last_inbound_at = at
        due = None
        if account.ai_enabled and not chats.ai_paused(chat) and conv.handoff_status != "human":
            due = at + timedelta(seconds=settings.clean(account.settings)["wait_seconds"])
            chat.reply_due_at = due
        try:
            await db.commit()
        except IntegrityError:  # the same message, kept a moment ago by another server process
            await db.rollback()
            return None
        conv_id, session, owner_id = conv.conversation_id, conv.visitor_session_id, account.user_id
    from instagram import contacts
    if new:
        fire_and_forget(contacts.first_dm(chat.id))  # a lead, with the name Instagram gives once they've written
    else:
        from leads.contact import WROTE, stop_for_chat
        fire_and_forget(stop_for_chat(conv_id, WROTE))  # they answered: whatever was chasing them stops
    await live.message(owner_id, chat, m, w)
    await notify_owner(owner_id, "new_message", {"conversation_id": conv_id, "bot_id": bot.bot_id, "session_id": session, "role": "user",
                                                 "message": text, "created_at": at.timestamp()})
    if due is not None:
        from instagram import replies
        replies.schedule(chat.id, due)
    return chat.id


async def echo(account: InstagramAccount, igsid: str, msg: dict) -> None:
    """What the account sent. Nimmi's own send (kept before Meta answered, so without an id yet) takes the id; anything else was written in the
    Instagram app: kept, and the assistant leaves that chat to the person. Never answered."""
    mid = str(msg.get("mid") or "")[:255]
    if not mid or not igsid or await _known(mid):
        return
    text = str(msg.get("text") or "").strip()
    async with async_session() as db:
        chat = (await db.execute(select(InstagramChat).where(InstagramChat.account_id == account.id, InstagramChat.igsid == igsid))).scalars().first()
        if chat is not None:
            ours = (await db.execute(select(InstagramMessage, Message.content).outerjoin(Message, Message.id == InstagramMessage.message_id).where(
                InstagramMessage.chat_id == chat.id, InstagramMessage.direction == "out", InstagramMessage.mid.is_(None),
                InstagramMessage.status.in_(("sending", "sent")), InstagramMessage.created_at >= chats.now() - OWN_ECHO)
                .order_by(InstagramMessage.created_at))).all()
            pick = next((w for w, said in ours if text and (said or "").startswith(text[:50])), None) or (ours[0][0] if len(ours) == 1 else None)
            if pick is not None:
                pick.mid = mid
                pick.status = "sent" if pick.status == "sending" else pick.status
                try:
                    await db.commit()
                except IntegrityError:
                    await db.rollback()
                return
    from instagram import comments
    if await comments.recent_own_send(account, mid, text):
        return  # a private reply to a comment that Nimmi is sending now: comments.py keeps it
    kind, shown, media, reply_to = describe(msg)
    chat = await chats.find_or_create(account, igsid)
    async with async_session() as db:
        chat = await db.get(InstagramChat, chat.id)
        account = await db.get(InstagramAccount, account.id)
        bot = await accounts.assistant(db, account)
        if bot is None:
            return
        conv, _ = await chats.conversation(db, chat, bot)
        at = chats.now()
        m = Message(conversation_id=conv.conversation_id, role="assistant", content=shown[:8000], timestamp=at)
        db.add(m)
        await db.flush()
        w = InstagramMessage(chat_id=chat.id, message_id=m.id, mid=mid, direction="out", kind=kind, sent_by="app", media=media, reply_to=reply_to,
                             status="sent", handled=True, created_at=at)
        db.add(w)
        chat.last_message_at = at
        chat.ai_paused_until = at + timedelta(hours=settings.clean(account.settings)["pause_hours"])
        chat.reply_due_at = None
        await db.execute(update(InstagramMessage).where(InstagramMessage.chat_id == chat.id, InstagramMessage.direction == "in",
                                                        InstagramMessage.handled.is_(False)).values(handled=True))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return
        conv_id, owner_id = conv.conversation_id, account.user_id
    from leads.contact import stop_for_chat
    fire_and_forget(stop_for_chat(conv_id))  # the team wrote from the Instagram app: they have this person now
    await live.message(owner_id, chat, m, w)


async def _chat(account: InstagramAccount, igsid: str):
    async with async_session() as db:
        return (await db.execute(select(InstagramChat).where(InstagramChat.account_id == account.id, InstagramChat.igsid == igsid))).scalars().first()


async def reaction(account: InstagramAccount, igsid: str, r: dict, timestamp=None) -> None:
    """A reaction to a message, shown in the chat. It doesn't open Instagram's window and isn't answered."""
    chat = await _chat(account, igsid) if igsid else None
    if chat is None or not chat.conversation_id:
        return
    key = f"r:{r.get('mid')}:{igsid}:{r.get('action')}:{timestamp}"[:255]
    if await _known(key):
        return
    shown = f"(reacted {r['emoji']} to a message)" if r.get("action") == "react" and r.get("emoji") else (
        "(reacted to a message)" if r.get("action") == "react" else "(removed a reaction)")
    async with async_session() as db:
        at = chats.now()
        m = Message(conversation_id=chat.conversation_id, role="user", content=shown, timestamp=at)
        db.add(m)
        await db.flush()
        w = InstagramMessage(chat_id=chat.id, message_id=m.id, mid=key, direction="in", kind="reaction", sent_by="customer",
                             reply_to=str(r.get("mid") or "")[:255] or None, status="received", handled=True, created_at=at)
        db.add(w)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return
    await live.message(account.user_id, chat, m, w)


async def seen(account: InstagramAccount, igsid: str, read: dict) -> None:
    """They saw the account's messages, up to this one."""
    chat = await _chat(account, igsid) if igsid else None
    if chat is None:
        return
    async with async_session() as db:
        upto = (await db.execute(select(InstagramMessage.created_at).where(InstagramMessage.mid == str(read.get("mid") or ""),
                                                                           InstagramMessage.chat_id == chat.id))).scalar_one_or_none()
        upto = upto or chats.now()
        done = await db.execute(update(InstagramMessage).where(InstagramMessage.chat_id == chat.id, InstagramMessage.direction == "out",
                                                               InstagramMessage.status == "sent", InstagramMessage.created_at <= upto)
                                .values(status="read").execution_options(synchronize_session=False))
        await db.commit()
    if done.rowcount:
        await live.chat_changed(account.user_id, chat)


async def edited(account: InstagramAccount, edit: dict) -> None:
    async with async_session() as db:
        w = (await db.execute(select(InstagramMessage).where(InstagramMessage.mid == str(edit.get("mid") or "")))).scalars().first()
        chat = await db.get(InstagramChat, w.chat_id) if w else None
        if w is None or chat is None or chat.account_id != account.id or w.direction != "in" or not w.message_id:
            return
        m = await db.get(Message, w.message_id)
        m.content = f"{str(edit.get('text') or '').strip()} (edited)"[:8000]
        await db.commit()
    await live.message(account.user_id, chat, m, w)


async def unsent(account: InstagramAccount, igsid: str, msg: dict) -> None:
    """They unsent a message: its words go, and if it was waiting for an answer, it isn't answered."""
    async with async_session() as db:
        w = (await db.execute(select(InstagramMessage).where(InstagramMessage.mid == str(msg.get("mid") or "")))).scalars().first()
        chat = await db.get(InstagramChat, w.chat_id) if w else None
        if w is None or chat is None or chat.account_id != account.id or chat.igsid != igsid:
            return
        m = await db.get(Message, w.message_id) if w.message_id else None
        if m is not None:
            m.content = "(unsent a message)"
        w.status, w.media, w.handled = "deleted", None, True
        await db.flush()
        waiting = (await db.execute(select(InstagramMessage.id).where(InstagramMessage.chat_id == chat.id, InstagramMessage.direction == "in",
                                                                      InstagramMessage.handled.is_(False)))).first()
        if waiting is None:
            chat.reply_due_at = None
        await db.commit()
    if m is not None:
        await live.message(account.user_id, chat, m, w)


async def referral(account: InstagramAccount, igsid: str, ref: dict) -> None:
    """An ig.me link or an ad opened an existing chat: kept on the conversation if nothing brought them before, and, as Meta's ig.me page says, it
    restarts the 24-hour window."""
    chat = await _chat(account, igsid) if igsid else None
    came = lead_origin.from_instagram(ref)
    if chat is None or not chat.conversation_id:
        return
    from backend.models import Conversation
    async with async_session() as db:
        row = await db.get(InstagramChat, chat.id)
        row.last_inbound_at = chats.now()
        conv = await db.get(Conversation, chat.conversation_id)
        if conv is not None and came and not conv.origin:
            conv.origin = came
        await db.commit()
