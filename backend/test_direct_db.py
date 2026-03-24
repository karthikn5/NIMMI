import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def test_direct():
    raw_url = DATABASE_URL.replace(":6543/", ":5432/")
    if "asyncpg" in raw_url:
        raw_url = raw_url.replace("+asyncpg", "")
    if "?" in raw_url:
        raw_url = raw_url.split("?")[0]
        
    print(f"Connecting to direct port 5432: {raw_url}...")
    try:
        conn = psycopg2.connect(raw_url)
        print("Connected successfully!")
        cur = conn.cursor()
        cur.execute("SELECT id, email FROM users;")
        print(f"Users in Direct DB: {cur.fetchall()}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Failed to connect to 5432: {e}")

if __name__ == "__main__":
    test_direct()
