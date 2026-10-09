import json
import sqlite3
import datetime
from llm import generate_json
from newsfilter import is_junk

conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS daily (
  date TEXT PRIMARY KEY, url TEXT, title TEXT, source TEXT,
  sentiment TEXT, tickers TEXT, brief TEXT, summary_easy TEXT, glossary TEXT, pick_reason TEXT
)""")
# 기존 테이블에 brief 컬럼 없으면 추가 (1회 마이그레이션)
try:
    cur.execute("ALTER TABLE daily ADD COLUMN brief TEXT")
except sqlite3.OperationalError:
    pass
conn.commit()

# "오늘"은 뉴스 UTC 날짜가 아니라 보는 사람(KST) 기준으로 라벨.
# (뉴스 published는 UTC라 07시 실행 시점엔 KST 당일 뉴스가 0건 → 하루 밀림 방지)
iso = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime("%Y-%m-%d")

if cur.execute("SELECT 1 FROM daily WHERE date=?", (iso,)).fetchone():
    print(f"{iso}: 오늘 기사 이미 있음 — 생략")
    conn.close()
    raise SystemExit

# 이미 고른 적 있는 기사(url)는 제외 → 매일 새 기사 선정
used = set(r[0] for r in cur.execute("SELECT url FROM daily WHERE url IS NOT NULL AND url<>''"))

# 후보: 최근 수집된 뉴스에서 일반 경제 + 종목을 각각 최신순으로(잡음·중복 제외)
cols = "title, summary, source, sentiment, tickers, url"


def recent(where, limit=15):
    out = []
    for r in cur.execute(f"SELECT {cols} FROM news WHERE {where} ORDER BY published DESC LIMIT 60"):
        if r["url"] in used or is_junk(r["title"]):
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


rows = recent("tickers='경제'") + recent("tickers<>'경제'")
if not rows:
    print("최근 뉴스 후보 없음 — 다음 실행에서 재시도")
    conn.close()
    raise SystemExit

cand = "\n".join(
    f"[{i}] title: {r['title']}\n    summary: {(r['summary'] or '')[:300]}\n    tickers: {r['tickers']}"
    for i, r in enumerate(rows))
prompt = f"""아래는 최근 수집된 경제 뉴스 후보들이다.
경제 초보자가 오늘 하나를 읽고 배우기에 가장 좋은 기사 1건을 골라라.
기준: (1) 이해하기 쉬움 (2) 경제 기본 개념을 배울 수 있음 (3) 내용이 명확함 (4) 종목/지표와 연결되면 가점.
피할 것: 지나친 전문 분석, 단순 시세 나열, 광고성 기사.

아래 JSON 형식으로만 한국어로 답하라:
{{
  "chosen_index": <고른 기사 번호(정수)>,
  "sentiment": "<고른 기사가 시장·경제에 주는 영향: 반드시 '긍정' '부정' '중립' 중 하나만>",
  "pick_reason": "<초보자에게 이 기사를 고른 이유 1-2문장>",
  "brief": "<기사가 무슨 내용인지 1~2문장으로 간단히 요약>",
  "summary_easy": "<이것은 '요약'이 아니라 '설명'이다. 경제를 전혀 모르는 초보자도 이해하도록 아주 쉽고 자세하게 풀어써라. (1) 무슨 일이 일어났는지, (2) 여기 나오는 핵심 개념이 무엇인지 — 어려운 용어는 쉬운 말이나 일상 비유로 바로 풀어서, (3) 그래서 이게 왜 중요하고 어떤 의미인지를 단계적으로 설명. 쉬운 일상 언어로 5~7문장, 중학생도 이해할 수준으로.>",
  "glossary": [{{"term": "<용어>", "desc": "<초보자용 설명>"}}]
}}
glossary 는 기사에 나오는 어려운 경제 용어 2-4개.

후보:
{cand}"""
try:
    data = generate_json(prompt)
except Exception as e:
    print(f"{iso}: 실패 ({e.__class__.__name__}) — 다음 실행에서 재시도")
    conn.close()
    raise SystemExit

idx = int(data.get("chosen_index", 0))
if idx < 0 or idx >= len(rows):
    idx = 0
pick = rows[idx]
sent = data.get("sentiment", "").strip()
if sent not in ("긍정", "부정", "중립"):
    sent = "중립"
cur.execute(
    "INSERT INTO daily (date, url, title, source, sentiment, tickers, brief, summary_easy, glossary, pick_reason) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (iso, pick["url"], pick["title"], pick["source"], sent, pick["tickers"],
     data.get("brief", ""), data["summary_easy"], json.dumps(data["glossary"], ensure_ascii=False), data["pick_reason"]))
conn.commit()
conn.close()
print(f"{iso}: [{idx}] {pick['title'][:50]} — 큐레이션 완료")
