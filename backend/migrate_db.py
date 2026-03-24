import asyncio
from dotenv import load_dotenv
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("NO DATABASE_URL in .env")
    exit(1)

engine = create_async_engine(DATABASE_URL)

async def migrate():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN ai_provider VARCHAR(50) DEFAULT 'google'"))
            print("Added ai_provider")
        except Exception as e: print("ai_provider:", e)
        
        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN ai_model VARCHAR(100) DEFAULT 'gemini-1.5-flash'"))
            print("Added ai_model")
        except Exception as e: print("ai_model:", e)
        
        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN ai_api_key VARCHAR(255)"))
            print("Added ai_api_key")
        except Exception as e: print("ai_api_key:", e)

asyncio.run(migrate())
