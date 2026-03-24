import asyncio
import asyncpg
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def check_asyncpg():
    # Parse the URL to remove the 'postgresql+asyncpg://' prefix for asyncpg.connect
    parsed = urlparse(DATABASE_URL.replace("+asyncpg", ""))
    
    # Extract components
    user = parsed.username
    password = parsed.password
    host = parsed.hostname
    port = parsed.port
    database = parsed.path.lstrip("/")
    
    print(f"Connecting to {host}:{port} / {database} as {user}...")
    
    conn = await asyncpg.connect(
        user=user,
        password=password,
        host=host,
        port=port,
        database=database,
        # Remove prepared_statement_cache_size if it's in the string, or handle manually
        ssl='require' # Supabase usually requires SSL
    )
    
    try:
        # Check columns of bots table
        rows = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'bots'
        """)
        columns = [row['column_name'] for row in rows]
        print(f"Columns in 'bots': {columns}")
        
        # List all bots
        bot_rows = await conn.fetch("SELECT bot_id, bot_name FROM bots")
        print(f"Bots: {[dict(r) for r in bot_rows]}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_asyncpg())
