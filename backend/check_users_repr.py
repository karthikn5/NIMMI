import sqlite3
import os

db_path = "nimmi_local.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT id, email, name FROM users")
rows = cursor.fetchall()
for row in rows:
    print(f"User: id={repr(row[0])}, email={repr(row[1])}, name={repr(row[2])}")
conn.close()
