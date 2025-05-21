import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect("finance.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    category TEXT,
    amount REAL,
    date TEXT
)
""")
conn.commit()

def add_transaction(user_id, type_, category, amount):
    cursor.execute(
        "INSERT INTO transactions (user_id, type, category, amount, date) VALUES (?, ?, ?, ?, ?)",
        (user_id, type_, category, amount, datetime.now().isoformat())
    )
    conn.commit()

def get_summary(user_id, days: int):
    since = datetime.now() - timedelta(days=days)
    cursor.execute("""
        SELECT type, SUM(amount) FROM transactions
        WHERE user_id = ? AND date >= ?
        GROUP BY type
    """, (user_id, since.isoformat()))
    return dict(cursor.fetchall())

def get_summary_by_category(user_id: int, days: int, type_: str):
    since = datetime.now() - timedelta(days=days)
    cursor.execute("""
        SELECT category, SUM(amount) FROM transactions
        WHERE user_id = ? AND type = ? AND date >= ?
        GROUP BY category
    """, (user_id, type_, since.isoformat()))
    return dict(cursor.fetchall())

def export_all_transactions(user_id: int):
    cursor.execute("""
        SELECT date, type, category, amount FROM transactions
        WHERE user_id = ?
        ORDER BY date DESC
    """, (user_id,))
    return cursor.fetchall()


