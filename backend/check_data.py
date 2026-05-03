import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv
import sys

# Force UTF-8 for printing
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def check_data():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        print("\n--- Bots with User IDs ---")
        result = await conn.execute(text("SELECT bot_id, bot_name, user_id FROM bots"))
        for row in result:
            name = row[1].encode('ascii', 'ignore').decode('ascii')
            print(f"Bot: {row[0]}, Name: {name}, User: {row[2]}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_data())
