"""
Socket.io wiring shared by all routers.

Rooms:
  admin_<owner_id>   dashboard users of a workspace (joined with a valid token)
  <visitor_session>  one chat visitor plus the agent who accepted them
"""
import logging
from typing import Optional

from sqlalchemy.future import select

from auth import decode_token
from database import async_session
from backend.models import Bot, Conversation, IntegrationSettings, Message, TeamMember

logger = logging.getLogger(__name__)

sio = None  # set by main.py once the SocketManager exists
_agent_sids: dict = {}  # sid -> user_id for sockets that proved they are dashboard users


async def emit(event: str, data: dict, room: str) -> None:
    if sio is None:
        return
    try:
        await sio.emit(event, data, room=room)
    except Exception as e:  # never let a socket hiccup fail an HTTP request
        logger.warning(f"Socket emit failed ({event} -> {room}): {e}")


async def notify_owner(owner_id: str, event: str, data: dict) -> None:
    await emit(event, data, room=f"admin_{owner_id}")


async def _can_join_admin_room(user_id: str, owner_id: str) -> bool:
    if user_id == owner_id:
        return True
    async with async_session() as db:
        member = (await db.execute(
            select(TeamMember.id).where(
                TeamMember.owner_id == owner_id,
                TeamMember.member_id == user_id,
                TeamMember.status == "active",
            )
        )).scalar_one_or_none()
        return member is not None


async def _relay_to_whatsapp(db, conv: Conversation, phone: str, text: str) -> None:
    """Send a dashboard agent's reply to the customer's WhatsApp, from the workspace's own number."""
    from notify import channels
    bot = (await db.execute(select(Bot).where(Bot.bot_id == conv.bot_id))).scalars().first()
    settings = (await db.execute(select(IntegrationSettings).where(
        IntegrationSettings.user_id == bot.user_id))).scalars().first() if bot else None
    if not settings or not settings.whatsapp_phone_number_id:
        return
    try:
        await channels.send_whatsapp_text(phone, text, phone_number_id=settings.whatsapp_phone_number_id,
                                          token=settings.whatsapp_access_token)
    except Exception as e:  # e.g. outside WhatsApp's 24-hour reply window
        logger.warning(f"WhatsApp relay to {phone[-4:]} failed: {e}")
        if sio:
            await sio.emit("delivery_error", {"conversation_id": str(conv.conversation_id), "error": str(e)[:300]},
                           room=f"admin_{bot.user_id}")


def register(socket_manager) -> None:
    global sio
    sio = socket_manager

    @socket_manager.on("join")
    async def handle_join(sid, data):
        room = (data or {}).get("room")
        if not room:
            return
        if room.startswith("admin_"):
            user_id = decode_token((data or {}).get("token") or "")
            if not user_id or not await _can_join_admin_room(user_id, room[len("admin_"):]):
                logger.warning(f"Socket {sid} refused admin room {room}")
                return
            _agent_sids[sid] = user_id
        elif (data or {}).get("token"):
            # An agent joining a visitor room: remember they are authenticated.
            user_id = decode_token(data["token"])
            if user_id:
                _agent_sids[sid] = user_id
        await socket_manager.enter_room(sid, room)

    @socket_manager.on("message")
    async def handle_message(sid, data):
        room = (data or {}).get("room")
        message = (data or {}).get("message")
        if not room or not message or room.startswith("admin_"):
            return
        # Only authenticated dashboard sockets may speak as the agent.
        sender = "agent" if (data.get("sender") == "agent" and sid in _agent_sids) else "visitor"
        data = {**data, "sender": sender}
        try:
            async with async_session() as db:
                conv = (await db.execute(
                    select(Conversation)
                    .where(Conversation.visitor_session_id == room)
                    .order_by(Conversation.created_at.desc())
                )).scalars().first()
                if conv:
                    db.add(Message(
                        conversation_id=conv.conversation_id,
                        role="assistant" if sender == "agent" else "user",
                        content=message,
                    ))
                    await db.commit()
                    if sender == "agent" and room.startswith("wa:"):
                        await _relay_to_whatsapp(db, conv, room[3:], message)
                    if sender != "agent" and conv.handoff_status == "pending":
                        bot = (await db.execute(select(Bot).where(Bot.bot_id == conv.bot_id))).scalars().first()
                        if bot:
                            await notify_owner(bot.user_id, "handoff_requested", {
                                "conversation_id": str(conv.conversation_id),
                                "bot_id": bot.bot_id,
                                "bot_name": bot.bot_name,
                                "session_id": room,
                                "message": message,
                            })
        except Exception as e:
            logger.error(f"Error saving socket message: {e}")
        await socket_manager.emit("message", data, room=room)

    @socket_manager.on("disconnect")
    async def handle_disconnect(sid):
        _agent_sids.pop(sid, None)


def is_agent_socket(sid: str) -> Optional[str]:
    return _agent_sids.get(sid)
