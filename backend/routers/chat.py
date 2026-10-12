"""Public endpoints used by the chat widget and demo page."""
import asyncio
import logging
import os
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, get_optional_ctx
from database import async_session, get_db
from backend.models import Bot, Conversation, Message
from netsafe import UnsafeUrl, assert_public_url
import assist
import behaviour
from notify.events import handoff_requested, fire_and_forget, lead_captured
from phone import extract_contact
from realtime import notify_owner
from subscriptions import active_subscription
from utils import FlowEngine, generate_ai_response, generate_ai_response_stream
from vector_store import query_knowledge

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

HUMAN_KEYWORDS = ["talk to human", "agent", "human", "speak to someone", "representative",
                  "talk to a person", "speak to a person", "real person", "talk to someone", "customer care"]
EXPIRED_TEXT = "Subscription Expired: This bot is currently inactive. Please renew your subscription to continue chatting."


class ChatMessage(BaseModel):
    bot_id: str
    message: str
    visitor_session_id: str
    history: List[dict] = []
    is_demo: Optional[bool] = False


class VariableCapture(BaseModel):
    bot_id: str
    visitor_session_id: str
    variable_name: str
    variable_value: str


class AIPromptRequest(BaseModel):
    bot_id: str
    prompt: str
    visitor_session_id: str
    context: Optional[str] = ""


class HTTPProxyRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: Optional[dict] = {}
    body: Optional[dict] = {}


class GoogleSheetsSyncRequest(BaseModel):
    bot_id: str
    spreadsheet_id: str
    sheet_name: str = "Sheet1"
    data: dict


class ManualHandoffRequest(BaseModel):
    bot_id: str
    visitor_session_id: str


async def _load_bot(bot_id: str, db: AsyncSession) -> Bot:
    bot = (await db.execute(select(Bot).where(Bot.bot_id == (bot_id or "").strip()[:36]))).scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


def _demo_allowed(bot: Bot, ctx: Optional[AuthContext]) -> bool:
    """Demo mode skips the plan check, so only the bot's own team (or listed marketing demos) get it."""
    if ctx and ctx.owner_id == bot.user_id:
        return True
    return bot.bot_id in {b.strip() for b in os.getenv("DEMO_BOT_IDS", "").split(",") if b.strip()}


async def _plan_ok(bot: Bot, chat_is_demo: bool, ctx: Optional[AuthContext], db: AsyncSession) -> bool:
    if chat_is_demo and _demo_allowed(bot, ctx):
        return True
    return await active_subscription(bot.bot_id, db) is not None


async def _conversation(bot: Bot, session_id: str, db: AsyncSession) -> Optional[Conversation]:
    return (await db.execute(
        select(Conversation).where(Conversation.bot_id == bot.bot_id, Conversation.visitor_session_id == session_id)
    )).scalars().first()


async def _knowledge(bot: Bot, query: str, top_k: int, limit: int) -> str:
    """The business's confirmed answers first, then the closest matches from its knowledge."""
    confirmed = await assist.verified_answers(bot.bot_id)
    try:
        matches = await asyncio.wait_for(query_knowledge(bot.bot_id, query, top_k), timeout=6.0)
        if matches:
            return confirmed + "\n\n".join(m["text"] for m in matches)
    except Exception as e:
        logger.warning(f"Knowledge search failed for {bot.bot_id}: {e}")
    return confirmed + (bot.knowledge_base or "")[:limit]


def _after_answer(bot: Bot, conversation_id: Optional[str], question: str, answer: str, channel: str = "chat") -> None:
    """Questions the assistant couldn't answer go to the Questions page for the business to answer."""
    if assist.is_unanswered(answer):
        fire_and_forget(assist.record_gap(bot.bot_id, question, channel, conversation_id))


async def _save_turn(conversation_id: str, user_text: str, answer: str) -> None:
    async with async_session() as db:
        db.add(Message(conversation_id=conversation_id, role="user", content=user_text))
        if answer:
            db.add(Message(conversation_id=conversation_id, role="assistant", content=answer))
        await db.commit()


