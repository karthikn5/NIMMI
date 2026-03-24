import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def list_all_schemas():
    raw_url = DATABASE_URL.replace(":6543/", ":5432/")
    if "asyncpg" in raw_url:
        raw_url = raw_url.replace("+asyncpg", "")
    if "?" in raw_url:
        raw_url = raw_url.split("?")[0]
        
    conn = psycopg2.connect(raw_url)
    cur = conn.cursor()
    
    # List schemas
    cur.execute("SELECT nspname FROM pg_namespace;")
    schemas = [r[0] for r in cur.fetchall()]
    print(f"Schemas: {schemas}")
    
    # List tables in public
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
    print(f"Tables in public: {[r[0] for r in cur.fetchall()]}")
    
    # Check bots table specifically
    cur.execute("SELECT table_schema FROM information_schema.tables WHERE table_name = 'bots';")
    print(f"Bots table belongs to schema: {[r[0] for r in cur.fetchall()]}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    list_all_schemas()
