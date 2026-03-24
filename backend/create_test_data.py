import asyncio
import uuid
from database import async_session
from models import User, Bot

async def create_test_data():
    async with async_session() as session:
        # Create a test user if not exists
        user_id = "59502828-090c-4394-a4b5-0c58f000300d" # Example ID
        user = User(
            id=user_id,
            email="test@example.com",
            name="Test User",
            password_hash="dummy_hash"
        )
        session.add(user)
        try:
            await session.commit()
            print(f"User {user_id} created.")
        except:
            await session.rollback()
            print(f"User {user_id} already exists or error.")

        # Create a test bot
        bot_id = "d9c5ea9c-f22a-4442-bc0b-4fb9663f6d7c" # ID used in test_api_capture.py
        bot = Bot(
            bot_id=bot_id,
            user_id=user_id,
            bot_name="Test Bot",
            system_prompt="You are a test assistant.",
            is_active=True
        )
        session.add(bot)
        try:
            await session.commit()
            print(f"Bot {bot_id} created.")
        except Exception as e:
            await session.rollback()
            print(f"Error creating bot: {e}")

if __name__ == "__main__":
    asyncio.run(create_test_data())