async def _request_handoff(bot: Bot, conv: Conversation, message: str) -> None:
    fire_and_forget(handoff_requested(conv.conversation_id, message))
    await notify_owner(bot.user_id, "handoff_requested", {
        "conversation_id": conv.conversation_id, "bot_id": bot.bot_id, "bot_name": bot.bot_name,
        "session_id": conv.visitor_session_id, "message": message, "created_at": datetime.utcnow().isoformat(),
    })


def _persona_prompt(bot: Bot, first_message: bool) -> str:
    name = bot.bot_name or "Assistant"
    intro = (f'Introduce yourself naturally in this first message: "Hi, I am {name}, your personal assistant from [Company/Name]".'
             if first_message else
             "Do NOT introduce yourself again. You have already introduced yourself. Get straight to the answer without repeating your name or role.")
    return f"""You are {name}. You must ALWAYS respond in first person as {name}.
Speak naturally as a human assistant.

YOUR IDENTITY:
- Name: {name}
- Role: Personal Assistant
- Organization/Company: Find the company name or the person's name in the "INTERNAL KNOWLEDGE" below.

INTRODUCTION RULE:
{intro}

STRICT RULES:
1. NEVER mention technical terms like "RAG", "AI model", "knowledge base", "context", or "database".
2. NO HALLUCINATION: Only answer using the "INTERNAL KNOWLEDGE" provided. If the information is not there, say "{behaviour.fallback(bot.behaviour)}"
3. CORRECT SPACING: Ensure you use proper spacing between words.
4. BE CONCISE: Don't repeat your name in every sentence.

{bot.system_prompt or ""}
{behaviour.rules(bot.behaviour)}

Adopt the persona fully. Be helpful, natural, and stay in character."""


async def _pre_ai(chat: ChatMessage, bot: Bot, db: AsyncSession):
    """
    Shared checks before calling the AI: human takeover, handoff keywords and
    the visual flow. Returns (conversation, replies_or_None, extra_fields).
    """
    conv = await _conversation(bot, chat.visitor_session_id, db)
    if conv and conv.handoff_status == "human":
        return conv, ["A human agent is currently handling this chat."], {"handoff_status": "human"}

    asked = any(k in chat.message.lower() for k in HUMAN_KEYWORDS)
    upset = not asked and await assist.should_escalate(bot.user_id, chat.message)
    if asked or upset:
        if not conv:
            conv = Conversation(bot_id=bot.bot_id, visitor_session_id=chat.visitor_session_id)
            db.add(conv)
        conv.handoff_requested, conv.handoff_status = True, "pending"
        await db.commit()
        await _request_handoff(bot, conv, chat.message)
        away = await assist.away_reply(bot.user_id)
        reply = away or ("I'm sorry about this. I'm bringing in someone from our team to help you." if upset
                         else "I've notified a human agent. They will join the chat shortly. Please wait.")
        return conv, [reply], {"handoff_status": "pending"}

    if bot.flow_data and bot.flow_data.get("nodes"):
        current = conv.current_node_id if conv else None
        first_user_message = not any(m.get("role") == "user" for m in chat.history)
        if current or first_user_message:
            flow_messages, next_node, handoff = FlowEngine.process(bot.flow_data, current)
            if flow_messages:
                if not conv:
                    conv = Conversation(bot_id=bot.bot_id, visitor_session_id=chat.visitor_session_id)
                    db.add(conv)
                conv.current_node_id = next_node
                if handoff:
                    conv.handoff_status, conv.handoff_requested = "pending", True
                await db.commit()
                if handoff:
                    await _request_handoff(bot, conv, chat.message)
                return conv, flow_messages, {}

    if not conv:
        conv = Conversation(bot_id=bot.bot_id, visitor_session_id=chat.visitor_session_id)
        db.add(conv)
        await db.commit()
    return conv, None, {}


class AnswerFeedback(BaseModel):
    bot_id: str
    visitor_session_id: str
    question: str
    helpful: bool


