import psycopg2
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def migrate_sync():
    # Parse the URL for psycopg2 compatibility
    # remove the 'postgresql+asyncpg://' or 'postgresql://' prefix
    raw_url = DATABASE_URL
    if "asyncpg" in raw_url:
        raw_url = raw_url.replace("+asyncpg", "")
    
    # Strip query parameters for psycopg2
    if "?" in raw_url:
        raw_url = raw_url.split("?")[0]
    
    print(f"Connecting to database via psycopg2...")
    conn = psycopg2.connect(raw_url)
    conn.autocommit = True
    cur = conn.cursor()
    
    columns_to_add = [
        ("ai_provider", "VARCHAR DEFAULT 'google'"),
        ("ai_model", "VARCHAR DEFAULT 'gemini-1.5-flash'"),
        ("ai_api_key", "TEXT NULL")
    ]
    
    for col_name, col_type in columns_to_add:
        try:
            print(f"Adding column {col_name}...")
            cur.execute(f"ALTER TABLE bots ADD COLUMN {col_name} {col_type};")
            print(f"Column {col_name} added successfully.")
        except psycopg2.errors.DuplicateColumn:
            print(f"Column {col_name} already exists.")
        except Exception as e:
            print(f"Error adding {col_name}: {e}")
            
    # Verify columns
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'bots';")
    cols = [r[0] for r in cur.fetchall()]
    print(f"Final columns in bots: {cols}")
    
    cur.close()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate_sync()
