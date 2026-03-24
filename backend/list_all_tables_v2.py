import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
raw_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
if "?" in raw_url: raw_url = raw_url.split("?")[0]

try:
    conn = psycopg2.connect(raw_url)
    cur = conn.cursor()
    cur.execute("""
        SELECT schemaname, tablename 
        FROM pg_catalog.pg_tables 
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema');
    """)
    tables = cur.fetchall()
    print(f"Tables found: {tables}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
