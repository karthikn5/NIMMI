import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
# Use psycopg2 (sync) for metadata checks
raw_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
if "?" in raw_url:
    raw_url = raw_url.split("?")[0]

try:
    conn = psycopg2.connect(raw_url)
    cur = conn.cursor()
    cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
    dbs = [r[0] for r in cur.fetchall()]
    print(f"Databases on server: {dbs}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
