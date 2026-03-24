import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def final_insert():
    # Ensure we use 5432
    raw_url = DATABASE_URL
    if "asyncpg" in raw_url:
        raw_url = raw_url.replace("+asyncpg", "")
    
    # Strip params
    if "?" in raw_url:
        raw_url = raw_url.split("?")[0]
        
    print(f"Connecting to {raw_url}...")
    conn = psycopg2.connect(raw_url)
    conn.autocommit = True
    cur = conn.cursor()
    
    user_id = "23984ca3-48fb-4fd4-ac0e-749e77b6706e"
    bot_id = "fd7068f9-431d-42b5-b677-66c3cd7126e0"
    
    cur.execute("""
        INSERT INTO bots (bot_id, user_id, bot_name, system_prompt, visual_config, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (bot_id) DO UPDATE SET user_id = EXCLUDED.user_id;
    """, (bot_id, user_id, 'My AI Bot', 'You are a helpful assistant.', '{"color": "#3b82f6"}'))
    
    print("Bot fd7068f9 created/updated successfully on Port 5432.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    final_insert()