@router.post("/chat/feedback")
async def answer_feedback(data: AnswerFeedback, db: AsyncSession = Depends(get_db)):
    """A visitor rated an answer. Unhelpful ones go to Questions, so the business can answer them properly."""
    bot = await _load_bot(data.bot_id, db)
    conv = (await db.execute(select(Conversation).where(
        Conversation.bot_id == bot.bot_id, Conversation.visitor_session_id == data.visitor_session_id))).scalars().first()
    if not conv:  # only people who actually chatted can rate
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not data.helpful and data.question.strip():
        await assist.record_gap(bot.bot_id, data.question.strip()[:300], "chat", conv.conversation_id)
    return {"ok": True}


@router.post("/chat/message")
async def chat_message(chat: ChatMessage, ctx: Optional[AuthContext] = Depends(get_optional_ctx), db: AsyncSession = Depends(get_db)):
    bot = await _load_bot(chat.bot_id, db)
    if not await _plan_ok(bot, bool(chat.is_demo), ctx, db):
        return {"answer": EXPIRED_TEXT, "bot_id": chat.bot_id, "expired": True}

    conv, replies, extra = await _pre_ai(chat, bot, db)
    if replies is not None:
        reply = "\n".join(replies)
        await _save_turn(conv.conversation_id, chat.message, reply)
        return {"answer": reply, "bot_id": chat.bot_id, **extra}

    context = await _knowledge(bot, chat.message, 5, 8000)
    try:
        answer = await asyncio.to_thread(
            generate_ai_response, _persona_prompt(bot, len(chat.history) == 0), context, chat.message,
            provider=bot.ai_provider, model_name=bot.ai_model, api_key=bot.ai_api_key, is_system_use=False,
        )
    except Exception as e:
        logger.error(f"AI response error: {e}")
        answer = "Sorry, I'm having trouble thinking right now. Please try again."
    await _save_turn(conv.conversation_id, chat.message, answer)
    _after_answer(bot, conv.conversation_id, chat.message, answer)
    return {"answer": answer, "bot_id": chat.bot_id}


