import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def fix_bot():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        # Get a valid user_id
        result = await conn.execute(text("SELECT id FROM users LIMIT 1"))
        user_id = result.scalar()
        
        if not user_id:
            print("No users found!")
            return
            
        bot_id = "fd7068f9-431d-42b5-b677-66c3cd7126e0"
        
        # Check if exists
        check = await conn.execute(text("SELECT bot_id FROM bots WHERE bot_id = :id"), {"id": bot_id})
        if check.scalar():
            print(f"Bot {bot_id} already exists.")
            return
            
        print(f"Inserting bot {bot_id} for user {user_id}...")
        await conn.execute(text("""
            INSERT INTO bots (bot_id, user_id, bot_name, system_prompt, is_active, created_at)
            VALUES (:bot_id, :user_id, 'Nimmi Assistant', 'You are a helpful assistant.', true, NOW())
        """), {"bot_id": bot_id, "user_id": user_id})
        await conn.commit()
        print("Bot inserted successfully.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_bot())
