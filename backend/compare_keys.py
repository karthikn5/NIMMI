import os
import asyncio
from sqlalchemy import select
from database import async_session
from models import Bot
from dotenv import load_dotenv

load_dotenv()

async def compare_keys():
    default_key = os.getenv("GEMINI_API_KEY")
    print(f"Default Key: {default_key[:10]}..." if default_key else "Default Key: Not set")
    
    async with async_session() as db:
        result = await db.execute(select(Bot).where(Bot.bot_name == "IY bot"))
        bot = result.scalars().first()
        if bot:
            bot_key = bot.ai_api_key
            print(f"Bot Key: {bot_key[:10]}..." if bot_key else "Bot Key: Not set")
            if bot_key == default_key:
                print("Keys are IDENTICAL")
            else:
                print("Keys are DIFFERENT")

if __name__ == "__main__":
    asyncio.run(compare_keys())
