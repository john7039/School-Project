import datetime
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "/home/miniserver/School-Project/backend/econ.db"
MAX_RELEASE_DAYS = 45
MAX_MONTH_DAYS = 120

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
today = datetime.date.today()
fail = 0

for name, mdate, mrel in conn.execute(
        "SELECT name, MAX(date), MAX(release_date) FROM indicators GROUP BY name"):
    if mrel:
        days = (today - datetime.date.fromisoformat(mrel)).days
        limit, what = MAX_RELEASE_DAYS, "새 발표 없음"
    else:
        days = (today - datetime.date.fromisoformat(mdate)).days
        limit, what = MAX_MONTH_DAYS, "새 데이터 없음 (발표일 모름)"
    if days > limit:
        print(f"BAD {name} {days}일째 {what} (허용 {limit}일)")
        fail = 1
    else:
        print(f"OK {name} {days}일 전")

sys.exit(fail)


