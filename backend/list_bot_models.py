import asyncio
import google.generativeai as genai
from sqlalchemy import select
from database import async_session
from models import Bot
from dotenv import load_dotenv

load_dotenv()

async def list_models_for_bot():
    async with async_session() as db:
        result = await db.execute(select(Bot).where(Bot.bot_name == "IY bot"))
        bot = result.scalars().first()
        if not bot:
            print("IY bot not found")
            return
        
        key = bot.ai_api_key
        print(f"Listing models for Bot Key: {key[:10]}...")
        
        try:
            genai.configure(api_key=key, transport='rest')
            for m in genai.list_models():
                print(f"Model: {m.name} | Methods: {m.supported_generation_methods}")
        except Exception as e:
            print(f"Error listing models: {e}")

if __name__ == "__main__":
    asyncio.run(list_models_for_bot())
