import sqlite3
import os

DB_PATH = "nimmi_local.db"
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT bot_id, bot_name, ai_api_key FROM bots")
        rows = cursor.fetchall()
        print(f"Bots in SQLite ({DB_PATH}):")
        for row in rows:
            print(f"ID: {row[0]}, Name: {row[1]}, API Key: {row[2][:8] if row[2] else 'None'}...")
    except sqlite3.OperationalError as e:
        print(f"Error reading SQLite: {e}")
    conn.close()
else:
    print(f"SQLite DB {DB_PATH} not found")