@router.post("/chat/message/stream")
async def chat_message_stream(chat: ChatMessage, ctx: Optional[AuthContext] = Depends(get_optional_ctx), db: AsyncSession = Depends(get_db)):
    bot = await _load_bot(chat.bot_id, db)

    def single(text: str) -> StreamingResponse:
        async def gen():
            yield f"data: {text}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    if not await _plan_ok(bot, bool(chat.is_demo), ctx, db):
        return single("Subscription Expired: This bot is currently inactive. Please renew your subscription.")

    conv, replies, _ = await _pre_ai(chat, bot, db)
    if replies is not None:
        await _save_turn(conv.conversation_id, chat.message, "\n".join(replies))

        async def flow_gen():
            for line in replies:
                yield f"data: {line}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(flow_gen(), media_type="text/event-stream")

    context = await _knowledge(bot, chat.message, 3, 5000)
    prompt = _persona_prompt(bot, len(chat.history) == 0)
    conversation_id = conv.conversation_id

    async def event_generator():
        parts: list[str] = []
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def produce():
            try:
                for chunk in generate_ai_response_stream(
                    prompt, context, chat.message, history=chat.history,
                    provider=bot.ai_provider, model_name=bot.ai_model, api_key=bot.ai_api_key,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as e:
                logger.error(f"Stream error: {e}")
                loop.call_soon_threadsafe(queue.put_nowait, "Sorry, I'm having trouble responding. Please try again.")
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(None, produce)
        while (chunk := await queue.get()) is not None:
            parts.append(chunk)
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"
        try:
            await _save_turn(conversation_id, chat.message, "".join(parts))
        except Exception as e:
            logger.warning(f"Could not save chat turn: {e}")
        _after_answer(bot, conversation_id, chat.message, "".join(parts))

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


@router.post("/chat/variables")
async def capture_variables(data: VariableCapture, db: AsyncSession = Depends(get_db)):
    bot = await _load_bot(data.bot_id, db)
    conv = await _conversation(bot, data.visitor_session_id, db)
    if not conv:
        conv = Conversation(bot_id=bot.bot_id, visitor_session_id=data.visitor_session_id, captured_data={})
        db.add(conv)
    captured = dict(conv.captured_data or {})
    captured[data.variable_name[:80]] = str(data.variable_value)[:2000]
    conv.captured_data = captured
    await db.commit()

    contact = extract_contact(captured)
    if contact.get("phone") or contact.get("email"):
        fire_and_forget(lead_captured(conv.conversation_id))
    return {"status": "success", "captured": captured}


@router.post("/chat/ai-prompt")
async def ai_custom_prompt(data: AIPromptRequest, ctx: Optional[AuthContext] = Depends(get_optional_ctx), db: AsyncSession = Depends(get_db)):
    bot = await _load_bot(data.bot_id, db)
    if not await _plan_ok(bot, True, ctx, db):
        return {"answer": EXPIRED_TEXT}
    try:
        answer = await asyncio.to_thread(
            generate_ai_response, "Execute the following specific prompt based on the context.",
            (data.context or bot.knowledge_base or "")[:20000], data.prompt,
            provider=bot.ai_provider, model_name=bot.ai_model, api_key=bot.ai_api_key, is_system_use=False,
        )
        return {"answer": answer}
    except Exception as e:
        logger.error(f"AI prompt error: {e}")
        return {"answer": "Error generating AI response."}


@router.post("/chat/proxy-http")
async def proxy_http_request(data: HTTPProxyRequest):
    """Runs the flow's HTTP Request node. Only public internet addresses are reachable."""
    method = data.method.upper()
    if method not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
        return {"error": "Method not supported"}
    try:
        url = await assert_public_url(data.url)
    except UnsafeUrl as e:
        return {"error": str(e)}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            resp = await client.request(method, url, headers=data.headers or {},
                                        json=data.body if method in ("POST", "PATCH", "PUT") else None)
        body = resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text[:20000]
        return {"status": resp.status_code, "data": body}
    except Exception as e:
        return {"error": str(e)}


def _sheet_configured(bot: Bot, spreadsheet_id: str) -> bool:
    for node in (bot.flow_data or {}).get("nodes", []):
        data = node.get("data") or {}
        if spreadsheet_id and spreadsheet_id in (str(data.get("spreadsheetId", "")), str(data.get("spreadsheet_id", "")), str(data.get("sheetUrl", ""))):
            return True
    return False


@router.post("/integrations/google-sheets")
async def sync_to_google_sheets(data: GoogleSheetsSyncRequest, db: AsyncSession = Depends(get_db)):
    bot = await _load_bot(data.bot_id, db)
    if not _sheet_configured(bot, data.spreadsheet_id):
        raise HTTPException(status_code=403, detail="This spreadsheet isn't connected to the assistant's flow")
    key_path = os.getenv("GOOGLE_SHEETS_KEY_PATH", "google_sheets_key.json")
    if not os.path.exists(key_path):
        return {"error": "Google Sheets isn't set up on the server (service account key missing)."}
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        def append():
            creds = service_account.Credentials.from_service_account_file(key_path, scopes=["https://www.googleapis.com/auth/spreadsheets"])
            service = build("sheets", "v4", credentials=creds, cache_discovery=False)
            return service.spreadsheets().values().append(
                spreadsheetId=data.spreadsheet_id, range=f"{data.sheet_name}!A1", valueInputOption="RAW",
                insertDataOption="INSERT_ROWS", body={"values": [[str(v) for v in data.data.values()]]},
            ).execute()

        result = await asyncio.to_thread(append)
        return {"status": "success", "updatedRange": result.get("updates", {}).get("updatedRange")}
    except Exception as e:
        logger.error(f"Google Sheets sync error: {e}")
        return {"error": str(e)}


@router.post("/chat/handoff")
async def manual_handoff(request: ManualHandoffRequest, db: AsyncSession = Depends(get_db)):
    """The widget's 'talk to a person' button."""
    bot = await _load_bot(request.bot_id, db)
    conv = await _conversation(bot, request.visitor_session_id, db)
    if not conv:
        conv = Conversation(bot_id=bot.bot_id, visitor_session_id=request.visitor_session_id)
        db.add(conv)
    conv.handoff_status, conv.handoff_requested = "pending", True
    await db.commit()
    await _request_handoff(bot, conv, "")
    away = await assist.away_reply(bot.user_id)
    return {"status": "success", "message": away or "Handoff requested", "away": bool(away)}
