from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import shutil
import uuid
import os
import httpx
from dotenv import load_dotenv
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import Bot, User, Message, Conversation
from crawler import extract_text_from_url, extract_youtube_transcript
import asyncio
import logging
import traceback
from datetime import datetime, timedelta
import secrets
from mailer import send_reset_email

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Nimmi AI Backend")

from payments import router as payments_router
app.include_router(payments_router)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    origin = request.headers.get("origin")
    query_params = dict(request.query_params)
    logger.info(f"Incoming request: {request.method} {request.url} | Params: {query_params} | Origin: {origin}")
    response = await call_next(request)
    return response

# CORS Configuration
raw_origins = os.getenv("ALLOWED_ORIGINS", "")
dashboard_url = os.getenv("DASHBOARD_URL", "")
if raw_origins:
    allowed_origins = raw_origins.split(",")
else:
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3003",
    ]

# Auto-add Railway dashboard URL if set
if dashboard_url:
    allowed_origins.append(dashboard_url)
    # Also add without trailing slash
    allowed_origins.append(dashboard_url.rstrip("/"))

# Allow all railway.app subdomains
allowed_origins.extend([
    "https://nimmi-dashboard-production-91c6.up.railway.app",
    "https://nimmi-backend-production-2e2f.up.railway.app",
])


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Static Files
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def on_startup():
    from database import init_db
    # Run database initialization in background to prevent hanging uvicorn startup
    async def run_db_init():
        try:
            await init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Warning: Database initialization failed: {e}")
            
    asyncio.create_task(run_db_init())
    logger.info("Application starting up...")

# Models
class BotCreate(BaseModel):
    user_id: str # Temporary until real auth session
    bot_name: str
    system_prompt: Optional[str] = "You are a helpful assistant."
    visual_config: Optional[dict] = {"color": "#3b82f6", "logo_url": "", "position": "right"}

class ChatMessage(BaseModel):
    bot_id: str
    message: str
    visitor_session_id: str
    history: List[dict] = []

class VariableCapture(BaseModel):
    bot_id: str
    visitor_session_id: str
    variable_name: str
    variable_value: str

# Auth Models
class UserSignup(BaseModel):
    email: str
    name: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class SocialLogin(BaseModel):
    email: str
    name: Optional[str] = None
    provider: Optional[str] = "google"

class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetSubmit(BaseModel):
    token: str
    new_password: str

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None

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

class KnowledgeCrawlRequest(BaseModel):
    bot_id: str
    url: str

class YouTubeCrawlRequest(BaseModel):
    bot_id: str
    url: str

# Password hashing
import bcrypt as bcrypt_lib

def hash_password(password: str) -> str:
    return bcrypt_lib.hashpw(password.encode('utf-8'), bcrypt_lib.gensalt()).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt_lib.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

@app.get("/")
async def root():
    return {"message": "Nimmi AI API is running with PostgreSQL"}

