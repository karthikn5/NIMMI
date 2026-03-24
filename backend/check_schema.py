import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def check_columns():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'bots'
        """))
        columns = [row[0] for row in result]
        print(f"Columns in 'bots' table: {columns}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_columns())
