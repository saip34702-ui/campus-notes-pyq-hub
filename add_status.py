import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("""
ALTER TABLE files
ADD COLUMN status TEXT DEFAULT 'pending'
""")

conn.commit()
conn.close()

print("Status column added successfully!")