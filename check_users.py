import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from prime_guardrails.data import Database
import sqlite3

db = Database()
conn = sqlite3.connect(db.db_path)
cursor = conn.cursor()

print("📊 Users in database:")
cursor.execute('SELECT user_id, name, email FROM users')
for row in cursor.fetchall():
    print(f"  - ID: {row[0]}, Name: {row[1]}, Email: {row[2]}")

conn.close()
