import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def force_create_bot():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        user_id = "23984ca3-48fb-4fd4-ac0e-749e77b6706e"
        bot_id = "fd7068f9-431d-42b5-b677-66c3cd7126e0"
        
        print(f"Checking for user {user_id}...")
        res = await conn.execute(text("SELECT id FROM users WHERE id = :uid"), {"uid": user_id})
        if not res.scalar():
            print("User NOT found in users table!")
            # Let's see what users DO exist
            res = await conn.execute(text("SELECT id, email FROM users"))
            print(f"Existing users: {res.fetchall()}")
            return

        print(f"Creating bot {bot_id} for user {user_id}...")
        try:
            await conn.execute(text("""
                INSERT INTO bots (bot_id, user_id, bot_name, system_prompt, visual_config, created_at)
                VALUES (:bid, :uid, 'My AI Bot', 'You are a helpful assistant.', '{"color": "#3b82f6"}', NOW())
                ON CONFLICT (bot_id) DO UPDATE SET user_id = EXCLUDED.user_id
            """), {"bid": bot_id, "uid": user_id})
            await conn.commit()
            print("Bot created successfully!")
        except Exception as e:
            print(f"Failed to create bot: {e}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(force_create_bot())
