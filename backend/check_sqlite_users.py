import sqlite3
import os

db_path = "nimmi_local.db"
if not os.path.exists(db_path):
    print(f"Database {db_path} not found.")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, email, name FROM users")
        rows = cursor.fetchall()
        if rows:
            print(f"Found {len(rows)} users:")
            for row in rows:
                print(row)
        else:
            print("No users found.")
    except sqlite3.OperationalError as e:
        print(f"Error: {e}")
    conn.close()
