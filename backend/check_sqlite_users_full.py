import sqlite3
import os

db_path = "nimmi_local.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT id, email, name, password_hash FROM users")
rows = cursor.fetchall()
for row in rows:
    print(f"ID: {row[0]}")
    print(f"Email: '{row[1]}'")
    print(f"Name: '{row[2]}'")
    print(f"Hash: {row[3][:10] if row[3] else 'None'}...")
    print("-" * 20)
conn.close()
