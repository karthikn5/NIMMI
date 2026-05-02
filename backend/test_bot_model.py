import os
import google.generativeai as genai
import asyncio
from sqlalchemy import select
from database import async_session
from models import Bot
from dotenv import load_dotenv

load_dotenv()

async def test_bot_model():
    async with async_session() as db:
        result = await db.execute(select(Bot).where(Bot.bot_name == "IY bot"))
        bot = result.scalars().first()
        if not bot:
            print("IY bot not found")
            return
        
        key = bot.ai_api_key
        model_name = bot.ai_model 
        print(f"Testing with Bot Key: {key[:10]}... and Model: {model_name}")
        
        try:
            genai.configure(api_key=key, transport='rest')
            # Try the model exactly as stored
            print(f"Attempting model: {model_name}")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content("hi")
            print(f"Success! Response: {response.text}")
        except Exception as e:
            print(f"Error with {model_name}: {e}")
            
            # Try with models/ prefix
            print(f"Attempting model: models/{model_name}")
            try:
                model = genai.GenerativeModel(f"models/{model_name}")
                response = model.generate_content("hi")
                print(f"Success with prefix! Response: {response.text}")
            except Exception as e2:
                print(f"Error with models/{model_name}: {e2}")

if __name__ == "__main__":
    asyncio.run(test_bot_model())
