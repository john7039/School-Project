# scripts/ 로 옮겼다(2026-11-14). backend/ 의 모듈과 econ.db 를 그대로 쓰도록
# 어디서 실행하든 backend/ 를 기준으로 돈다.
import os as _os, sys as _sys
_BACKEND = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _BACKEND)
_os.chdir(_BACKEND)

import sqlite3
conn = sqlite3.connect("econ.db")
conn.execute("CREATE TABLE IF NOT EXISTS news (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, summary TEXT, source TEXT, published TEXT, sentiment TEXT, tickers TEXT, url TEXT, UNIQUE(title, published))")
conn.commit()
conn.close()
print("news 테이블 생성 완료")
