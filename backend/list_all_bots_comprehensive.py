import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv
import sqlite3

load_dotenv()

def check_sqlite():
    DB_PATH = "nimmi_local.db"
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT bot_id, bot_name, ai_api_key FROM bots")
            rows = cursor.fetchall()
            print(f"--- SQLite (nimmi_local.db) ---")
            for row in rows:
                print(f"ID: {row[0]}, Name: {row[1]}, API Key: {row[2] if row[2] else 'None'}")
        except sqlite3.OperationalError as e:
            print(f"Error reading SQLite: {e}")
        conn.close()
    else:
        print(f"SQLite DB {DB_PATH} not found")

async def check_postgres():
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print("DATABASE_URL not found in .env")
        return
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    
    try:
        engine = create_async_engine(DATABASE_URL)
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT bot_id, bot_name, ai_api_key FROM bots"))
            rows = result.fetchall()
            print(f"--- PostgreSQL ({DATABASE_URL}) ---")
            for row in rows:
                print(f"ID: {row[0]}, Name: {row[1]}, API Key: {row[2] if row[2] else 'None'}")
        await engine.dispose()
    except Exception as e:
        print(f"Error reading PostgreSQL: {e}")

if __name__ == "__main__":
    print("Listing ALL bots across both databases...")
    check_sqlite()
    asyncio.run(check_postgres())