# Auth Endpoints
@app.post("/api/auth/signup")
async def signup(user_data: UserSignup, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    user = result.scalars().first()
    if user:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # Create new user with hashed password
    new_user = User(
        email=user_data.email,
        name=user_data.name,
        password_hash=hash_password(user_data.password)
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"message": "Signup successful", "user_id": str(new_user.id), "name": new_user.name}

@app.post("/api/auth/login")
async def login(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    # Find user by email
    result = await db.execute(select(User).where(User.email == user_data.email))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Check if user has a password (old users might not)
    if not user.password_hash:
        raise HTTPException(status_code=401, detail="Please sign up again to set a password")
    
    # Verify password (run in thread pool to avoid blocking async loop)
    if not await asyncio.to_thread(verify_password, user_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    return {"message": "Login successful", "user_id": str(user.id), "name": user.name or ""}

@app.post("/api/auth/social")
async def social_login(user_data: SocialLogin, db: AsyncSession = Depends(get_db)):
    # Find user by email
    result = await db.execute(select(User).where(User.email == user_data.email))
    user = result.scalars().first()
    
    if not user:
        # Create new user for social login (no password)
        user = User(
            email=user_data.email,
            name=user_data.name,
            password_hash=None # No password for social login
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"New social user created: {user_data.email}")
    else:
        # Update name if it wasn't set
        if user_data.name and not user.name:
            user.name = user_data.name
            await db.commit()
            
    return {"message": "Success", "user_id": str(user.id), "name": user.name or ""}

@app.get("/api/auth/profile")
async def get_profile(user_id: str, db: AsyncSession = Depends(get_db)):
    try:
        user_uuid = uuid.UUID(user_id)
        result = await db.execute(select(User).where(User.id == str(user_uuid)))
        user = result.scalars().first()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid User ID format")
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "user_id": str(user.id),
        "email": user.email,
        "name": user.name or "",
        "subscription_tier": user.subscription_tier,
        "created_at": user.created_at.isoformat() if user.created_at else None
    }

@app.patch("/api/auth/profile")
async def update_profile(user_id: str, profile_data: ProfileUpdate, db: AsyncSession = Depends(get_db)):
    try:
        try:
            user_uuid = uuid.UUID(user_id)
            result = await db.execute(select(User).where(User.id == str(user_uuid)))
            user = result.scalars().first()
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid User ID format")
    except Exception as e:
        logger.error(f"Error in update_profile: {e}")
        with open("backend_traceback.log", "a") as f:
            f.write(f"Error in update_profile: {str(e)}\n")
            traceback.print_exc(file=f)
        raise HTTPException(status_code=500, detail=str(e))
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if profile_data.name is not None:
        user.name = profile_data.name
    if profile_data.email is not None:
        # Check if email is taken by another user
        existing = await db.execute(select(User).where(User.email == profile_data.email, User.id != user_id))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = profile_data.email
    
    await db.commit()
    return {"message": "Profile updated successfully"}

@app.post("/api/auth/forgot-password")
async def forgot_password(data: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalars().first()
    
    if not user:
        # Avoid user enumeration - return success anyway
        return {"message": "If that email exists, a reset link has been sent."}
    
    # Generate token
    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
    
    await db.commit()
    
    # Send email (async send)
    sent = await send_reset_email(user.email, token)
    
    return {"message": "If that email exists, a reset link has been sent."}

@app.post("/api/auth/reset-password")
async def reset_password(data: PasswordResetSubmit, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.reset_token == data.token))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    # Check expiry
    if user.reset_token_expires and user.reset_token_expires < datetime.utcnow():
        user.reset_token = None
        user.reset_token_expires = None
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    # Update password
    user.password_hash = hash_password(data.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    
    await db.commit()
    return {"message": "Password reset successful"}

@app.post("/api/bots/create")
async def create_bot(bot_data: BotCreate, db: AsyncSession = Depends(get_db)):
    try:
        user_uuid = uuid.UUID(bot_data.user_id)
        new_bot = Bot(
            user_id=str(user_uuid),
            bot_name=bot_data.bot_name,
            system_prompt=bot_data.system_prompt,
            visual_config=bot_data.visual_config
        )
        db.add(new_bot)
        await db.commit()
        # await db.refresh(new_bot)  # Skip refresh to avoid potential pooler schema sync issues
        return {"message": "Bot created", "bot_id": str(new_bot.bot_id)}
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid User ID format")

@app.get("/api/bots")
async def list_bots(user_id: str, db: AsyncSession = Depends(get_db)):
    try:
        user_uuid = uuid.UUID(user_id)
        result = await db.execute(select(Bot).where(Bot.user_id == str(user_uuid)))
        bots = result.scalars().all()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid User ID format")
    return [
        {
            "id": str(bot.bot_id),
            "name": bot.bot_name,
            "status": "Active" if bot.is_active else "Inactive",
            "conversations": 0, # Placeholder
            "lastActive": "Just now"
        }
        for bot in bots
    ]

@app.get("/api/bots/{bot_id}/config")
async def get_bot_config(bot_id: str, db: AsyncSession = Depends(get_db)):
    try:
        try:
            bot_uuid = uuid.UUID(bot_id)
            result = await db.execute(select(Bot).where(Bot.bot_id == str(bot_uuid)))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid Bot ID format")
            
        bot = result.scalars().first()
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        return {
            "bot_id": str(bot.bot_id),
            "bot_name": bot.bot_name,
            "system_prompt": bot.system_prompt,
            "visual_config": bot.visual_config,
            "flow_data": bot.flow_data,
            "knowledge_base": bot.knowledge_base,
            "ai_provider": bot.ai_provider,
            "ai_model": bot.ai_model,
            "ai_api_key": bot.ai_api_key,
            "is_active": bot.is_active,
            "export_unlocked": bot.export_unlocked,
            "created_at": bot.created_at
        }
    except Exception as e:
        with open("backend_traceback.log", "a") as f:
            f.write(f"Error in get_bot_config: {str(e)}\n")
            traceback.print_exc(file=f)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/bots/{bot_id}/config")
async def update_bot_config(bot_id: str, config_data: dict, db: AsyncSession = Depends(get_db)):
    try:
        try:
            bot_uuid = uuid.UUID(bot_id)
            result = await db.execute(select(Bot).where(Bot.bot_id == str(bot_uuid)))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid Bot ID format")
            
        bot = result.scalars().first()
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Map frontend fields to DB fields
        if "botName" in config_data:
            bot.bot_name = config_data["botName"]
        if "systemPrompt" in config_data:
            bot.system_prompt = config_data["systemPrompt"]
        if "knowledgeBase" in config_data:
            bot.knowledge_base = config_data["knowledgeBase"]
        if "aiProvider" in config_data:
            bot.ai_provider = config_data["aiProvider"]
        if "aiModel" in config_data:
            bot.ai_model = config_data["aiModel"]
        if "aiApiKey" in config_data:
            bot.ai_api_key = config_data["aiApiKey"]
            
        # Visual config grouping
        visual_fields = [
            "color", "botLogo", "position", "fontFamily", "textColor", 
            "inputBgColor", "inputTextColor", "userBubbleBg", "userBubbleText", 
            "assistantBubbleBg", "assistantBubbleText", "chatBgColor", 
            "headerHeight", "borderRadius", "launcherShape", "showTail", 
            "showLauncherBg", "logoSize", "rightPadding", "bottomPadding",
            "backgroundImage", "backgroundOpacity"
        ]
        
        current_visual = bot.visual_config or {}
        for field in visual_fields:
            if field in config_data:
                current_visual[field] = config_data[field]
        
        bot.visual_config = current_visual
        
        # Flow data
        bot.flow_data = {
            "nodes": config_data.get("nodes", []),
            "edges": config_data.get("edges", [])
        }
        
        await db.commit()
        return {"message": "Bot configuration updated"}
    except Exception as e:
        with open("backend_traceback.log", "a") as f:
            f.write(f"Error in update_bot: {str(e)}\n")
            traceback.print_exc(file=f)
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/bots/{bot_id}")
async def update_bot(bot_id: str, bot_data: dict, db: AsyncSession = Depends(get_db)):
    try:
        try:
            bot_uuid = uuid.UUID(bot_id)
            result = await db.execute(select(Bot).where(Bot.bot_id == str(bot_uuid)))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid Bot ID format")
            
        bot = result.scalars().first()
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        if "bot_name" in bot_data:
            bot.bot_name = bot_data["bot_name"]
        if "system_prompt" in bot_data:
            bot.system_prompt = bot_data["system_prompt"]
        if "visual_config" in bot_data:
            bot.visual_config = bot_data["visual_config"]
        if "flow_data" in bot_data:
            bot.flow_data = bot_data["flow_data"]
        if "knowledge_base" in bot_data:
            bot.knowledge_base = bot_data["knowledge_base"]
        if "ai_provider" in bot_data:
            bot.ai_provider = bot_data["ai_provider"]
        if "ai_model" in bot_data:
            bot.ai_model = bot_data["ai_model"]
        if "ai_api_key" in bot_data:
            bot.ai_api_key = bot_data["ai_api_key"]
        
        await db.commit()
        return {"message": "Bot updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_bot: {e}")
        with open("backend_traceback.log", "a") as f:
            f.write(f"Error in update_bot (PATCH): {str(e)}\n")
            traceback.print_exc(file=f)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/bots/{bot_id}")
async def delete_bot(bot_id: str, db: AsyncSession = Depends(get_db)):
    try:
        bot_uuid = uuid.UUID(bot_id)
        result = await db.execute(select(Bot).where(Bot.bot_id == str(bot_uuid)))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid Bot ID format")
        
    bot = result.scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    try:
        await db.delete(bot)
        await db.commit()
        return {"message": "Bot deleted successfully"}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting bot {bot_id}: {e}")
        with open("backend_traceback.log", "a") as f:
            f.write(f"Error deleting bot {bot_id}: {str(e)}\n")
            traceback.print_exc(file=f)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

from utils import extract_text_from_pdf, extract_text_from_txt, generate_ai_response

@app.post("/api/bots/{bot_id}/logo")
async def upload_logo(bot_id: str, file: UploadFile = File(...)):
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    
    # Read file content
    file_content = await file.read()
    
    # Try Supabase Storage first (persistent across Railway deploys)
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if supabase_url and supabase_key:
        try:
            bucket_name = "logos"
            upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{unique_filename}"
            
            async with httpx.AsyncClient() as client:
                # Try to upload to the bucket
                resp = await client.post(
                    upload_url,
                    headers={
                        "Authorization": f"Bearer {supabase_key}",
                        "apikey": supabase_key,
                        "Content-Type": file.content_type,
                    },
                    content=file_content,
                )
                
                if resp.status_code in (200, 201):
                    logo_url = f"{supabase_url}/storage/v1/object/public/{bucket_name}/{unique_filename}"
                    return {"logo_url": logo_url}
                else:
                    logger.warning(f"Supabase upload failed ({resp.status_code}): {resp.text}. Falling back to local storage.")
        except Exception as e:
            logger.warning(f"Supabase upload error: {e}. Falling back to local storage.")
    
    # Fallback: save to local filesystem
    file_path = os.path.join("static/uploads", unique_filename)
    
    def save_logo():
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
            
    await asyncio.to_thread(save_logo)
    
    # Return the URL for the logo
    logo_url = f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/static/uploads/{unique_filename}"
    return {"logo_url": logo_url}

@app.post("/api/bots/{bot_id}/background")
async def upload_background(bot_id: str, file: UploadFile = File(...)):
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"bg_{uuid.uuid4()}{file_extension}"
    
    # Read file content
    file_content = await file.read()
    
    # Try Supabase Storage first
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if supabase_url and supabase_key:
        try:
            bucket_name = "logos" # Reuse the same bucket
            upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{unique_filename}"
            
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    upload_url,
                    headers={
                        "Authorization": f"Bearer {supabase_key}",
                        "apikey": supabase_key,
                        "Content-Type": file.content_type,
                    },
                    content=file_content,
                )
                
                if resp.status_code in (200, 201):
                    bg_url = f"{supabase_url}/storage/v1/object/public/{bucket_name}/{unique_filename}"
                    return {"bg_url": bg_url}
        except Exception as e:
            logger.warning(f"Supabase upload error for bg: {e}")
    
    # Fallback to local
    file_path = os.path.join("static/uploads", unique_filename)
    
    def save_bg():
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
            
    await asyncio.to_thread(save_bg)
    
    # Return the URL
    bg_url = f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/static/uploads/{unique_filename}"
    return {"bg_url": bg_url}

@app.post("/api/bots/{bot_id}/knowledge/upload")
async def upload_knowledge(bot_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    try:
        bot_uuid = uuid.UUID(bot_id)
        result = await db.execute(select(Bot).where(Bot.bot_id == str(bot_uuid)))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid Bot ID format")
        
    bot = result.scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    extracted_text = ""
    if file.filename.endswith(".pdf"):
        extracted_text = await asyncio.to_thread(extract_text_from_pdf, file.file)
    elif file.filename.endswith(".txt"):
        extracted_text = await asyncio.to_thread(extract_text_from_txt, file.file)
    else:
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported")
    
    if not extracted_text:
        raise HTTPException(status_code=400, detail="Could not extract text from file")
    
    # Append to existing knowledge base
    if bot.knowledge_base:
        bot.knowledge_base += "\n\n" + extracted_text
    else:
        bot.knowledge_base = extracted_text
    
    await db.commit()
    return {"message": "Knowledge updated", "bot_id": bot_id, "filename": file.filename, "knowledge_base": bot.knowledge_base}

@app.post("/api/chat/message")
async def chat_message(chat: ChatMessage, db: AsyncSession = Depends(get_db)):
    try:
        bot_uuid = uuid.UUID(chat.bot_id)
        result = await db.execute(select(Bot).where(Bot.bot_id == str(bot_uuid)))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid Bot ID format")
        
    bot = result.scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    system_prompt = bot.system_prompt or "You are a helpful assistant."
    knowledge_context = bot.knowledge_base or ""
    
    logger.info(f"Generating AI response for Bot: {bot.bot_id}")
    logger.info(f"Query: {chat.message}")
    logger.info(f"Context Length: {len(knowledge_context)} characters")
    
    try:
        answer = generate_ai_response(
            system_prompt, 
            knowledge_context, 
            chat.message,
            provider=bot.ai_provider,
            model_name=bot.ai_model,
            api_key=bot.ai_api_key,
            is_system_use=False
        )
        return {
            "answer": answer,
            "bot_id": chat.bot_id
        }
    except Exception as e:
        with open("backend_traceback.log", "a") as f:
            f.write(f"Error in chat_message: {str(e)}\n")
            traceback.print_exc(file=f)
        logger.error(f"AI Response Error: {e}")
        return {
            "answer": "Sorry, I'm having trouble thinking right now. Please try again.",
            "bot_id": chat.bot_id
        }

@app.post("/api/chat/variables")
async def capture_variables(data: VariableCapture, db: AsyncSession = Depends(get_db)):
    logger.info(f"Capturing variable: {data.variable_name} = {data.variable_value} for bot: {data.bot_id} | Session: {data.visitor_session_id}")
    # Find or create conversation
    result = await db.execute(
        select(Conversation).where(
            Conversation.bot_id == data.bot_id,
            Conversation.visitor_session_id == data.visitor_session_id
        )
    )
    conv = result.scalars().first()
    
    if not conv:
        conv = Conversation(
            bot_id=data.bot_id,
            visitor_session_id=data.visitor_session_id,
            captured_data={}
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
    
    # Update captured data
    captured = dict(conv.captured_data or {})
    captured[data.variable_name] = data.variable_value
    conv.captured_data = captured
    
    db.add(conv)
    await db.commit()
    return {"status": "success", "captured": captured}

@app.post("/api/chat/ai-prompt")
async def ai_custom_prompt(data: AIPromptRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Bot).where(Bot.bot_id == data.bot_id))
    bot = result.scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    try:
        answer = generate_ai_response(
            "Execute the following specific prompt based on the context.", 
            data.context or bot.knowledge_base or "", 
            data.prompt,
            provider=bot.ai_provider,
            model_name=bot.ai_model,
            api_key=bot.ai_api_key,
            is_system_use=False
        )
        return {"answer": answer}
    except Exception as e:
        logger.error(f"AI Prompt Error: {e}")
        return {"answer": "Error generating AI response."}

@app.post("/api/chat/proxy-http")
async def proxy_http_request(data: HTTPProxyRequest):
    async with httpx.AsyncClient() as client:
        try:
            if data.method.upper() == "GET":
                resp = await client.get(data.url, headers=data.headers)
            elif data.method.upper() == "POST":
                resp = await client.post(data.url, headers=data.headers, json=data.body)
            elif data.method.upper() == "PATCH":
                resp = await client.patch(data.url, headers=data.headers, json=data.body)
            elif data.method.upper() == "DELETE":
                resp = await client.delete(data.url, headers=data.headers)
            else:
                return {"error": "Method not supported"}
            
            return {
                "status": resp.status_code,
                "data": resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text
            }
        except Exception as e:
            return {"error": str(e)}

@app.get("/api/bots/{bot_id}/leads")
async def get_bot_leads(bot_id: str, db: AsyncSession = Depends(get_db)):
    logger.info(f"Fetching leads for bot: {bot_id}")
    try:
        bot_uuid = uuid.UUID(bot_id)
        result = await db.execute(
            select(Conversation).where(
                Conversation.bot_id == str(bot_uuid)
            ).order_by(Conversation.created_at.desc())
        )
        conversations = result.scalars().all()
        
        # Filter conversations that have captured data manually to avoid DB comparison issues
        leads = [
            {
                "id": str(conv.conversation_id),
                "session_id": conv.visitor_session_id,
                "data": conv.captured_data,
                "created_at": conv.created_at
            }
            for conv in conversations if conv.captured_data and len(conv.captured_data) > 0
        ]
        
        logger.info(f"Found {len(leads)} leads for bot {bot_id}")
        return leads
    except Exception as e:
        logger.error(f"Error fetching leads: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.post("/api/integrations/google-sheets")
async def sync_to_google_sheets(data: GoogleSheetsSyncRequest):
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        # Check for service account key file
        key_path = "google_sheets_key.json"
        if not os.path.exists(key_path):
            return {"error": "Google Sheets Service Account key (google_sheets_key.json) not found in backend."}
            
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_file(key_path, scopes=scopes)
        service = build('sheets', 'v4', credentials=creds)
        
        # Prepare row data
        # First row is often headers, but for append we just provide values
        values = [[str(v) for v in data.data.values()]]
        
        body = {
            'values': values
        }
        
        result = service.spreadsheets().values().append(
            spreadsheetId=data.spreadsheet_id,
            range=f"{data.sheet_name}!A1",
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        
        return {"status": "success", "updatedRange": result.get('updates').get('updatedRange')}
        
    except Exception as e:
        logger.error(f"Google Sheets Sync Error: {e}")
        return {"error": str(e)}

@app.post("/api/knowledge/crawl")
async def crawl_website(data: KnowledgeCrawlRequest, db: AsyncSession = Depends(get_db)):
    try:
        text = await extract_text_from_url(data.url)
        if text.startswith("Error"):
            return {"error": text}
            
        bot_uuid = uuid.UUID(data.bot_id)
        result = await db.execute(select(Bot).where(Bot.bot_id == str(bot_uuid)))
        bot = result.scalars().first()
        if not bot:
            return {"error": "Bot not found"}
            
        # Append to knowledge base
        current_kb = bot.knowledge_base or ""
        new_kb = f"{current_kb}\n\n--- Source: {data.url} ---\n{text}"
        bot.knowledge_base = new_kb
        await db.commit()
        
        return {"status": "success", "message": f"Crawled {len(text)} characters from {data.url}"}
    except Exception as e:
        logger.error(f"Crawl Error: {e}")
        return {"error": str(e)}

@app.post("/api/knowledge/youtube")
async def crawl_youtube(data: YouTubeCrawlRequest, db: AsyncSession = Depends(get_db)):
    try:
        text = await extract_youtube_transcript(data.url)
        if text.startswith("Error"):
            return {"error": text}
            
        bot_uuid = uuid.UUID(data.bot_id)
        result = await db.execute(select(Bot).where(Bot.bot_id == str(bot_uuid)))
        bot = result.scalars().first()
        if not bot:
            return {"error": "Bot not found"}
            
        # Append to knowledge base
        current_kb = bot.knowledge_base or ""
        new_kb = f"{current_kb}\n\n--- YouTube Source ---\n{text}"
        bot.knowledge_base = new_kb
        await db.commit()
        
        return {"status": "success", "message": f"Extracted {len(text)} characters from YouTube"}
    except Exception as e:
        logger.error(f"YouTube Extract Error: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
