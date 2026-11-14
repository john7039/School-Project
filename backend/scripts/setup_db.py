# scripts/ 로 옮겼다(2026-11-14). backend/ 의 모듈과 econ.db 를 그대로 쓰도록
# 어디서 실행하든 backend/ 를 기준으로 돈다.
import os as _os, sys as _sys
_BACKEND = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _BACKEND)
_os.chdir(_BACKEND)

import sqlite3
conn = sqlite3.connect("econ.db")
cur = conn.cursor()
cur.execute("DROP TABLE IF EXISTS prices")
cur.execute("DROP TABLE IF EXISTS indicators")
cur.execute("CREATE TABLE prices (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, date TEXT, open REAL, close REAL, UNIQUE(ticker, date))")
# ⚠️ 운영 테이블과 맞춰 둔다. 예전에는 release_date 가 빠져 있어서, 이 스크립트로
#    다시 세우면 collect.py 의 자동 마이그레이션이 다시 돌아야 했다.
cur.execute("CREATE TABLE indicators ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " country TEXT NOT NULL DEFAULT 'US',"
            " name TEXT, date TEXT, value REAL, release_date TEXT,"
            " UNIQUE(country, name, date))")
conn.commit()
conn.close()
print("done")
