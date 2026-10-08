import json
import sqlite3
from llm import generate_json

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

dates = [r[0] for r in cur.execute(
    "SELECT DISTINCT substr(published,1,8) d FROM news ORDER BY d DESC")]

for ymd in dates:
    iso = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
    if cur.execute("SELECT 1 FROM daily WHERE date=?", (iso,)).fetchone():
        continue
    rows = cur.execute(
        "SELECT title, summary, source, sentiment, tickers, url FROM news "
        "WHERE substr(published,1,8)=? LIMIT 15", (ymd,)).fetchall()
    if not rows:
        continue
    cand = "\n".join(
        f"[{i}] title: {r['title']}\n    summary: {(r['summary'] or '')[:300]}\n    tickers: {r['tickers']}"
        for i, r in enumerate(rows))
    prompt = f"""아래는 {iso}에 발행된 경제 뉴스 후보들이다.
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
        continue
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
    print(f"{iso}: [{idx}] {pick['title'][:50]}")

conn.close()
print("큐레이션 완료")
