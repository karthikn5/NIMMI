"""Public endpoints used by the chat widget and demo page."""
import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, client_ip, get_optional_ctx, rate_limit
from database import async_session, get_db
from backend.models import Bot, Conversation, Message
from netsafe import UnsafeUrl, assert_public_url, safe_client
import assist
import behaviour
import plans
from notify.events import handoff_requested, fire_and_forget, lead_captured
from phone import extract_contact
from realtime import notify_owner
from subscriptions import active_subscription
from utils import generate_ai_response, generate_ai_response_stream
import brain

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

# Asking for a person, as on WhatsApp (whatsapp/replies.py): whole phrases. Inside a sentence one word isn't enough:
# "your voice agent", "I'm a travel agent", "does it sound human?" and "can it replace our customer care?" are
# questions. Sent on its own ("human", "agent please", "customer care"), it is a request.
_WHO = (r"(?:a |an |the |your |some |a real |a live )?"
        r"(?:human(?: being)?|person|people|someone|somebody|agent|human agent|representative|executive|team|staff)")
_ASKS_FOR_PERSON = re.compile(
    rf"(?<!\w)(?:(?:talk|speak|chat)(?: to| with)|connect me(?: to| with)|transfer me to|put me through to) {_WHO}(?!\w)"
    r"|(?<!\w)(?:human agent|live agent|real person|real human)(?!\w)|ஆள் வேண்டும்|பேச வேண்டும்|बात करनी है", re.IGNORECASE)
_PERSON_ALONE = re.compile(
    rf"^\W*(?:(?:i )?(?:want|need) )?{_WHO}(?: please| pls| plz| now)?\W*$"
    r"|^\W*(?:customer care|customer service|support(?: team)?|மனிதன்|इंसान)\W*$", re.IGNORECASE)


def asks_for_person(message: str) -> bool:
    text = " ".join(str(message or "").split())
    return bool(_ASKS_FOR_PERSON.search(text) or _PERSON_ALONE.match(text))


EXPIRED_TEXT = "Subscription Expired: This bot is currently inactive. Please renew your subscription to continue chatting."


# Sizes are capped so one request can't run up AI costs or fill the database.
BotId = Field(..., max_length=40)
SessionId = Field(..., min_length=1, max_length=120)
MAX_FIELDS = 60  # details one conversation can collect


class ChatMessage(BaseModel):
    bot_id: str = BotId
    message: str = Field(..., min_length=1, max_length=4000)
    visitor_session_id: str = SessionId
    history: List[dict] = Field(default_factory=list)  # only the last 20 turns are kept
    is_demo: Optional[bool] = False

    @field_validator("history")
    @classmethod
    def _clean_history(cls, turns: List[dict]) -> List[dict]:
        # Only user/assistant turns, text only, and not too long (they're sent to the AI).
        return [{"role": "user" if t.get("role") == "user" else "assistant", "content": str(t.get("content") or t.get("text") or "")[:4000]}
                for t in turns[-20:] if isinstance(t, dict)]


class VariableCapture(BaseModel):
    bot_id: str = BotId
    visitor_session_id: str = SessionId
    variable_name: str = Field(..., min_length=1, max_length=80)
    variable_value: str = Field("", max_length=50_000)  # stored up to 2000 characters


class AIPromptRequest(BaseModel):
    bot_id: str = BotId
    prompt: str = Field(..., max_length=4000)
    visitor_session_id: str = SessionId
    context: Optional[str] = Field("", max_length=200_000)  # the flow's collected details; the first 8000 characters are used


class HTTPProxyRequest(BaseModel):
    bot_id: str = BotId
    url: str = Field(..., max_length=2000)
    method: str = Field("GET", max_length=10)
    body: Optional[dict] = Field(default_factory=dict)


class GoogleSheetsSyncRequest(BaseModel):
    bot_id: str = BotId
    spreadsheet_id: str = Field(..., max_length=200)
    sheet_name: str = Field("Sheet1", max_length=100)
    data: dict


class ManualHandoffRequest(BaseModel):
    bot_id: str = BotId
    visitor_session_id: str = SessionId


