import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def repair_all():
    raw_url = DATABASE_URL
    if "asyncpg" in raw_url:
        raw_url = raw_url.replace("+asyncpg", "")
    if "?" in raw_url:
        raw_url = raw_url.split("?")[0]
        
    print(f"Connecting to {raw_url}...")
    conn = psycopg2.connect(raw_url)
    conn.autocommit = True
    cur = conn.cursor()
    
    # IDs to ensure exist
    user_ids = ["23984ca3-48fb-4fd4-ac0e-749e77b6706e", "51ce6d64-445b-434b-8b91-3a883dd148f4"]
    bot_id = "fd7068f9-431d-42b5-b677-66c3cd7126e0"
    
    for uid in user_ids:
        print(f"Ensuring user {uid} exists...")
        cur.execute("SELECT id FROM users WHERE id = %s", (uid,))
        if not cur.fetchone():
            print(f"Inserting user {uid}...")
            cur.execute("INSERT INTO users (id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING;", (uid, "recovery@example.com"))
    
    print(f"Ensuring bot {bot_id} exists...")
    # Use the active account user id for the bot
    active_uid = "23984ca3-48fb-4fd4-ac0e-749e77b6706e"
    cur.execute("""
        INSERT INTO bots (bot_id, user_id, bot_name, system_prompt, visual_config, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (bot_id) DO UPDATE SET user_id = EXCLUDED.user_id;
    """, (bot_id, active_uid, 'My AI Bot', 'You are a helpful assistant.', '{"color": "#3b82f6"}'))
    
    print("Repair complete.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    repair_all()
