import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import behaviour
import knowledge_sources
import supa
from auth import AuthContext, get_ctx, get_optional_ctx, get_owned_bot, require_manager
from crawler import crawl_site, extract_text_from_url, extract_youtube_transcript
from database import get_db
import templates
from backend.models import Bot, CallbackSettings, Conversation, Subscription, UserUsage, VoiceAgent
from netsafe import UnsafeUrl, assert_public_url
from subscriptions import active_subscription
from utils import extract_text_from_pdf, extract_text_from_txt
from vector_store import delete_bot_knowledge, get_bot_vector_count, upsert_knowledge

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["bots"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DOC_BYTES = 20 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"}


class BotCreate(BaseModel):
    name: str
    template: Optional[str] = None  # an industry template id (see templates.py)
    system_prompt: Optional[str] = "You are a helpful assistant."
    visual_config: Optional[dict] = None
    user_id: Optional[str] = None  # ignored; the token decides the owner


class KnowledgeCrawlRequest(BaseModel):
    bot_id: str
    url: str
    pages: int = 1  # websites: also read up to this many linked pages on the same site


@router.get("/usage")
async def get_usage(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    usage = (await db.execute(select(UserUsage).where(UserUsage.user_id == ctx.owner_id))).scalars().first()
    if not usage:
        usage = UserUsage(user_id=ctx.owner_id, total_credits=0, used_credits=0)
        db.add(usage)
        await db.commit()
    return {"total_credits": usage.total_credits, "used_credits": usage.used_credits, "remaining_credits": 0}


@router.get("/bots/templates")
async def bot_templates():
    return templates.catalog()


@router.post("/bots/create")
async def create_bot(data: BotCreate, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    name = (data.name or "").strip()[:60] or "New assistant"
    tpl = templates.BY_ID.get(data.template or "")
    if data.template and not tpl:
        raise HTTPException(status_code=400, detail="Unknown template")
    bot = Bot(
        user_id=ctx.owner_id,
        bot_name=name,
        system_prompt=tpl["prompt"] if tpl else data.system_prompt,
        knowledge_base=tpl["knowledge"] if tpl else None,
        visual_config=data.visual_config or {"color": "#550a64", "logo_url": "", "position": "right"},
    )
    db.add(bot)
    await db.flush()
    if tpl:
        # Voice starts ready to configure: goal, fields to collect and greeting from the template.
        db.add(VoiceAgent(bot_id=bot.bot_id, user_id=ctx.owner_id, enabled=False, language="en-IN", understand_code_mixed=True,
                          speaking_rate=1.0, assistant_name="Nimmi", company_name=name, greeting=tpl["greeting"],
                          allow_interruptions=True, silence_timeout_sec=8, max_call_minutes=10, transfer_enabled=False,
                          transfer_number="", transfer_when="The caller asks to speak to a person.",
                          end_call_phrases=["that's all", "bye"], call_goal=tpl["goal"], collect_fields=tpl["fields"]))
    await db.commit()
    return {"message": "Bot created", "id": str(bot.bot_id), "template": tpl["id"] if tpl else None}


@router.post("/bots/export")
async def export_bot(bot_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    if not await active_subscription(bot.bot_id, db):
        raise HTTPException(status_code=402, detail="This bot does not have an active plan. Please subscribe to export.")
    bot.is_exported = True
    bot.exported_at = datetime.utcnow()
    await db.commit()
    return {"message": "Bot exported successfully", "bot_id": bot.bot_id, "export_unlocked": True}


@router.get("/bots")
async def list_bots(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    if os.getenv("LOCAL_DEV", "false").lower() == "true":
        bots = (await db.execute(select(Bot).order_by(Bot.created_at.desc()))).scalars().all()
    else:
        bots = (await db.execute(select(Bot).where(Bot.user_id == ctx.owner_id).order_by(Bot.created_at.desc()))).scalars().all()
    bot_ids = [b.bot_id for b in bots]
    subs = (await db.execute(
        select(Subscription).where(Subscription.bot_id.in_(bot_ids), Subscription.status == "active")
        .order_by(Subscription.end_date.desc())
    )).scalars().all() if bot_ids else []

    now = datetime.utcnow()
    active: dict = {}
    for s in subs:
        if s.end_date.replace(tzinfo=None) > now and s.bot_id not in active:
            active[s.bot_id] = s

    out = []
    for bot in bots:
        sub = active.get(bot.bot_id)
        out.append({
            "id": bot.bot_id,
            "name": bot.bot_name,
            "status": "Active" if sub else "Expired",
            "plan": sub.plan_name if sub else "None",
            "expiry": sub.end_date.strftime("%b %d, %Y") if sub else "-",
            "days_remaining": (sub.end_date.replace(tzinfo=None) - now).days if sub else 0,
        })
    return out


@router.get("/bots/{bot_id}/config")
async def get_bot_config(bot_id: str, ctx: Optional[AuthContext] = Depends(get_optional_ctx), db: AsyncSession = Depends(get_db)):
    """Public: the widget reads this. Private fields are included only for the bot's own workspace."""
    try:
        clean = str(uuid.UUID(bot_id.strip()[:36]))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Bot ID format")
    bot = (await db.execute(select(Bot).where(Bot.bot_id == clean))).scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    sub = await active_subscription(clean, db)
    is_member = ctx is not None and ctx.owner_id == bot.user_id
    callbacks = (await db.execute(select(CallbackSettings.enabled).where(CallbackSettings.user_id == bot.user_id))).scalar_one_or_none()
    voice_on = (await db.execute(select(VoiceAgent.enabled).where(VoiceAgent.bot_id == bot.bot_id))).scalar_one_or_none()

    config = {
        "bot_id": bot.bot_id,
        "bot_name": bot.bot_name,
        "visual_config": bot.visual_config,
        "flow_data": bot.flow_data,
        "is_active": bot.is_active,
        # The widget offers "call me back" only when the business has callbacks and voice turned on.
        "callbacks_enabled": bool(callbacks and voice_on and sub is not None),
        "is_exported": (sub is not None) or bot.export_unlocked,
        "subscription": {
            "active": sub is not None,
            "plan": sub.plan_name if sub else "None",
            "expiry": sub.end_date.strftime("%b %d, %Y") if sub else "-",
        },
        "created_at": bot.created_at,
    }
    if is_member:
        config.update({
            "system_prompt": bot.system_prompt,
            "knowledge_base": bot.knowledge_base,
            "ai_provider": bot.ai_provider,
            "ai_model": bot.ai_model,
            # Show only that a key exists; never send it back to the browser.
            "ai_api_key": "",
            "has_ai_api_key": bool(bot.ai_api_key),
            "behaviour": behaviour.clean(bot.behaviour),
        })
    return config


VISUAL_FIELDS = [
    "color", "botLogo", "position", "fontFamily", "textColor", "inputBgColor", "inputTextColor",
    "userBubbleBg", "userBubbleText", "assistantBubbleBg", "assistantBubbleText", "chatBgColor",
    "headerHeight", "borderRadius", "launcherShape", "showTail", "showLauncherBg", "logoSize",
    "rightPadding", "bottomPadding", "backgroundImage", "backgroundOpacity", "hideBranding",
]


@router.post("/bots/{bot_id}/config")
async def update_bot_config(bot_id: str, config_data: dict, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    if "botName" in config_data:
        bot.bot_name = str(config_data["botName"])[:60]
    if "systemPrompt" in config_data:
        bot.system_prompt = config_data["systemPrompt"]
    if "knowledgeBase" in config_data:
        bot.knowledge_base = config_data["knowledgeBase"]
    if "aiProvider" in config_data:
        bot.ai_provider = config_data["aiProvider"]
    if "aiModel" in config_data:
        bot.ai_model = config_data["aiModel"]
    if config_data.get("aiApiKey"):  # empty means "keep the saved key"
        bot.ai_api_key = config_data["aiApiKey"]
    if config_data.get("clearAiApiKey"):
        bot.ai_api_key = None

    visual = dict(bot.visual_config or {})
    for field in VISUAL_FIELDS:
        if field in config_data:
            visual[field] = config_data[field]
    bot.visual_config = visual
    if "nodes" in config_data or "edges" in config_data:
        bot.flow_data = {"nodes": config_data.get("nodes", []), "edges": config_data.get("edges", [])}
    await db.commit()
    return {"message": "Bot configuration updated"}


@router.patch("/bots/{bot_id}")
async def update_bot(bot_id: str, bot_data: dict, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    for field in ("bot_name", "system_prompt", "visual_config", "flow_data", "knowledge_base", "ai_provider", "ai_model"):
        if field in bot_data:
            setattr(bot, field, bot_data[field])
    if bot_data.get("ai_api_key"):
        bot.ai_api_key = bot_data["ai_api_key"]
    if "behaviour" in bot_data:
        bot.behaviour = behaviour.clean(bot_data["behaviour"])
    await db.commit()
    return {"message": "Bot updated"}


@router.delete("/bots/{bot_id}")
async def delete_bot(bot_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    try:
        await asyncio.to_thread(delete_bot_knowledge, bot.bot_id)
    except Exception as e:
        logger.warning(f"Failed to delete vectors for bot {bot.bot_id}: {e}")
    await db.delete(bot)
    await db.commit()
    return {"message": "Bot deleted successfully"}


async def _store_image(file: UploadFile, prefix: str) -> str:
    if file.content_type not in IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Upload a PNG, JPG, WebP, GIF or SVG image")
    content = await file.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Images must be 5 MB or smaller")
    ext = os.path.splitext(file.filename or "")[1].lower()[:6] or ".png"
    name = f"{prefix}{uuid.uuid4()}{ext}"

    url, key = os.getenv("SUPABASE_URL"), supa.service_key() or os.getenv("SUPABASE_KEY")
    if url and key:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    f"{url}/storage/v1/object/logos/{name}",
                    headers=supa.headers(key, file.content_type),
                    content=content,
                )
            if resp.status_code in (200, 201):
                return f"{url}/storage/v1/object/public/logos/{name}"
            logger.warning(f"Supabase upload failed ({resp.status_code}); using local storage")
        except Exception as e:
            logger.warning(f"Supabase upload error: {e}; using local storage")

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "uploads", name)
    await asyncio.to_thread(lambda: open(path, "wb").write(content))
    return f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/static/uploads/{name}"


@router.post("/bots/{bot_id}/logo")
async def upload_logo(bot_id: str, file: UploadFile = File(...), ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await get_owned_bot(bot_id, ctx, db)
    return {"logo_url": await _store_image(file, "")}


@router.post("/bots/{bot_id}/background")
async def upload_background(bot_id: str, file: UploadFile = File(...), ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    await get_owned_bot(bot_id, ctx, db)
    return {"bg_url": await _store_image(file, "bg_")}


async def _index(bot: Bot, text: str, source: str) -> int:
    try:
        return await asyncio.to_thread(upsert_knowledge, bot.bot_id, text, source)
    except Exception as e:
        logger.error(f"Vector indexing failed for {source}: {e}")
        return 0


@router.post("/bots/{bot_id}/knowledge/upload")
async def upload_knowledge(bot_id: str, file: UploadFile = File(...), ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    name = (file.filename or "").lower()
    if not (name.endswith(".pdf") or name.endswith(".txt")):
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported")
    if file.size and file.size > MAX_DOC_BYTES:
        raise HTTPException(status_code=400, detail="Files must be 20 MB or smaller")
    extractor = extract_text_from_pdf if name.endswith(".pdf") else extract_text_from_txt
    text = await asyncio.to_thread(extractor, file.file)
    if not text or text == "Error":
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    bot.knowledge_base = knowledge_sources.put(bot.knowledge_base, f"file: {file.filename or 'document'}", text)
    await db.commit()
    chunks = await _index(bot, text, file.filename or "upload")
    return {"message": "Knowledge updated", "bot_id": bot.bot_id, "filename": file.filename,
            "chunks_indexed": chunks, "knowledge_base": bot.knowledge_base}


@router.post("/knowledge/crawl")
async def crawl_website(data: KnowledgeCrawlRequest, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(data.bot_id, ctx, db)
    try:
        url = await assert_public_url(data.url)
    except UnsafeUrl as e:
        return {"error": str(e)}
    if data.pages > 1:
        try:
            pages = await crawl_site(url, min(data.pages, 25))
        except Exception as e:
            return {"error": f"Couldn't read {url}: {e}"}
    else:
        text = await extract_text_from_url(url)
        if text.startswith("Error"):
            return {"error": text}
        pages = [(url, text)]
    if not pages:
        return {"error": "No readable text found on that page."}
    for page_url, text in pages:
        bot.knowledge_base = knowledge_sources.put(bot.knowledge_base, page_url, text)
    await db.commit()
    chunks = 0
    for page_url, text in pages:
        chunks += await _index(bot, text, page_url)
    total = sum(len(t) for _, t in pages)
    return {"status": "success", "pages": len(pages), "message": f"Read {len(pages)} page(s), {total} characters", "chunks_indexed": chunks}


@router.post("/knowledge/youtube")
async def crawl_youtube(data: KnowledgeCrawlRequest, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(data.bot_id, ctx, db)
    text = await extract_youtube_transcript(data.url)
    if text.startswith("Error"):
        return {"error": text}
    bot.knowledge_base = knowledge_sources.put(bot.knowledge_base, data.url.strip(), text)
    await db.commit()
    chunks = await _index(bot, text, data.url)
    return {"status": "success", "message": f"Extracted {len(text)} characters from YouTube", "chunks_indexed": chunks}


@router.get("/bots/{bot_id}/knowledge/sources")
async def list_sources(bot_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    return {"sources": knowledge_sources.listing(bot.knowledge_base or "")}


@router.delete("/bots/{bot_id}/knowledge/sources")
async def remove_source(bot_id: str, name: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Remove one website, video or file from the knowledge, then rebuild the search index without it."""
    bot = await get_owned_bot(bot_id, ctx, db)
    text, removed = knowledge_sources.remove(bot.knowledge_base or "", name)
    if not removed:
        raise HTTPException(status_code=404, detail="Source not found")
    bot.knowledge_base = text
    await db.commit()
    try:
        await asyncio.to_thread(delete_bot_knowledge, bot.bot_id)
    except Exception as e:
        logger.warning(f"Clearing vectors for {bot.bot_id} failed: {e}")
    if text.strip():
        await _index(bot, text, "reindex")
    return {"sources": knowledge_sources.listing(text), "knowledge_base": text}


@router.post("/bots/{bot_id}/knowledge/reindex")
async def reindex_knowledge(bot_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    if not bot.knowledge_base:
        return {"message": "No knowledge base to index", "chunks_indexed": 0}
    try:
        await asyncio.to_thread(delete_bot_knowledge, bot.bot_id)
    except Exception:
        pass
    chunks = await _index(bot, bot.knowledge_base, "reindex")
    return {"message": f"Successfully re-indexed {chunks} chunks", "chunks_indexed": chunks}


@router.get("/bots/{bot_id}/knowledge/stats")
async def knowledge_stats(bot_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    try:
        count = await asyncio.to_thread(get_bot_vector_count, bot.bot_id)
        return {"bot_id": bot.bot_id, "vector_count": count, "indexed": count > 0}
    except Exception as e:
        return {"bot_id": bot.bot_id, "vector_count": 0, "indexed": False, "error": str(e)}


@router.get("/bots/{bot_id}/leads")
async def get_bot_leads(bot_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    bot = await get_owned_bot(bot_id, ctx, db)
    conversations = (await db.execute(
        select(Conversation).where(Conversation.bot_id == bot.bot_id).order_by(Conversation.created_at.desc())
    )).scalars().all()
    return [
        {"id": c.conversation_id, "session_id": c.visitor_session_id, "data": c.captured_data, "created_at": c.created_at}
        for c in conversations if c.captured_data
    ]
