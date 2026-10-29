"""
Socket.io wiring shared by all routers.

Rooms:
  admin_<owner_id>   dashboard users of a workspace (joined with a valid token)
  <visitor_session>  one chat visitor plus the agent who accepted them
  wa:<phone>         a WhatsApp customer; only that workspace's team may join

Who may do what:
  - A web visitor joins only their own room. Its name is a random id kept in their browser,
    so knowing it is the visitor's proof.
  - A dashboard user joins a visitor room only if the conversation belongs to a workspace they
    own or are an active member of, and only then can they speak as "agent" in that room.
  - WhatsApp rooms are named after phone numbers, which aren't secret, so visitors can't join them.
    The same customer can message several businesses on Nimmi, so an agent's socket is tied to their
    own workspace's conversation, and WhatsApp traffic uses a per-assistant room behind the scenes:
    one business never sees another's replies, and replies are saved to and sent from the right one.
"""
import logging
import time
from collections import defaultdict, deque
from typing import Optional

from sqlalchemy.future import select

from auth import user_for_token
from database import async_session
try:
    from backend.models import Bot, Conversation, Message, TeamMember
except ImportError:
    from models import Bot, Conversation, Message, TeamMember

logger = logging.getLogger(__name__)

sio = None  # set by main.py once the SocketManager exists
_agent_sids: dict = {}  # sid -> user_id for sockets that proved they are dashboard users
_agent_rooms: dict = defaultdict(set)  # sid -> visitor rooms where this socket may speak as the agent
_joined: dict = defaultdict(set)  # sid -> rooms the socket joined (it may only post to these)
_recent: dict = defaultdict(deque)  # sid -> times of recent messages, for flood protection
_agent_conv: dict = defaultdict(dict)  # sid -> {room: conversation id this agent is answering}
_actual: dict = defaultdict(dict)  # sid -> {room as the client names it: socket.io room actually used}

MAX_ROOM = 120
MAX_MESSAGE = 4000
FLOOD = (20, 10.0)  # at most 20 messages in 10 seconds per socket


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


async def _agent_conversation(user_id: str, room: str) -> Optional[Conversation]:
    """The conversation with this visitor in a workspace the user owns or works in, if any."""
    async with async_session() as db:
        workspaces = {user_id} | set((await db.execute(select(TeamMember.owner_id).where(
            TeamMember.member_id == user_id, TeamMember.status == "active"))).scalars().all())
        return (await db.execute(
            select(Conversation).join(Bot, Bot.bot_id == Conversation.bot_id)
            .where(Conversation.visitor_session_id == room, Bot.user_id.in_(workspaces))
            .order_by(Conversation.created_at.desc())
        )).scalars().first()


def socket_room(room: str, bot_id: str) -> str:
    """WhatsApp rooms are per phone number, which several businesses can share: keep each assistant's apart."""
    return f"{room}#{bot_id}" if room.startswith("wa:") else room


async def _token_user(token) -> Optional[str]:
    if not isinstance(token, str) or not token:
        return None
    async with async_session() as db:
        return await user_for_token(token, db)


def _flooding(sid: str) -> bool:
    limit, window = FLOOD
    now, q = time.monotonic(), _recent[sid]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False


async def relay_to_whatsapp(db, conv: Conversation, text: str, message_id: Optional[str] = None,
                            author_id: Optional[str] = None) -> None:
    """Send a Live chat reply (already saved as `message_id`) to the customer on WhatsApp, from the number they wrote
    to. A message WhatsApp refuses (e.g. outside its 24-hour window) is reported to the team's dashboards."""
    from sqlalchemy import update
    from backend.models import WhatsAppMessage, WhatsAppNumber
    from whatsapp import chats, outbound
    chat = await chats.for_conversation(db, conv.conversation_id)
    number = await db.get(WhatsAppNumber, chat.number_id) if chat and chat.number_id else None
    bot = (await db.execute(select(Bot).where(Bot.bot_id == conv.bot_id))).scalars().first()
    error = None
    if chat is None or number is None or number.status == "disconnected":
        error = "This WhatsApp number isn't connected any more."
    else:
        await db.execute(update(WhatsAppMessage).where(WhatsAppMessage.chat_id == chat.id, WhatsAppMessage.direction == "in",
                                                       WhatsAppMessage.handled.is_(False)).values(handled=True))
        chat.unread, chat.reply_due_at = 0, None
        await db.commit()
        sent = await outbound.send_text(number, chat, text, sent_by="team", author_id=author_id, message_id=message_id)
        error = sent.error
    if error and sio and bot:
        logger.warning(f"WhatsApp reply from Live chat not sent: {error}")
        await sio.emit("delivery_error", {"conversation_id": str(conv.conversation_id), "error": error[:300]},
                       room=f"admin_{bot.user_id}")


