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

# ── 1단계: 후보 중 best 1건 "선정"만 (번호만 받음) ──
cand = "\n".join(
    f"[{i}] {r['title']}  (tickers: {r['tickers']})"
    for i, r in enumerate(rows))
pick_prompt = f"""아래는 최근 수집된 뉴스 후보들이다(번호순).
목표: 경제 초보자에게 "오늘 무슨 일이 있었고, 그게 경제에 어떤 영향을 주는지"를 설명하기 가장 좋은 기사 1건을 골라라.

반드시 '실제로 일어난 경제·시장·기업·정책 사건' 중에서 고를 것:
- 예: 주가·유가·환율·금리·물가의 변동, 기업 실적·투자·구조조정, 정부·중앙은행 정책, 경제에 영향 주는 국제·정치 뉴스.
제외할 것 (경제와 직접 관련 없는 생활·취미·연예·스포츠·가십):
- 예: 포켓몬 카드, 우정·인간관계, 맛집, 경제 영향이 뚜렷하지 않은 단순 사건사고.
그중 초보자가 이해하기 쉽고 경제 영향이 뚜렷한 1건을 골라라.

아래 JSON 형식으로만 답하라:
{{"chosen_index": <고른 기사 번호(정수)>, "pick_reason": "<이 기사가 '오늘의 경제 사건'으로 적절한 이유 1-2문장, 한국어>"}}

후보:
{cand}"""
try:
    sel = generate_json(pick_prompt)
except Exception as e:
    print(f"{iso}: 선정 실패 ({e.__class__.__name__}) — 다음 실행에서 재시도")
    conn.close()
    raise SystemExit

idx = int(sel.get("chosen_index", 0))
if idx < 0 or idx >= len(rows):
    idx = 0
pick = rows[idx]

# ── 2단계: 고른 "그 기사 하나"만 주고 설명·감정·용어 생성 (제목↔설명 100% 일치) ──
exp_prompt = f"""아래 기사를 경제 초보자용으로 설명하라. 핵심은 "오늘 무슨 일이 있었고, 그게 경제에 어떤 영향을 주는지".
제목: {pick['title']}
요약: {(pick['summary'] or pick['title'])[:400]}

아래 JSON 형식으로만 한국어로 답하라:
{{
  "sentiment": "<이 사건이 경제·시장에 주는 영향. 반드시 '긍정'/'부정'/'중립' 중 하나. 악재(유가·물가·금리 상승, 규제, 전쟁·사고, 실적 부진, 주가 하락)면 '부정', 호재(실적 호조·성장·완화, 주가 상승)면 '긍정'. 영향 방향이 조금이라도 분명하면 반드시 '긍정' 또는 '부정'으로, 정말 판단이 불가능할 때만 '중립'. 중립을 남발하지 말 것>",
  "brief": "<오늘 무슨 일이 있었는지 1~2문장으로 요약>",
  "summary_easy": "<경제를 전혀 모르는 초보자도 이해하도록 쉽고 자세하게. 반드시 이 순서로: (1) 무슨 일이 일어났는지, (2) 그 일이 경제·시장에 어떤 영향을 주는지 — 물가·금리·주가·기업·우리 생활 등과 연결해서, (3) 그래서 왜 중요한지. 어려운 용어는 일상 비유로 바로 풀어서. 5~7문장, 중학생도 이해할 수준. 반드시 위 '제목'의 사건에 대해서만 쓸 것(다른 주제로 새지 말 것).>",
  "glossary": [{{"term": "<용어>", "desc": "<초보자용 설명>"}}]
}}
glossary 는 기사에 나오는 어려운 경제 용어 2-4개."""
try:
    data = generate_json(exp_prompt)
except Exception as e:
    print(f"{iso}: 설명 실패 ({e.__class__.__name__}) — 다음 실행에서 재시도")
    conn.close()
    raise SystemExit

sent = (data.get("sentiment", "") or "").strip()
if sent not in ("긍정", "부정", "중립"):
    sent = "중립"
cur.execute(
    "INSERT INTO daily (date, url, title, source, sentiment, tickers, brief, summary_easy, glossary, pick_reason) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (iso, pick["url"], pick["title"], pick["source"], sent, pick["tickers"],
     data.get("brief", ""), data.get("summary_easy", ""), json.dumps(data.get("glossary", []), ensure_ascii=False), sel.get("pick_reason", "")))
conn.commit()
conn.close()
print(f"{iso}: [{idx}] {pick['title'][:50]} ({sent}) — 큐레이션 완료")
