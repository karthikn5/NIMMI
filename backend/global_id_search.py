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

ID_TO_FIND = "894264ec-d748-4060-90a0-e5b50ba58eb5"

async def global_search():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        tables = ["users", "bots", "conversations", "messages"]
        for table in tables:
            print(f"Searching in table: {table}...")
            result = await conn.execute(text(f"SELECT * FROM {table}"))
            columns = result.keys()
            rows = result.fetchall()
            for row in rows:
                row_dict = dict(zip(columns, row))
                if any(str(v).lower() == ID_TO_FIND.lower() for v in row_dict.values()):
                    print(f"MATCH FOUND in {table}!")
                    for k, v in row_dict.items():
                        print(f"  {k}: {v}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(global_search())
