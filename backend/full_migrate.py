import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def run_migration():
    print(f"--- Starting Full Migration ---")
    print(f"Target: {DATABASE_URL.split('@')[-1]}")
    
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0,
            "command_timeout": 30
        }
    )
    
    try:
        from database import Base
        from models import User, Bot, Conversation, Message
        
        async with engine.begin() as conn:
            print("Connecting...")
            # Create all tables defined in models.py
            await conn.run_sync(Base.metadata.create_all)
            print("✓ Basic tables created/verified")
            
            # Ensure AI columns exist (Backup check)
            await conn.execute(text("ALTER TABLE bots ADD COLUMN IF NOT EXISTS ai_provider VARCHAR DEFAULT 'google'"))
            await conn.execute(text("ALTER TABLE bots ADD COLUMN IF NOT EXISTS ai_model VARCHAR DEFAULT 'gemini-2.0-flash'"))
            await conn.execute(text("ALTER TABLE bots ADD COLUMN IF NOT EXISTS ai_api_key VARCHAR"))
            print("✓ AI columns verified")
            
        print("\n✅ Migration complete! You can now start the backend.")
    except Exception as e:
        print(f"\n❌ Migration FAILED: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_migration())
