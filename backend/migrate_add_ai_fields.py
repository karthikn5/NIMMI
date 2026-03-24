import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def migrate():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        print("Adding missing columns to 'bots' table...")
        
        # Add ai_provider
        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN ai_provider VARCHAR DEFAULT 'google';"))
            print("Added ai_provider")
        except Exception as e:
            print(f"ai_provider might already exist: {e}")
            
        # Add ai_model
        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN ai_model VARCHAR DEFAULT 'gemini-2.0-flash';"))
            print("Added ai_model")
        except Exception as e:
            print(f"ai_model might already exist: {e}")
            
        # Add ai_api_key
        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN ai_api_key TEXT;"))
            print("Added ai_api_key")
        except Exception as e:
            print(f"ai_api_key might already exist: {e}")
            
        print("Migration complete.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
