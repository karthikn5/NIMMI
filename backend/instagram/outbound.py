"""
Sending Instagram DMs, for the assistant and the team alike. Each message is kept before Meta is asked (a Message in the conversation and an
InstagramMessage "sending"), so the echo Meta sends back for it is recognised as Nimmi's own, even when it arrives before Meta's answer does
(inbound.py). Then it's sent, and marked sent with Meta's id, or failed with the reason, so the team sees what didn't go out. If Instagram says the
sign-in ended or access was taken away, the account shows its repair (Instagram > Settings).

Instagram's human agent tag lets a person reply up to 7 days after someone's last message. Only the team's replies may carry it: the assistant
never does, and asking for it on anything else is refused here, whatever called this.
"""
import logging
from typing import Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from backend.models import InstagramAccount, InstagramChat, InstagramMessage, Message, User
from database import async_session
from instagram import accounts, chats, graph, live

logger = logging.getLogger(__name__)


class TagRefused(ValueError):
    """The human agent tag was asked for on something that isn't a person's reply."""


async def send_text(account: InstagramAccount, chat: InstagramChat, text: str, *, sent_by: str, author_id: Optional[str] = None,
                    quick_replies: Optional[list[str]] = None, message_id: Optional[str] = None, human_agent: bool = False) -> InstagramMessage:
    """A DM (with quick replies, if given). `message_id`: the conversation already has it (Live chat). `human_agent`: a person's reply after 24 hours."""
    if human_agent and (sent_by != "team" or not author_id):
        raise TagRefused("Only a person's reply may use Instagram's human agent tag")
    text = graph.fit(text)
    shown = text + ("\n" + " | ".join(f"[{q}]" for q in quick_replies) if quick_replies else "")
    w = await _keep(chat, shown, kind="choice" if quick_replies else "text", sent_by=sent_by, author_id=author_id, message_id=message_id,
                    tag="human_agent" if human_agent else None)
    mid, error = None, None
    try:
        mid = await graph.send(account.ig_id, account.access_token, chat.igsid, graph.text_message(text, quick_replies),
                               tag=graph.HUMAN_AGENT if human_agent else None)
    except graph.IGError as e:
        error = str(e)
        logger.warning(f"Instagram message to ...{chat.igsid[-4:]} not sent: {e}")
        await accounts.trouble(account.id, e)
    return await _sent(account, chat, w, mid, error, author_id)


async def _keep(chat: InstagramChat, text: str, *, kind: str, sent_by: str, author_id: Optional[str],
                message_id: Optional[str], tag: Optional[str]) -> InstagramMessage:
    at = chats.now()
    async with async_session() as db:
        m = await db.get(Message, message_id) if message_id else None
        if m is None:
            m = Message(conversation_id=chat.conversation_id, role="assistant", content=text[:8000], author_id=author_id, timestamp=at)
            db.add(m)
            await db.flush()
        w = InstagramMessage(chat_id=chat.id, message_id=m.id, direction="out", kind=kind, sent_by=sent_by, author_id=author_id, status="sending",
                             tag=tag, handled=True, created_at=at)
        db.add(w)
        row = await db.get(InstagramChat, chat.id)
        row.last_message_at = at
        await db.commit()
        await db.refresh(w)
    return w


async def _sent(account: InstagramAccount, chat: InstagramChat, w: InstagramMessage, mid: Optional[str], error: Optional[str],
                author_id: Optional[str]) -> InstagramMessage:
    async with async_session() as db:
        if error:
            await db.execute(update(InstagramMessage).where(InstagramMessage.id == w.id).values(status="failed", error=error[:500])
                             .execution_options(synchronize_session=False))
        else:
            # The echo may have named it already (inbound.py): its id stays. If the echo couldn't tell it was this send and kept it apart, that row has the id.
            try:
                await db.execute(update(InstagramMessage).where(InstagramMessage.id == w.id, InstagramMessage.mid.is_(None))
                                 .values(mid=(mid or None) and mid[:255]).execution_options(synchronize_session=False))
                await db.commit()
            except IntegrityError:
                await db.rollback()
            await db.execute(update(InstagramMessage).where(InstagramMessage.id == w.id, InstagramMessage.status == "sending")
                             .values(status="sent").execution_options(synchronize_session=False))
        await db.commit()
        w = await db.get(InstagramMessage, w.id)
        m = await db.get(Message, w.message_id) if w.message_id else None
        row = await db.get(InstagramChat, chat.id)
        user = await db.get(User, author_id) if author_id else None
    if m is not None:
        await live.message(account.user_id, row, m, w, user.name if user else None)
    return w
