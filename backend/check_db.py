
import asyncio
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine, get_db
from models import Bot
from sqlalchemy.orm import sessionmaker


async def check_bots():
    # Correct way to get a session manually for a script
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        result = await session.execute(select(Bot))
        bots = result.scalars().all()
        with open("bot_configs.txt", "w") as f:
            f.write("--- BOT CONFIG CHECK ---\n")
            for bot in bots:
                f.write(f"Bot ID: {bot.bot_id}\n")
                f.write(f"Name: {bot.bot_name}\n")
                f.write(f"Provider: {bot.ai_provider}\n")
                f.write(f"Model: {bot.ai_model}\n")
                key_preview = f"{bot.ai_api_key[:8]}..." if bot.ai_api_key else "None"
                f.write(f"API Key (Prefix): {key_preview}\n")
                f.write("-" * 25 + "\n")

if __name__ == "__main__":
    asyncio.run(check_bots())
