import asyncio
from database import async_session
from models import Bot
from sqlalchemy.future import select

async def check_bot(bot_id):
    async with async_session() as session:
        result = await session.execute(select(Bot).where(Bot.bot_id == bot_id))
        bot = result.scalars().first()
        if bot:
            print(f"Bot Name: {bot.bot_name}")
            print(f"AI Provider: {bot.ai_provider}")
            print(f"AI Model: {bot.ai_model}")
            print(f"AI API Key: {bot.ai_api_key}")
            print(f"Is Active: {bot.is_active}")
        else:
            print(f"Bot with ID {bot_id} NOT FOUND.")

if __name__ == "__main__":
    bot_id = "894264ec-d748-4060-90a0-e5b60ba58eb5"
    asyncio.run(check_bot(bot_id))
