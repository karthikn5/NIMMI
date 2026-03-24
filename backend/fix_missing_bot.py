import asyncio
import os
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from models import Bot, User

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def create_missing_bot():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Get the first user id
        result = await session.execute(select(User.id).limit(1))
        user_id = result.scalar()
        
        if not user_id:
            print("No users found in database!")
            return
            
        bot_id = "fd7068f9-431d-42b5-b677-66c3cd7126e0"
        
        # Check if it exists now
        result = await session.execute(select(Bot).where(Bot.bot_id == bot_id))
        if result.scalars().first():
            print(f"Bot {bot_id} already exists.")
            return

        print(f"Creating bot {bot_id} for user {user_id}...")
        new_bot = Bot(
            bot_id=bot_id,
            user_id=user_id,
            bot_name="Nimmi Assistant",
            system_prompt="You are a helpful assistant.",
            ai_provider="google",
            ai_model="gemini-1.5-flash"
        )
        session.add(new_bot)
        await session.commit()
        print("Bot created successfully.")
        
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_missing_bot())
