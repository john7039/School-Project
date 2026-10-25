"""daily 에 들어 있던 분석을 article_analysis 로 옮긴다 (1회).

왜 — 분석이 두 군데에 따로 살면 금방 어긋난다. 실제로 지금 검색으로 만든
분석에는 기업별 영향이 있는데 매일 추천 기사에는 없다. "검색한 건 기업이
나오고 오늘 기사는 안 나오는" 상태다.

옮긴 뒤 daily 는 "어느 날 어느 기사를 골랐나"만 들고 있고, 내용은 전부
article_analysis 한 군데에 있다. 기존 컬럼은 지우지 않는다 — 되돌릴 수 있게.

impacts 는 비워 둔다. 옛 기사들은 기업별 영향을 만든 적이 없다.
redo_daily.py 가 나중에 채운다.
"""
import json
import sqlite3

conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS article_analysis (
    url TEXT PRIMARY KEY,
    title TEXT, title_ko TEXT, source TEXT, published TEXT,
    pick_reason TEXT, brief TEXT, summary_easy TEXT,
    glossary TEXT, impacts TEXT,
    sentiment TEXT, sentiment_reason TEXT, created TEXT)""")
conn.commit()

rows = cur.execute("SELECT * FROM daily ORDER BY date").fetchall()
print(f"daily {len(rows)}행")

no_url = [r["date"] for r in rows if not (r["url"] or "").strip()]
if no_url:
    print(f"  url 없는 행 {len(no_url)}건 — 옮길 수 없음: {no_url[:5]}")

urls = [r["url"] for r in rows if (r["url"] or "").strip()]
print(f"  url 있는 행 {len(urls)}건 · 서로 다른 url {len(set(urls))}개")

moved = skipped = 0
for r in rows:
    url = (r["url"] or "").strip()
    if not url:
        skipped += 1
        continue
    if cur.execute("SELECT 1 FROM article_analysis WHERE url=?", (url,)).fetchone():
        skipped += 1          # 같은 기사를 이미 옮겼거나 검색으로 분석했음
        continue

    # news 에서 발행 시각과 번역 제목을 끌어온다 (없으면 비움)
    n = cur.execute("SELECT published, title_ko FROM news WHERE url=?", (url,)).fetchone()

    cur.execute(
        "INSERT INTO article_analysis "
        "(url, title, title_ko, source, published, pick_reason, brief, "
        " summary_easy, glossary, impacts, sentiment, sentiment_reason, created) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
        (url, r["title"], n["title_ko"] if n else None, r["source"],
         n["published"] if n else None,
         r["pick_reason"], r["brief"], r["summary_easy"],
         r["glossary"] or "[]", "[]",          # impacts 는 비움
         r["sentiment"], ""))
    moved += 1

conn.commit()
total = cur.execute("SELECT COUNT(*) FROM article_analysis").fetchone()[0]
print(f"옮김 {moved}건 · 건너뜀 {skipped}건 · article_analysis 총 {total}행")
conn.close()
