import asyncio
from database import engine
from sqlalchemy import text

async def check_columns():
    async with engine.connect() as conn:
        # Check if table exists
        result = await conn.execute(text("SELECT * FROM bots LIMIT 0"))
        print(f"Columns in 'bots' (cursor): {result.keys()}")
        
        # Check specific columns
        try:
            await conn.execute(text("SELECT ai_provider FROM bots LIMIT 1"))
            print("Successfully selected ai_provider")
        except Exception as e:
            print(f"Failed to select ai_provider: {e}")

if __name__ == "__main__":
    asyncio.run(check_columns())
