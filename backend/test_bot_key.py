import os
import google.generativeai as genai
import asyncio
from sqlalchemy import select
from database import async_session
from models import Bot
from dotenv import load_dotenv

load_dotenv()

async def test_bot_key():
    async with async_session() as db:
        result = await db.execute(select(Bot).where(Bot.bot_name == "IY bot"))
        bot = result.scalars().first()
        if not bot:
            print("IY bot not found")
            return
        
        key = bot.ai_api_key
        print(f"Testing with Bot Key: {key[:10]}...")
        
        try:
            genai.configure(api_key=key, transport='rest')
            model = genai.GenerativeModel('gemini-1.5-flash')
            # Test a simple message
            print("Testing 'hi'...")
            response = model.generate_content("hi")
            print(f"Response to 'hi': {response.text}")
            
            # Test the failing message
            print("Testing 'can i get karthikeyan contact number'...")
            response = model.generate_content("can i get karthikeyan contact number")
            print(f"Response to contact number: {response.text}")
            
        except Exception as e:
            print(f"Error with Bot Key: {e}")

if __name__ == "__main__":
    asyncio.run(test_bot_key())
