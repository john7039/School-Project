import os, json, sqlite3, time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-3.6-flash"


def generate(prompt, tries=3):
    for attempt in range(tries):
        try:
            return client.models.generate_content(
                model=MODEL, contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"))
        except Exception as e:
            if attempt < tries - 1:
                print(f"  재시도 {attempt + 1}/{tries} ({e.__class__.__name__}) ...")
                time.sleep(8)
            else:
                raise

conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS daily (
  date TEXT PRIMARY KEY,
  url TEXT,
  title TEXT,
  source TEXT,
  sentiment TEXT,
  tickers TEXT,
  summary_easy TEXT,
  glossary TEXT,
  pick_reason TEXT
)""")
conn.commit()

dates = [r[0] for r in cur.execute(
    "SELECT DISTINCT substr(published,1,8) d FROM news ORDER BY d DESC")]

for ymd in dates:
    iso = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
    if cur.execute("SELECT 1 FROM daily WHERE date=?", (iso,)).fetchone():
        continue  # already curated (fixed)

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
기준: (1) 이해하기 쉬움 (2) 경제 기본 개념을 배울 수 있음 (3) 내용이 명확함(추측/루머 아님) (4) 종목/지표와 연결되면 가점.
피할 것: 지나친 전문 분석, 단순 시세 나열, 광고성 기사.

후보:
{cand}

아래 JSON 형식으로만 한국어로 답하라:
{{
  "chosen_index": <고른 기사 번호(정수)>,
  "pick_reason": "<초보자에게 이 기사를 고른 이유 1-2문장>",
  "summary_easy": "<초보자가 이해하도록 기사 내용을 풀어쓴 설명 3-4문장>",
  "glossary": [{{"term": "<용어>", "desc": "<초보자용 설명>"}}]
}}
glossary 는 기사에 나오는 어려운 경제 용어 2-4개."""

    try:
        resp = generate(prompt)
        data = json.loads(resp.text)
    except Exception as e:
        print(f"{iso}: 실패 ({e.__class__.__name__}) — 다음 실행에서 재시도")
        continue

    idx = int(data.get("chosen_index", 0))
    if idx < 0 or idx >= len(rows):
        idx = 0
    pick = rows[idx]

    cur.execute(
        "INSERT INTO daily (date, url, title, source, sentiment, tickers, summary_easy, glossary, pick_reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (iso, pick["url"], pick["title"], pick["source"], pick["sentiment"], pick["tickers"],
         data["summary_easy"], json.dumps(data["glossary"], ensure_ascii=False), data["pick_reason"]))
    conn.commit()
    print(f"{iso}: [{idx}] {pick['title'][:55]}")

conn.close()
print("큐레이션 완료")
