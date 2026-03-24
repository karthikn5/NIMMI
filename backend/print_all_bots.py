import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

async def print_all_bots():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT * FROM bots"))
        columns = result.keys()
        rows = result.fetchall()
        print(f"Found {len(rows)} bots in PostgreSQL.")
        for i, row in enumerate(rows):
            print(f"--- Bot {i+1} ---")
            data = dict(zip(columns, row))
            for key, value in data.items():
                print(f"{key}: {value}")
            print("-" * 20)
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(print_all_bots())
