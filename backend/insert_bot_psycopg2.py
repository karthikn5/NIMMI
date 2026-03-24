import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def insert_bot_sync():
    raw_url = DATABASE_URL
    if "asyncpg" in raw_url:
        raw_url = raw_url.replace("+asyncpg", "")
    if "?" in raw_url:
        raw_url = raw_url.split("?")[0]
    
    print(f"Connecting to database via psycopg2...")
    conn = psycopg2.connect(raw_url)
    conn.autocommit = True
    cur = conn.cursor()
    
    user_id = "23984ca3-48fb-4fd4-ac0e-749e77b6706e"
    bot_id = "fd7068f9-431d-42b5-b677-66c3cd7126e0"
    
    print(f"Checking for user {user_id}...")
    cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    if not cur.fetchone():
        print(f"User {user_id} NOT found!")
        return

    print(f"Forcing insert of bot {bot_id}...")
    # Use a raw SQL insert with all columns
    cur.execute("""
        INSERT INTO bots (bot_id, user_id, bot_name, system_prompt, visual_config, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (bot_id) DO UPDATE SET user_id = EXCLUDED.user_id;
    """, (bot_id, user_id, 'My AI Bot', 'You are a helpful assistant.', '{"color": "#3b82f6"}'))
    
    print("Bot inserted/updated successfully.")
    
    cur.execute("SELECT bot_id FROM bots WHERE bot_id = %s", (bot_id,))
    if cur.fetchone():
        print("Verification: Bot IS in DB.")
    else:
        print("Verification: Bot IS STILL MISSING!")
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    insert_bot_sync()
