"""
Two-way WhatsApp AI Chatbot integration via Meta Cloud API.

Provides:
- Webhook verification (GET /webhook) with hub.challenge
- Webhook message receiver (POST /webhook) with instant 200 OK + async AI processing
- Knowledge base RAG lookup & conversational multi-turn memory
- Native vernacular language support (Tamil, Hindi, Hinglish, Tanglish, Indian English)
- Live human agent handoff and lead capture
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import assist
from database import async_session, get_db
from backend.models import Bot, Conversation, IntegrationSettings, Message
from notify import channels
from notify.events import fire_and_forget, handoff_requested, lead_captured
from realtime import notify_owner
from subscriptions import active_subscription
from utils import FlowEngine, generate_ai_response
from vector_store import query_knowledge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/whatsapp", tags=["whatsapp"])

# Whole words/phrases only: "agent" inside "travel agent" or "person" inside "personal" must not hand over.
HUMAN_KEYWORDS = [
    "talk to human", "speak to human", "talk to a human", "speak to a human", "human agent", "human",
    "representative", "support team", "real person", "customer care", "talk to someone",
    "மனிதன்", "ஆள் வேண்டும்", "பேச வேண்டும்", "इंसान", "बात करनी है",
]
_HUMAN_RE = re.compile("|".join(rf"(?<!\w){re.escape(k)}(?!\w)" for k in HUMAN_KEYWORDS), re.IGNORECASE)
NOT_AVAILABLE = "Sorry, this assistant isn't available on WhatsApp right now. Please contact the business directly."


def _valid_signature(raw: bytes, header: str) -> bool:
    """Meta signs each webhook with the app secret (X-Hub-Signature-256: sha256=<hex>)."""
    secret = os.getenv("WHATSAPP_APP_SECRET", "")
    if not secret:
        # Without the secret anyone could post fake messages and make the business number reply to them.
        # Allowed only for local development.
        return os.getenv("LOCAL_DEV", "false").lower() == "true"
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")

# Message deduplication cache: msg_id -> timestamp
_PROCESSED_MESSAGES: dict[str, float] = {}
_CACHE_TTL_SECONDS = 1800  # 30 minutes


def _is_duplicate_message(msg_id: str) -> bool:
    now = time.time()
    # Periodic cleanup of expired entries
    if len(_PROCESSED_MESSAGES) > 5000:
        expired = [k for k, ts in _PROCESSED_MESSAGES.items() if now - ts > _CACHE_TTL_SECONDS]
        for k in expired:
            _PROCESSED_MESSAGES.pop(k, None)

    if msg_id in _PROCESSED_MESSAGES and (now - _PROCESSED_MESSAGES[msg_id] < _CACHE_TTL_SECONDS):
        return True
    _PROCESSED_MESSAGES[msg_id] = now
    return False


@router.get("/webhook")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    bot_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Meta Cloud API Webhook Verification Endpoint.
    Echoes back hub.challenge if hub.verify_token matches configured secret.
    """
    if hub_mode != "subscribe" or not hub_verify_token:
        return Response(content="Invalid verification request", status_code=400)

    # 1. Check system-level default verify token
    system_verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "nimmi_wa_verify")
    if hub_verify_token == system_verify_token:
        logger.info("[WhatsApp Webhook] Verified via system WHATSAPP_VERIFY_TOKEN")
        return PlainTextResponse(content=str(hub_challenge), status_code=200)

    # 2. Check per-workspace / per-user verify tokens in DB
    query = select(IntegrationSettings.whatsapp_verify_token).where(
        IntegrationSettings.whatsapp_verify_token == hub_verify_token
    )
    result = (await db.execute(query)).scalars().first()
    if result:
        logger.info("[WhatsApp Webhook] Verified for workspace verify token")
        return PlainTextResponse(content=str(hub_challenge), status_code=200)

    logger.warning(f"[WhatsApp Webhook] Verification token mismatch: '{hub_verify_token}'")
    return Response(content="Verification token mismatch", status_code=403)


