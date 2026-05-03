import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def run_migration():
    if not DATABASE_URL:
        print("DATABASE_URL not found in environment")
        return

    print("Starting migration on database...")
    
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0
        }
    )
    
    async with engine.begin() as conn:
        # Add bot_id to subscriptions
        try:
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS bot_id VARCHAR"))
            print("Added bot_id column to subscriptions table")
        except Exception as e:
            print("Error adding bot_id to subscriptions:", e)
        
        # Add bot_id to transactions
        try:
            await conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS bot_id VARCHAR"))
            print("Added bot_id column to transactions table")
        except Exception as e:
            print("Error adding bot_id to transactions:", e)

        # Add plan_name to transactions (for history)
        try:
            await conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS plan_name VARCHAR"))
            print("Added plan_name column to transactions table")
        except Exception as e:
            print("Error adding plan_name to transactions:", e)

    await engine.dispose()
    print("Migration v2 complete!")

if __name__ == "__main__":
    asyncio.run(run_migration())
