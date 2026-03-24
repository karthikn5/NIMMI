import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def test():
    print(f"Connecting to: {DATABASE_URL.split('@')[-1]}") # Hide password
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            print("Connection successful:", res.fetchone())
    except Exception as e:
        print("Connection FAILED:", e)
    finally:
        await engine.dispose()

asyncio.run(test())
