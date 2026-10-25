"""매일 아침, 오늘 기사 중 한 건을 골라 분석해 둔다.

고르기·설명·기업별 영향은 analyze.py 가 한다. 검색(/api/news/pick)도 같은
모듈을 쓴다 — 입구는 둘이지만 분석은 한 벌이어야, 프롬프트를 고칠 때
한쪽만 바뀌는 사고가 안 난다.

분석 본체는 article_analysis(url 기준)에 저장하고, daily 는 "어느 날 어느
기사를 골랐나"를 가리킨다. 기존 daily 컬럼도 당분간 같이 채운다 — 되돌릴
수 있게 두는 것이고, 화면이 읽는 곳은 article_analysis 다.
"""
import datetime
import json
import sqlite3

import analyze
from newsfilter import is_junk

conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS daily (
  date TEXT PRIMARY KEY, url TEXT, title TEXT, source TEXT,
  sentiment TEXT, tickers TEXT, brief TEXT, summary_easy TEXT,
  glossary TEXT, pick_reason TEXT
)""")
for col in ("brief",):
    try:
        cur.execute(f"ALTER TABLE daily ADD COLUMN {col} TEXT")
    except sqlite3.OperationalError:
        pass
cur.execute("""CREATE TABLE IF NOT EXISTS article_analysis (
    url TEXT PRIMARY KEY,
    title TEXT, title_ko TEXT, source TEXT, published TEXT,
    pick_reason TEXT, brief TEXT, summary_easy TEXT,
    glossary TEXT, impacts TEXT,
    sentiment TEXT, sentiment_reason TEXT, created TEXT)""")
try:
    cur.execute("ALTER TABLE article_analysis ADD COLUMN title_only INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass                # 이미 있음
conn.commit()

# "오늘"은 뉴스 UTC 날짜가 아니라 보는 사람(KST) 기준으로 라벨.
# (뉴스 published는 UTC라 07시 실행 시점엔 KST 당일 뉴스가 0건 → 하루 밀림 방지)
iso = (datetime.datetime.now(datetime.timezone.utc)
       + datetime.timedelta(hours=9)).strftime("%Y-%m-%d")

if cur.execute("SELECT 1 FROM daily WHERE date=?", (iso,)).fetchone():
    print(f"{iso}: 오늘 기사 이미 있음 — 생략")
    conn.close()
    raise SystemExit

# 이미 고른 적 있는 기사(url)는 제외 → 매일 새 기사 선정
used = set(r[0] for r in cur.execute(
    "SELECT url FROM daily WHERE url IS NOT NULL AND url<>''"))

cols = "title, title_ko, summary, source, published, sentiment, tickers, url"


def has_body(r):
    # 요약이 제목보다 충분히 길면 '본문 있음'(제목만 반복이 아님)
    s = (r["summary"] or "").strip()
    return len(s) > len(r["title"].strip()) + 15


def recent(where, limit):
    pool = []
    for r in cur.execute(
            f"SELECT {cols} FROM news WHERE {where} ORDER BY published DESC LIMIT 80"):
        if r["url"] in used or is_junk(r["title"]):
            continue
        pool.append(dict(r))
    # 본문 있는 기사 우선(환각 방지), 각 그룹 내 최신순 유지
    return ([r for r in pool if has_body(r)]
            + [r for r in pool if not has_body(r)])[:limit]


# 경제(general) + 종목(시장) 뉴스를 함께 후보로. 종목 쪽이 더 풍부하고,
# 기업이 등장하는 기사라야 '기업별 영향'을 말할 수 있다.
# 검색으로 들어온 기사(tickers='검색')는 뺀다. 그건 사용자가 그때그때 물어본
# 주제라 '오늘의 추천' 후보로는 맞지 않고, 본문 요약도 없어서 설명이 얕아진다.
rows = (recent("tickers='경제'", 12)
        + recent("tickers NOT IN ('경제','검색')", 20))
if not rows:
    print("최근 뉴스 후보 없음 — 다음 실행에서 재시도")
    conn.close()
    raise SystemExit

try:
    idx = analyze.pick(rows)
except Exception as e:
    print(f"{iso}: 선정 실패 ({e.__class__.__name__}) — 다음 실행에서 재시도")
    conn.close()
    raise SystemExit

art = rows[idx]
res = analyze.full(art["title"], art["summary"], art["tickers"])

if not res["summary_easy"]:
    print(f"{iso}: 설명 생성 실패 — 다음 실행에서 재시도")
    conn.close()
    raise SystemExit

cur.execute(
    "INSERT OR REPLACE INTO article_analysis "
    "(url, title, title_ko, source, published, pick_reason, brief, "
    " summary_easy, glossary, impacts, sentiment, sentiment_reason, "
    " title_only, created) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
    (art["url"], art["title"], art["title_ko"], art["source"], art["published"],
     res["pick_reason"], res["brief"], res["summary_easy"],
     json.dumps(res["glossary"], ensure_ascii=False),
     json.dumps(res["impacts"], ensure_ascii=False),
     res["sentiment"], res["sentiment_reason"],
     0 if analyze._has_body(art["title"], art["summary"]) else 1))

cur.execute(
    "INSERT INTO daily (date, url, title, source, sentiment, tickers, brief, "
    " summary_easy, glossary, pick_reason) VALUES (?,?,?,?,?,?,?,?,?,?)",
    (iso, art["url"], art["title"], art["source"], res["sentiment"],
     art["tickers"], res["brief"], res["summary_easy"],
     json.dumps(res["glossary"], ensure_ascii=False), res["pick_reason"]))

conn.commit()
conn.close()

n = len(res["impacts"])
print(f"{iso}: [{idx}] {art['title'][:50]} "
      f"({res['sentiment']} · 기업 {n}곳) — 큐레이션 완료")
