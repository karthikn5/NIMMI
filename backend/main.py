import os
import sys

import types

# Make both `backend.models` and direct sibling modules importable however uvicorn/gunicorn is started.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# When running in containers (e.g. Railway) where code is copied directly to /app,
# alias `backend` to this directory so `from backend.models import ...` resolves cleanly.
if "backend" not in sys.modules:
    backend_pkg = types.ModuleType("backend")
    backend_pkg.__path__ = [_HERE]
    sys.modules["backend"] = backend_pkg


import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_socketio import SocketManager

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import realtime  # noqa: E402
from database import init_db  # noqa: E402
from payments import router as payments_router  # noqa: E402
from routers.analytics import router as analytics_router  # noqa: E402
from routers.auth_routes import router as auth_router  # noqa: E402
from routers.bots import router as bots_router  # noqa: E402
from routers.chat import router as chat_router  # noqa: E402
from routers.handoffs import router as handoffs_router  # noqa: E402
from routers.integrations import router as integrations_router  # noqa: E402
from routers.team import router as team_router  # noqa: E402
from voice import scheduler as voice_scheduler  # noqa: E402
from voice.numbers_api import router as numbers_router  # noqa: E402
from voice.campaigns_api import router as campaigns_router  # noqa: E402
from voice.router import router as voice_router  # noqa: E402
from routers.whatsapp import router as whatsapp_router  # noqa: E402
from routers.workspace import router as workspace_router  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    if os.getenv("DISABLE_SCHEDULER", "").lower() != "true":
        voice_scheduler.start()
        if os.getenv("PINECONE_API_KEY"):
            import asyncio
            from vector_store import warm_up
            asyncio.ensure_future(warm_up())
    yield
    await voice_scheduler.stop()


app = FastAPI(title="Nimmi AI Backend", lifespan=lifespan)

# Browsers call from the dashboard and from customer websites (the widget), so CORS stays open;
# dashboard endpoints are protected by bearer tokens, not cookies.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)

realtime.register(SocketManager(app=app, mount_location="/socket.io", cors_allowed_origins="*"))

os.makedirs(os.path.join(_HERE, "static", "uploads"), exist_ok=True)
app.mount("/static", StaticFiles(directory=os.path.join(_HERE, "static")), name="static")

for router in (auth_router, bots_router, chat_router, handoffs_router, numbers_router, campaigns_router, voice_router,
               integrations_router, analytics_router, team_router, whatsapp_router, workspace_router):
    app.include_router(router)
app.include_router(payments_router, prefix="/api/payments")


@app.get("/")
async def root():
    return {"message": "Nimmi AI API is running"}


@app.get("/api/test")
async def test_api():
    return {"status": "ok", "message": "Backend is reachable"}


@app.get("/api/health")
async def health():
    from notify import channels, email
    from voice import exotel, sarvam, twilio
    return {
        "status": "ok",
        "services": {
            "ai": bool(os.getenv("GEMINI_API_KEY")),
            "knowledge": bool(os.getenv("PINECONE_API_KEY")),
            "payments": bool(os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET")),
            "email": email.is_configured(),
            "voice_engine": sarvam.configured(),
            "phone_calls": exotel.configured() or twilio.configured(),
            "whatsapp": channels.whatsapp_configured(),
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
