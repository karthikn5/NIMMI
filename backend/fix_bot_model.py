import asyncio
from models import Bot
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def fix_bots():
    async with AsyncSessionLocal() as session:
        print("Checking bots...")
        result = await session.execute(select(Bot))
        bots = result.scalars().all()
        for bot in bots:
            print(f"Bot {bot.bot_id} current model: {bot.ai_model}")
            if bot.ai_model == 'gemini-1.5-flash' or bot.ai_model is None:
                print(f"Updating Bot {bot.bot_id} to gemini-2.0-flash")
                bot.ai_model = 'gemini-2.0-flash'
            elif bot.ai_model == 'models/gemini-1.5-flash':
                 print(f"Updating Bot {bot.bot_id} to gemini-2.0-flash")
                 bot.ai_model = 'gemini-2.0-flash'
        
        await session.commit()
        print("Done.")

if __name__ == "__main__":
    asyncio.run(fix_bots())
