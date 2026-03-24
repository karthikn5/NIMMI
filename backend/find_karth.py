import sqlite3
import os

db_path = "nimmi_local.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT id, email, name FROM users WHERE email LIKE '%karth%'")
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f"MATCH: id={repr(row[0])}, email={repr(row[1])}, name={repr(row[2])}")
else:
    print("NO MATCH for karth")
conn.close()