def _limit(request: Request, name: str, bot_id: str, per_minute: int) -> None:
    """Public endpoints: per visitor address, per assistant and overall, so scripts can't flood them."""
    ip = client_ip(request)
    rate_limit(f"{name}:{ip}:{bot_id}", per_minute, 60)
    rate_limit(f"{name}:{ip}", per_minute * 3, 60)
    rate_limit(f"{name}-hour:{ip}", per_minute * 30, 3600)


def _flow_nodes(bot: Bot, *types: str) -> list[dict]:
    return [n.get("data") or {} for n in (bot.flow_data or {}).get("nodes", []) if n.get("type") in types]


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


async def _pre_ai(chat: ChatMessage, bot: Bot, db: AsyncSession, live_chat: bool = True):
    """
    Shared checks before calling the AI: human takeover and handoff keywords (on a plan with live chat; otherwise the
    assistant answers, and can take their details for the team). Returns (conversation, replies_or_None, extra_fields).
    The visual flow runs in the widget itself (it asks the questions and saves the answers), so it isn't run again here.
    """
    conv = await _conversation(bot, chat.visitor_session_id, db)
    if conv and conv.handoff_status == "human":
        return conv, ["A human agent is currently handling this chat."], {"handoff_status": "human"}

    asked = live_chat and asks_for_person(chat.message)
    upset = live_chat and not asked and await assist.should_escalate(bot.user_id, chat.message)
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

    if not conv:
        conv = Conversation(bot_id=bot.bot_id, visitor_session_id=chat.visitor_session_id)
        db.add(conv)
        await db.commit()
    return conv, None, {}


class AnswerFeedback(BaseModel):
    bot_id: str = BotId
    visitor_session_id: str = SessionId
    question: str = Field(..., max_length=10_000)
    helpful: bool


@router.post("/chat/feedback")
async def answer_feedback(data: AnswerFeedback, request: Request, db: AsyncSession = Depends(get_db)):
    """A visitor rated an answer. Unhelpful ones go to Questions, so the business can answer them properly."""
    _limit(request, "feedback", data.bot_id, 20)
    bot = await _load_bot(data.bot_id, db)
    conv = (await db.execute(select(Conversation).where(
        Conversation.bot_id == bot.bot_id, Conversation.visitor_session_id == data.visitor_session_id))).scalars().first()
    if not conv:  # only people who actually chatted can rate
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not data.helpful and data.question.strip():
        await assist.record_gap(bot.bot_id, data.question.strip()[:300], "chat", conv.conversation_id)
    return {"ok": True}


@router.post("/chat/message")
async def chat_message(chat: ChatMessage, request: Request, ctx: Optional[AuthContext] = Depends(get_optional_ctx), db: AsyncSession = Depends(get_db)):
    _limit(request, "chat", chat.bot_id, 30)
    bot = await _load_bot(chat.bot_id, db)
    if not await _plan_ok(bot, bool(chat.is_demo), ctx, db):
        return {"answer": EXPIRED_TEXT, "bot_id": chat.bot_id, "expired": True}

    testing = bool(chat.is_demo) and _demo_allowed(bot, ctx)  # the business trying it: no reply counted
    conv, replies, extra = await _pre_ai(chat, bot, db, (await plans.includes(db, bot.bot_id)).live_chat)
    if replies is not None:
        reply = "\n".join(replies)
        await _save_turn(conv.conversation_id, chat.message, reply)
        return {"answer": reply, "bot_id": chat.bot_id, **extra}
    if not testing and not await plans.can_reply(db, bot.bot_id):
        await _save_turn(conv.conversation_id, chat.message, plans.REPLIES_USED_UP)
        return {"answer": plans.REPLIES_USED_UP, "bot_id": chat.bot_id}

    system, messages = await _brief(bot, conv, chat)
    answer = await asyncio.to_thread(generate_ai_response, system, "", messages[-1]["content"], history=messages[:-1],
                                     provider=bot.ai_provider, model_name=bot.ai_model, api_key=bot.ai_api_key)
    if not testing:
        fire_and_forget(plans.count_reply(bot.bot_id))
    await _save_turn(conv.conversation_id, chat.message, answer)
    _after_answer(bot, conv.conversation_id, chat.message, answer)
    fire_and_forget(brain.learn_details(conv.conversation_id, bot, chat.message, _last_assistant(chat.history)))
    return {"answer": answer, "bot_id": chat.bot_id}


