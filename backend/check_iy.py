import asyncio
from sqlalchemy import select
from database import async_session
from models import Bot
import json

async def check_iy_bot():
    async with async_session() as db:
        result = await db.execute(select(Bot).where(Bot.bot_name == "IY bot"))
        bot = result.scalars().first()
        if not bot:
            print("IY bot not found")
            return
        
        print(f"Bot ID: {bot.bot_id}")
        print(f"Model: {bot.ai_model}")
        print(f"Provider: {bot.ai_provider}")
        print(f"API Key: {bot.ai_api_key[:5] + '...' if bot.ai_api_key else 'None'}")
        print(f"Knowledge Base Length: {len(bot.knowledge_base) if bot.knowledge_base else 0}")
        print(f"System Prompt Length: {len(bot.system_prompt) if bot.system_prompt else 0}")

if __name__ == "__main__":
    asyncio.run(check_iy_bot())