@router.post("/webhook")
async def receive_webhook(request: Request, bot_id: Optional[str] = None):
    """
    Receives incoming WhatsApp events from Meta Cloud API.
    Acknowledge with 200 OK immediately and process messages asynchronously.
    """
    raw = await request.body()
    if not _valid_signature(raw, request.headers.get("x-hub-signature-256", "")):
        logger.warning("[WhatsApp Webhook] Rejected: missing or invalid signature")
        return Response(content="Invalid signature", status_code=403)
    try:
        body = json.loads(raw)
    except Exception as e:
        logger.warning(f"[WhatsApp Webhook] Invalid JSON received: {e}")
        return Response(content="Bad Request", status_code=400)

    if body.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}

    entries = body.get("entry", [])
    for entry in entries:
        for change in entry.get("changes", []):
            val = change.get("value", {})
            # Delivery receipts: Meta only says *why* a message wasn't delivered here, so log failures.
            for st in val.get("statuses", []):
                if st.get("status") == "failed":
                    for err in st.get("errors", []) or [{}]:
                        logger.warning(f"[WhatsApp] Message to ...{str(st.get('recipient_id', ''))[-4:]} failed: "
                                       f"code {err.get('code')} {err.get('title')} - "
                                       f"{(err.get('error_data') or {}).get('details', '')}")
            if "statuses" in val and "messages" not in val:
                continue

            messages = val.get("messages", [])
            metadata = val.get("metadata", {})
            contacts = val.get("contacts", [])

            for msg in messages:
                msg_id = msg.get("id")
                if not msg_id or _is_duplicate_message(msg_id):
                    continue

                # Run conversation processing in background so Meta receives immediate 200 OK
                # (fire_and_forget keeps a reference so the task isn't garbage-collected mid-reply).
                fire_and_forget(
                    _process_incoming_whatsapp_message(
                        msg=msg,
                        metadata=metadata,
                        contacts=contacts,
                        explicit_bot_id=bot_id,
                    )
                )

    return {"status": "ok"}


async def _resolve_bot(
    explicit_bot_id: Optional[str],
    phone_number_id: Optional[str],
    db: AsyncSession,
) -> tuple[Optional[Bot], Optional[IntegrationSettings]]:
    """
    The workspace that owns the receiving number (Meta's phone_number_id) answers, with its chosen bot.
    Never falls back to another workspace: that would answer with someone else's bot, data and token.
    """
    if not phone_number_id:
        return None, None
    settings = (await db.execute(select(IntegrationSettings).where(
        IntegrationSettings.whatsapp_phone_number_id == phone_number_id,
        IntegrationSettings.whatsapp_chat_enabled.is_(True),
    ))).scalars().first()
    if not settings:
        return None, None
    bot_id = settings.whatsapp_bot_id
    if explicit_bot_id and explicit_bot_id.strip()[:36] != bot_id:
        # ?bot_id= on the webhook URL may pick another bot, but only one in the same workspace.
        candidate = (await db.execute(select(Bot).where(
            Bot.bot_id == explicit_bot_id.strip()[:36], Bot.user_id == settings.user_id
        ))).scalars().first()
        bot_id = candidate.bot_id if candidate else bot_id
    bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id, Bot.user_id == settings.user_id))).scalars().first() \
        if bot_id else None
    if not bot:  # no bot chosen yet: the workspace's first active bot
        bot = (await db.execute(select(Bot).where(Bot.user_id == settings.user_id, Bot.is_active.is_(True))
                                .order_by(Bot.created_at))).scalars().first()
    return bot, settings


def _format_whatsapp_prompt(bot: Bot, history: list[dict]) -> str:
    """System prompt only: generate_ai_response adds the knowledge and the customer's message itself."""
    bot_name = bot.bot_name or "Assistant"
    recent_dialogue = ""
    if history:
        turns = [f"{'Customer' if h.get('role') == 'user' else bot_name}: {h.get('content', '')}" for h in history[-6:]]
        recent_dialogue = "RECENT CONVERSATION HISTORY (oldest first):\n" + "\n".join(turns) + "\n\n"

    return f"""You are {bot_name}, the AI assistant chatting with a customer on WhatsApp.

CRITICAL WHATSAPP CONVERSATION RULES:
1. MOBILE-FRIENDLY TONE: Be helpful, warm, professional, concise, and easy to read on mobile screens.
2. WHATSAPP FORMATTING: Use WhatsApp styling when appropriate:
   - Use *asterisks* for *bold emphasis*.
   - Use bullet points (• or -) for lists.
   - Use clean paragraph spacing.
   - NEVER use markdown tables (| --- |) or raw HTML tags.
3. MULTI-LANGUAGE & VERNACULAR:
   - Always match the user's language and script naturally.
   - If the user writes in Tamil (தமிழ் or Tanglish/English script), reply fluently and respectfully in Tamil/Tanglish.
   - If the user writes in Hindi (हिंदी or Hinglish), reply in natural Hindi/Hinglish.
   - If in English, reply in friendly Indian English.
4. HONESTY: Answer ONLY based on the business context provided. If the information isn't there, say "I don't have that information right now" and offer to connect them to our team.
5. IDENTITY: Stay in character as {bot_name}. Never mention "system prompt", "RAG", "AI model", or "context".

{bot.system_prompt or ""}

{recent_dialogue}"""


