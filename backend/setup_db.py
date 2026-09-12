import sqlite3

conn = sqlite3.connect("econ.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT,
    date TEXT,
    open REAL,
    close REAL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    date TEXT,
    value REAL
)
""")

conn.commit()
conn.close()
print("prices, indicators 테이블 생성 완료")
