import sqlite3
conn = sqlite3.connect("econ.db")
conn.execute("CREATE TABLE IF NOT EXISTS news (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, summary TEXT, source TEXT, published TEXT, sentiment TEXT, tickers TEXT, url TEXT, UNIQUE(title, published))")
conn.commit()
conn.close()
print("news 테이블 생성 완료")