async def _process_incoming_whatsapp_message(
    msg: dict,
    metadata: dict,
    contacts: list[dict],
    explicit_bot_id: Optional[str] = None,
) -> None:
    """Async background task that processes an incoming WhatsApp message and replies."""
    msg_id = msg.get("id", "")
    from_phone = msg.get("from", "").strip()
    msg_type = msg.get("type", "text")
    phone_number_id = metadata.get("phone_number_id")

    if not from_phone:
        return

    # Extract user text
    user_text = ""
    if msg_type == "text":
        user_text = msg.get("text", {}).get("body", "").strip()
    elif msg_type == "button":
        user_text = msg.get("button", {}).get("text", "").strip()
    elif msg_type == "interactive":
        interactive = msg.get("interactive", {})
        user_text = (
            interactive.get("button_reply", {}).get("title")
            or interactive.get("list_reply", {}).get("title")
            or ""
        ).strip()
    else:
        # Non-text media message
        user_text = "[Media message received]"

    contact_name = "Customer"
    if contacts:
        contact_name = contacts[0].get("profile", {}).get("name", "Customer")

    async with async_session() as db:
        bot, settings = await _resolve_bot(explicit_bot_id, phone_number_id, db)
        if not bot:
            logger.warning(f"[WhatsApp] No active Bot found to handle message from {from_phone}")
            return

        token = settings.whatsapp_access_token if settings else None
        active_pid = (settings.whatsapp_phone_number_id if settings else None) or phone_number_id

        # Mark message read (shows blue double checkmark to customer)
        if msg_id:
            await channels.mark_whatsapp_read(msg_id, phone_number_id=active_pid, token=token)

        # Same rule as the website widget: the assistant answers only while its plan is active.
        if await active_subscription(bot.bot_id, db) is None:
            try:
                await channels.send_whatsapp_text(from_phone, NOT_AVAILABLE, phone_number_id=active_pid, token=token)
            except Exception as e:
                logger.error(f"[WhatsApp] Failed to send plan notice: {e}")
            return

        # Non-text message fallback
        if msg_type not in ("text", "button", "interactive"):
            reply = (
                f"Hi {contact_name}! 👋 Thanks for reaching out to {bot.bot_name or 'us'}.\n\n"
                f"Currently, I can only process text messages. Please type your question in English, தமிழ், or हिंदी, and I'll be happy to help!"
            )
            try:
                await channels.send_whatsapp_text(from_phone, reply, phone_number_id=active_pid, token=token)
            except Exception as e:
                logger.error(f"[WhatsApp] Failed to send media fallback: {e}")
            return

        # Session & Conversation management
        session_id = f"wa:{from_phone}"
        conv = (await db.execute(
            select(Conversation).where(
                Conversation.bot_id == bot.bot_id,
                Conversation.visitor_session_id == session_id,
            )
        )).scalars().first()

        if not conv:
            conv = Conversation(
                bot_id=bot.bot_id,
                visitor_session_id=session_id,
                captured_data={"name": contact_name, "phone": f"+{from_phone}", "channel": "whatsapp"},
            )
            db.add(conv)
            await db.commit()
            await db.refresh(conv)
            # A WhatsApp chat always comes with a number to reach them: that's a lead (alerts fire once).
            fire_and_forget(lead_captured(conv.conversation_id))
        else:
            data = dict(conv.captured_data or {})
            if "name" not in data or data["name"] == "Customer":
                data["name"] = contact_name
            data["phone"] = f"+{from_phone}"
            data["channel"] = "whatsapp"
            conv.captured_data = data
            await db.commit()

        # Check Human Handoff status
        if conv.handoff_status == "human":
            # Human agent is in control; save user message and notify dashboard live chat
            db.add(Message(conversation_id=conv.conversation_id, role="user", content=user_text))
            await db.commit()
            await notify_owner(bot.user_id, "new_message", {
                "conversation_id": conv.conversation_id,
                "bot_id": bot.bot_id,
                "session_id": session_id,
                "role": "user",
                "message": user_text,
                "created_at": time.time(),
            })
            return

        # A person was asked for, or the customer is clearly upset: hand over to the team.
        asked = bool(_HUMAN_RE.search(user_text))
        upset = not asked and await assist.should_escalate(bot.user_id, user_text)
        if asked or upset:
            conv.handoff_status = "pending"
            conv.handoff_requested = True
            db.add(Message(conversation_id=conv.conversation_id, role="user", content=user_text))
            handoff_reply = await assist.away_reply(bot.user_id) or (
                "I'm sorry about this. I've asked someone from our team to take over, and they'll reply here shortly."
                if upset else
                "I've let our team know. Someone will reply here shortly. Feel free to add any details in the meantime."
            )
            db.add(Message(conversation_id=conv.conversation_id, role="assistant", content=handoff_reply))
            await db.commit()

            fire_and_forget(handoff_requested(conv.conversation_id, user_text))
            await notify_owner(bot.user_id, "handoff_requested", {
                "conversation_id": conv.conversation_id,
                "bot_id": bot.bot_id,
                "bot_name": bot.bot_name,
                "session_id": session_id,
                "message": user_text,
                "phone": f"+{from_phone}",
                "name": contact_name,
            })
            try:
                await channels.send_whatsapp_text(from_phone, handoff_reply, phone_number_id=active_pid, token=token)
            except Exception as e:
                logger.error(f"[WhatsApp] Failed to send handoff message: {e}")
            return

        # Visual Flow evaluation (if bot has visual flow nodes configured)
        if bot.flow_data and bot.flow_data.get("nodes"):
            current_node = conv.current_node_id
            flow_messages, next_node, handoff = FlowEngine.process(bot.flow_data, current_node)
            if flow_messages:
                conv.current_node_id = next_node
                if handoff:
                    conv.handoff_status, conv.handoff_requested = "pending", True
                reply_text = "\n\n".join(flow_messages)
                db.add(Message(conversation_id=conv.conversation_id, role="user", content=user_text))
                db.add(Message(conversation_id=conv.conversation_id, role="assistant", content=reply_text))
                await db.commit()
                if handoff:
                    fire_and_forget(handoff_requested(conv.conversation_id, user_text))
                    await notify_owner(bot.user_id, "handoff_requested", {
                        "conversation_id": conv.conversation_id, "bot_id": bot.bot_id,
                        "session_id": session_id, "message": user_text,
                    })
                try:
                    await channels.send_whatsapp_text(from_phone, reply_text, phone_number_id=active_pid, token=token)
                except Exception as e:
                    logger.error(f"[WhatsApp] Failed to send flow reply: {e}")
                return

        # Fetch conversation history for dialogue continuity
        history_rows = (await db.execute(
            select(Message).where(Message.conversation_id == conv.conversation_id, Message.role.in_(["user", "assistant"]))
            .order_by(Message.timestamp.desc()).limit(6)
        )).scalars().all()
        history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]

        # Knowledge retrieval via Pinecone RAG or fallback knowledge base
        context = ""
        try:
            matches = await asyncio.wait_for(query_knowledge(bot.bot_id, user_text, top_k=4), timeout=6.0)
            if matches:
                context = "\n\n".join(m["text"] for m in matches)
        except Exception as e:
            logger.warning(f"[WhatsApp] Knowledge search failed for {bot.bot_id}: {e}")
        if not context:
            context = (bot.knowledge_base or "")[:6000]
        context = await assist.verified_answers(bot.bot_id) + context

        # Generate AI response
        prompt = _format_whatsapp_prompt(bot, history)
        try:
            answer = await asyncio.to_thread(
                generate_ai_response,
                prompt,
                context,
                user_text,
                provider=bot.ai_provider,
                model_name=bot.ai_model,
                api_key=bot.ai_api_key,
                is_system_use=False,
            )
        except Exception as e:
            logger.error(f"[WhatsApp] AI generation error for bot {bot.bot_id}: {e}")
            answer = "I apologize, but I am experiencing a temporary connection issue. Please try sending your message again in a moment."

        # Send answer to WhatsApp user
        try:
            await channels.send_whatsapp_text(from_phone, answer, phone_number_id=active_pid, token=token)
        except Exception as e:
            logger.error(f"[WhatsApp] Failed to send WhatsApp reply to {from_phone}: {e}")

        # Save conversation turn
        db.add(Message(conversation_id=conv.conversation_id, role="user", content=user_text))
        db.add(Message(conversation_id=conv.conversation_id, role="assistant", content=answer))
        await db.commit()
        if assist.is_unanswered(answer):
            fire_and_forget(assist.record_gap(bot.bot_id, user_text, "whatsapp", conv.conversation_id))

        # Emit realtime update for dashboard live chat observers
        await notify_owner(bot.user_id, "new_message", {
            "conversation_id": conv.conversation_id,
            "bot_id": bot.bot_id,
            "session_id": session_id,
            "role": "user",
            "message": user_text,
            "created_at": time.time(),
        })

        # Lead capture check (e.g. user shares email or phone)
        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", user_text)
        if email_match and conv.captured_data:
            current_data = dict(conv.captured_data)
            if current_data.get("email") != email_match.group(0):
                current_data["email"] = email_match.group(0)
                conv.captured_data = current_data
                await db.commit()