def register(socket_manager) -> None:
    global sio
    sio = socket_manager

    @socket_manager.on("join")
    async def handle_join(sid, data):
        data = data if isinstance(data, dict) else {}
        room = data.get("room")
        if not isinstance(room, str) or not room or len(room) > MAX_ROOM:
            return
        token = data.get("token")
        if room.startswith("admin_"):
            user_id = await _token_user(token)
            if not user_id or not await _can_join_admin_room(user_id, room[len("admin_"):]):
                logger.warning(f"Socket {sid} refused admin room")
                return
            _agent_sids[sid] = user_id
        elif token:
            # A dashboard user opening a conversation: only their own workspace's.
            user_id = await _token_user(token)
            conv = await _agent_conversation(user_id, room) if user_id else None
            if not conv:
                logger.warning(f"Socket {sid} refused visitor room")
                return
            _agent_sids[sid] = user_id
            _agent_rooms[sid].add(room)
            _agent_conv[sid][room] = conv.conversation_id
            _actual[sid][room] = socket_room(room, conv.bot_id)
        elif room.startswith("wa:"):
            return  # WhatsApp customers don't use sockets; their rooms are for the team only
        _joined[sid].add(room)
        await socket_manager.enter_room(sid, _actual[sid].get(room, room))

    @socket_manager.on("message")
    async def handle_message(sid, data):
        data = data if isinstance(data, dict) else {}
        room, message = data.get("room"), data.get("message")
        if not isinstance(room, str) or not isinstance(message, str) or not message.strip() or room.startswith("admin_"):
            return
        if room not in _joined.get(sid, ()) or _flooding(sid):
            return  # only rooms this socket was allowed to join
        message = message[:MAX_MESSAGE]
        # Only a dashboard user authorised for this conversation speaks as the agent.
        sender = "agent" if (data.get("sender") == "agent" and room in _agent_rooms.get(sid, ())) else "visitor"
        if room.startswith("wa:") and sender != "agent":
            return
        data = {"room": room, "message": message, "sender": sender}
        try:
            async with async_session() as db:
                if sender == "agent":  # the exact conversation this agent was authorised for
                    conv = (await db.execute(select(Conversation).where(
                        Conversation.conversation_id == _agent_conv[sid].get(room)))).scalars().first()
                else:  # a web visitor's own session (ids are random and per assistant)
                    conv = (await db.execute(
                        select(Conversation)
                        .where(Conversation.visitor_session_id == room)
                        .order_by(Conversation.created_at.desc())
                    )).scalars().first()
                if conv:
                    saved = Message(
                        conversation_id=conv.conversation_id,
                        role="assistant" if sender == "agent" else "user",
                        content=message,
                    )
                    db.add(saved)
                    await db.commit()
                    data["id"] = saved.id  # the widget also fetches replies; the id stops it showing one twice
                    if sender == "agent" and room.startswith("wa:"):
                        await relay_to_whatsapp(db, conv, message, message_id=saved.id, author_id=_agent_sids.get(sid))
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
        await socket_manager.emit("message", data, room=_actual.get(sid, {}).get(room, room))

    @socket_manager.on("disconnect")
    async def handle_disconnect(sid):
        for store in (_agent_sids, _agent_rooms, _joined, _recent, _agent_conv, _actual):
            store.pop(sid, None)


def is_agent_socket(sid: str) -> Optional[str]:
    return _agent_sids.get(sid)
