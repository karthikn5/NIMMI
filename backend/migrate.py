"""
Migration script to add name and password_hash columns to users table
Run this once to update your Supabase database
"""
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def run_migration():
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0
        }
    )
    
    async with engine.begin() as conn:
        # Add name column if it doesn't exist
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR"))
            print("✓ Added 'name' column")
        except Exception as e:
            print(f"Note: name column - {e}")
        
        # Add password_hash column if it doesn't exist
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR"))
            print("✓ Added 'password_hash' column")
        except Exception as e:
            print(f"Note: password_hash column - {e}")

        # Add reset_token and reset_token_expires columns if they don't exist
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR"))
            print("✓ Added 'reset_token' column")
        except Exception as e:
            print(f"Note: reset_token column - {e}")

        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP WITH TIME ZONE"))
            print("✓ Added 'reset_token_expires' column")
        except Exception as e:
            print(f"Note: reset_token_expires column - {e}")
        
        # Add flow_data column to bots table if it doesn't exist
        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN IF NOT EXISTS flow_data JSONB DEFAULT '{}'::jsonb"))
            print("✓ Added 'flow_data' column to bots table")
        except Exception as e:
            print(f"Note: flow_data column - {e}")

        # Add knowledge_base column to bots table
        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN IF NOT EXISTS knowledge_base TEXT"))
            print("✓ Added 'knowledge_base' column to bots table")
        except Exception as e:
            print(f"Note: knowledge_base column - {e}")

        # Add is_active column to bots table
        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"))
            print("✓ Added 'is_active' column to bots table")
        except Exception as e:
            print(f"Note: is_active column - {e}")

        # Add captured_data column to conversations table
        try:
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS captured_data JSONB DEFAULT '{}'::jsonb"))
            print("✓ Added 'captured_data' column to conversations table")
        except Exception as e:
            print(f"Note: captured_data column - {e}")
            
        # Add AI Provider columns
        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN IF NOT EXISTS ai_provider VARCHAR DEFAULT 'google'"))
            print("✓ Added 'ai_provider' column")
        except Exception as e:
            print(f"Note: ai_provider column - {e}")

        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN IF NOT EXISTS ai_model VARCHAR DEFAULT 'gemini-2.0-flash'"))
            print("✓ Added 'ai_model' column")
        except Exception as e:
            print(f"Note: ai_model column - {e}")

        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN IF NOT EXISTS ai_api_key VARCHAR"))
            print("✓ Added 'ai_api_key' column")
        except Exception as e:
            print(f"Note: ai_api_key column - {e}")

        # Add export_unlocked column to bots table
        try:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN IF NOT EXISTS export_unlocked BOOLEAN DEFAULT FALSE"))
            print("✓ Added 'export_unlocked' column")
        except Exception as e:
            print(f"Note: export_unlocked column - {e}")
    
    await engine.dispose()
    print("\n✅ Migration complete!")

if __name__ == "__main__":
    asyncio.run(run_migration())