def _last_assistant(history: List[dict]) -> str:
    return next((h.get("content", "") for h in reversed(history or []) if h.get("role") == "assistant"), "")


async def _brief(bot: Bot, conv: Conversation, chat: ChatMessage) -> tuple[str, list[dict]]:
    """The assistant's instructions (with knowledge and what it still needs to learn) and the conversation."""
    knowledge = await brain.knowledge(bot, chat.message)
    first = not any(h.get("role") == "assistant" for h in chat.history)
    system = brain.system_prompt(bot, captured=conv.captured_data or {}, first_message=first, channel="chat", knowledge_text=knowledge)
    return system, brain.turns(chat.history, chat.message)


def _sse(text: str) -> str:
    """One streamed piece. JSON-encoded so line breaks inside an answer survive the event stream."""
    return f"data: {json.dumps(text)}\n\n"


@router.post("/chat/message/stream")
async def chat_message_stream(chat: ChatMessage, request: Request, ctx: Optional[AuthContext] = Depends(get_optional_ctx), db: AsyncSession = Depends(get_db)):
    _limit(request, "chat", chat.bot_id, 30)
    bot = await _load_bot(chat.bot_id, db)

    def single(text: str) -> StreamingResponse:
        async def gen():
            yield _sse(text)
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    if not await _plan_ok(bot, bool(chat.is_demo), ctx, db):
        return single("Subscription Expired: This bot is currently inactive. Please renew your subscription.")

    testing = bool(chat.is_demo) and _demo_allowed(bot, ctx)  # the business trying it: no reply counted
    conv, replies, _ = await _pre_ai(chat, bot, db, (await plans.includes(db, bot.bot_id)).live_chat)
    if replies is not None:
        await _save_turn(conv.conversation_id, chat.message, "\n".join(replies))

        async def flow_gen():
            for line in replies:
                yield _sse(line)
            yield "data: [DONE]\n\n"
        return StreamingResponse(flow_gen(), media_type="text/event-stream")
    if not testing and not await plans.can_reply(db, bot.bot_id):
        await _save_turn(conv.conversation_id, chat.message, plans.REPLIES_USED_UP)
        return single(plans.REPLIES_USED_UP)

    system, messages = await _brief(bot, conv, chat)
    conversation_id = conv.conversation_id

    async def event_generator():
        parts: list[str] = []
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def produce():
            try:
                for chunk in generate_ai_response_stream(
                    system, "", messages[-1]["content"], history=messages[:-1],
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
            yield _sse(chunk)
        yield "data: [DONE]\n\n"
        if not testing:
            fire_and_forget(plans.count_reply(bot.bot_id))
        try:
            await _save_turn(conversation_id, chat.message, "".join(parts))
        except Exception as e:
            logger.warning(f"Could not save chat turn: {e}")
        _after_answer(bot, conversation_id, chat.message, "".join(parts))
        fire_and_forget(brain.learn_details(conversation_id, bot, chat.message, _last_assistant(chat.history)))

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


MAX_VOICE_BYTES = 1_000_000  # about a minute of compressed speech
SPEECH_LANGUAGES = {"en": "en-IN", "hi": "hi-IN", "ta": "ta-IN", "te": "te-IN", "kn": "kn-IN", "ml": "ml-IN",
                    "mr": "mr-IN", "bn": "bn-IN", "gu": "gu-IN"}


@router.post("/chat/transcribe")
async def transcribe_speech(request: Request, bot_id: str = Form(..., max_length=40), file: UploadFile = File(...),
                            ctx: Optional[AuthContext] = Depends(get_optional_ctx), db: AsyncSession = Depends(get_db)):
    """The widget's mic, for browsers without built-in speech recognition: a short recording to text."""
    _limit(request, "transcribe", bot_id, 8)
    bot = await _load_bot(bot_id, db)
    if not await _plan_ok(bot, True, ctx, db):
        raise HTTPException(status_code=402, detail="This assistant isn't active")
    if not (file.content_type or "").startswith("audio/"):
        raise HTTPException(status_code=400, detail="Send an audio recording")
    audio = await file.read(MAX_VOICE_BYTES + 1)
    if not audio or len(audio) > MAX_VOICE_BYTES:
        raise HTTPException(status_code=400, detail="Keep voice messages under a minute")
    from voice import sarvam
    if not sarvam.configured():
        raise HTTPException(status_code=503, detail="Voice input isn't available right now")
    language = SPEECH_LANGUAGES.get(behaviour.clean(bot.behaviour)["language"], "unknown") if bot.behaviour else "unknown"
    try:
        text = await sarvam.transcribe(audio, file.filename or "speech.webm", file.content_type, language)
    except sarvam.SarvamError as e:
        logger.warning(f"Voice input failed: {e}")
        raise HTTPException(status_code=502, detail="Couldn't understand that. Please try again or type your message.")
    return {"text": text}


@router.post("/chat/variables")
async def capture_variables(data: VariableCapture, request: Request, db: AsyncSession = Depends(get_db)):
    _limit(request, "variables", data.bot_id, 40)
    bot = await _load_bot(data.bot_id, db)
    conv = await _conversation(bot, data.visitor_session_id, db)
    if not conv:
        rate_limit(f"new-conv:{client_ip(request)}", 30, 3600)  # many fresh "visitors" from one address is a script
        conv = Conversation(bot_id=bot.bot_id, visitor_session_id=data.visitor_session_id, captured_data={})
        db.add(conv)
    captured = dict(conv.captured_data or {})
    if data.variable_name not in captured and len(captured) >= MAX_FIELDS:
        raise HTTPException(status_code=400, detail="Too many details for one conversation")
    captured[data.variable_name] = data.variable_value[:2000]
    conv.captured_data = captured
    await db.commit()

    contact = extract_contact(captured)
    if contact.get("phone") or contact.get("email"):
        fire_and_forget(lead_captured(conv.conversation_id))
    return {"status": "success", "captured": captured}


@router.post("/chat/ai-prompt")
async def ai_custom_prompt(data: AIPromptRequest, request: Request, ctx: Optional[AuthContext] = Depends(get_optional_ctx), db: AsyncSession = Depends(get_db)):
    """The flow's "AI prompt" step. Only prompts the business wrote into its flow run, so this can't be used as a free AI."""
    _limit(request, "ai-prompt", data.bot_id, 10)
    bot = await _load_bot(data.bot_id, db)
    if not await _plan_ok(bot, True, ctx, db):
        return {"answer": EXPIRED_TEXT}
    allowed = {str(d.get(k) or "").strip() for d in _flow_nodes(bot, "aiPrompt") for k in ("prompt", "systemPrompt")} - {""}
    if data.prompt.strip() not in allowed:
        raise HTTPException(status_code=403, detail="This prompt isn't part of the assistant's flow")
    testing = _demo_allowed(bot, ctx)
    if not testing and not await plans.can_reply(db, bot.bot_id):
        return {"answer": plans.REPLIES_USED_UP}
    if not testing:
        fire_and_forget(plans.count_reply(bot.bot_id))
    try:
        answer = await asyncio.to_thread(
            generate_ai_response, "Execute the following specific prompt based on the context.",
            (data.context[:8000] if data.context else (bot.knowledge_base or "")[:20000]), data.prompt,
            provider=bot.ai_provider, model_name=bot.ai_model, api_key=bot.ai_api_key, is_system_use=False,
        )
        return {"answer": answer}
    except Exception as e:
        logger.error(f"AI prompt error: {e}")
        return {"answer": "Error generating AI response."}


MAX_PROXY_BYTES = 256 * 1024


def _flow_request_allowed(bot: Bot, url: str, method: str) -> bool:
    """Only URLs the business put in its flow (HTTP request, webhook and Slack steps), with their method."""
    for d in _flow_nodes(bot, "httpRequest", "webhook", "slack"):
        if str(d.get("url") or "").strip() == url.strip():
            if str(d.get("method") or "POST").upper() == method:
                return True
    return False


@router.post("/chat/proxy-http")
async def proxy_http_request(data: HTTPProxyRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Runs the flow's HTTP request, webhook and Slack steps: only to URLs in that assistant's flow, only on the public internet."""
    _limit(request, "proxy", data.bot_id, 20)
    method = data.method.upper()
    if method not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
        return {"error": "Method not supported"}
    bot = await _load_bot(data.bot_id, db)
    if not _flow_request_allowed(bot, data.url, method):
        raise HTTPException(status_code=403, detail="This address isn't part of the assistant's flow")
    try:
        url = await assert_public_url(data.url)
    except UnsafeUrl as e:
        return {"error": str(e)}
    try:
        async with safe_client(timeout=10) as client:
            async with client.stream(method, url, json=data.body if method in ("POST", "PATCH", "PUT") else None) as resp:
                raw = bytearray()
                async for chunk in resp.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_PROXY_BYTES:
                        break
                status, ctype = resp.status_code, resp.headers.get("content-type", "")
        text = bytes(raw[:MAX_PROXY_BYTES]).decode("utf-8", errors="replace")
        if "application/json" in ctype:
            try:
                return {"status": status, "data": json.loads(text)}
            except ValueError:
                pass
        return {"status": status, "data": text[:20000]}
    except Exception as e:
        logger.info(f"Flow HTTP step failed: {e}")
        return {"error": "The request didn't go through"}


def _sheet_configured(bot: Bot, spreadsheet_id: str) -> bool:
    for node in (bot.flow_data or {}).get("nodes", []):
        data = node.get("data") or {}
        if spreadsheet_id and spreadsheet_id in (str(data.get("spreadsheetId", "")), str(data.get("spreadsheet_id", "")), str(data.get("sheetUrl", ""))):
            return True
    return False


@router.post("/integrations/google-sheets")
async def sync_to_google_sheets(data: GoogleSheetsSyncRequest, request: Request, db: AsyncSession = Depends(get_db)):
    _limit(request, "sheets", data.bot_id, 10)
    if len(data.data) > MAX_FIELDS:
        raise HTTPException(status_code=400, detail="Too many fields")
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
                insertDataOption="INSERT_ROWS", body={"values": [[str(v)[:2000] for v in data.data.values()]]},
            ).execute()

        result = await asyncio.to_thread(append)
        return {"status": "success", "updatedRange": result.get("updates", {}).get("updatedRange")}
    except Exception as e:
        logger.error(f"Google Sheets sync error: {e}")
        return {"error": "Couldn't add the row to Google Sheets"}


@router.post("/chat/handoff")
async def manual_handoff(request: ManualHandoffRequest, http: Request, db: AsyncSession = Depends(get_db)):
    """The widget's 'talk to a person' button."""
    _limit(http, "handoff", request.bot_id, 6)
    bot = await _load_bot(request.bot_id, db)
    if not (await plans.includes(db, bot.bot_id)).live_chat:
        raise HTTPException(status_code=403, detail="Live chat isn't on for this assistant")
    conv = await _conversation(bot, request.visitor_session_id, db)
    if not conv:
        conv = Conversation(bot_id=bot.bot_id, visitor_session_id=request.visitor_session_id)
        db.add(conv)
    conv.handoff_status, conv.handoff_requested = "pending", True
    await db.commit()
    await _request_handoff(bot, conv, "")
    away = await assist.away_reply(bot.user_id)
    # Replies from an earlier chat in this session: the widget mustn't show them as new ones.
    earlier = (await db.execute(select(Message.id).where(
        Message.conversation_id == conv.conversation_id, Message.role == "assistant"))).scalars().all()
    return {"status": "success", "message": away or "Handoff requested", "away": bool(away), "earlier": list(earlier)}


@router.get("/chat/live/{bot_id}/{session_id}")
async def live_replies(bot_id: str, session_id: str, http: Request, db: AsyncSession = Depends(get_db)):
    """The team's latest replies in a 'talk to a person' chat. The widget checks this every few seconds as well as
    listening on its socket, so a reply still arrives if the socket dropped or sits on another server process.
    The session id is a random id kept in the visitor's browser: knowing it is their proof, as for the socket."""
    _limit(http, "live", bot_id, 40)
    if not session_id.startswith("widget-session-human-") or len(session_id) > 120:
        raise HTTPException(status_code=404, detail="Chat not found")
    conv = await _conversation(await _load_bot(bot_id, db), session_id, db)
    if not conv:
        return {"status": "ai", "messages": []}
    latest = (await db.execute(select(Message).where(
        Message.conversation_id == conv.conversation_id, Message.role == "assistant"
    ).order_by(Message.timestamp.desc()).limit(20))).scalars().all()
    return {"status": conv.handoff_status, "messages": [{"id": m.id, "text": m.content} for m in reversed(latest)]}
