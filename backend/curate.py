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


def has_body(r):
    # 요약이 제목보다 충분히 길면 '본문 있음'(제목만 반복이 아님)
    s = (r["summary"] or "").strip()
    return len(s) > len(r["title"].strip()) + 15


def recent(where, limit):
    pool = []
    for r in cur.execute(f"SELECT {cols} FROM news WHERE {where} ORDER BY published DESC LIMIT 80"):
        if r["url"] in used or is_junk(r["title"]):
            continue
        pool.append(r)
    # 본문 있는 기사 우선(환각 방지), 각 그룹 내 최신순 유지
    return ([r for r in pool if has_body(r)] + [r for r in pool if not has_body(r)])[:limit]


# 경제(general) + 종목(시장) 뉴스를 함께 후보로 (종목이 더 풍부·경제적) → step1이 '현재 경제 상황' 기준으로 선별
rows = recent("tickers='경제'", 12) + recent("tickers<>'경제'", 20)
if not rows:
    print("최근 뉴스 후보 없음 — 다음 실행에서 재시도")
    conn.close()
    raise SystemExit

# ── 1단계: 후보 중 best 1건 "선정"만 (번호만 받음) ──
cand = "\n".join(
    f"[{i}] {r['title']}  (tickers: {r['tickers']})"
    for i, r in enumerate(rows))
pick_prompt = f"""아래는 최근 수집된 뉴스 후보들이다(번호순).
목표: 경제 초보자가 "지금 경제가 어떻게 돌아가고 있는지(현재 경제 상황)"를 공부하기 가장 좋은 기사 1건을 골라라.

골라야 할 것 — 지금 실제로 벌어지고 있는 경제·시장의 상황과 움직임을 보여주는 기사:
- 예: 주가·유가·환율·금리·물가의 현재 움직임, 기업 실적·동향, 정부·중앙은행 정책, 경제 흐름에 영향 주는 사건.
반드시 경제·시장·금융·기업·정책 기사 중에서만 고를 것. 아래는 **절대 고르지 마라**:
- 스포츠(NBA·축구 등)·연예·생활·취미·가십 (경제와 무관)
- 시점과 무관한 일반 상식·조언성 기사 ("새 투자자가 흔히 하는 실수", "~하는 법", "~해야 하는 이유" 같은 것)
초보자가 이해하기 쉽고 '현재 경제 상황'이 잘 드러나는 경제 기사 1건을 골라라.

아래 JSON 형식으로만 답하라:
{{"chosen_index": <고른 기사 번호(정수)>}}

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
exp_prompt = f"""아래 기사를 경제 초보자용으로 설명하라. 핵심은 "지금 무슨 일이 벌어지고 있고, 그게 경제에 어떤 영향을 주는지".
제목: {pick['title']}
요약: {(pick['summary'] or pick['title'])[:400]}

중요: **위 제목·요약에 실제로 있는 내용만으로 설명하라.** 본문에 없는 원인·배경·숨은 의미를 추측하거나 지어내지 말 것. 정보가 부족하면 제목이 말하는 사실만 담백하게 설명하라.

아래 JSON 형식으로만 한국어로 답하라:
{{
  "pick_reason": "<이 기사가 '지금의 경제 상황'을 공부하기 좋은 이유 1-2문장. 반드시 이 기사 내용에 대해서만>",
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

# ── 3단계: 감정만 전용으로 판정 (예시 기준, 중립 쏠림 방지) ──
sent_prompt = f"""다음 경제 뉴스가 '시장·경제에 주는 영향'을 분류하라.
제목: {pick['title']}
요약: {(pick['summary'] or pick['title'])[:300]}

분류 기준(예시):
- 부정: 주가·지수 하락, 약세, 하락·침체 경고나 우려, 물가·유가 상승, 금리 '추가 인상'·긴축, 규제·제재, 실적 부진, 전쟁·사고, 차입비용 상승
- 긍정: 주가 상승, 강세·반등, 실적 호조, 성장, 금리 인하·'인상 보류'·완화적 신호(시장에 호재), 규제 완화, 개선, 수요 증가
- 중립: 방향이 전혀 없는 단순 정보 전달, 변동 없음, 호재·악재가 비슷하게 섞인 혼조
주의: '금리 인상을 미룬다/보류한다'는 긴축이 아니라 '완화적'이므로 긍정이다. 단어만 보지 말고 시장에 좋은지 나쁜지로 판단하라.
조금이라도 호재 쪽이면 '긍정', 악재 쪽이면 '부정'. 정말 방향이 없을 때만 '중립'. 중립을 남발하지 말 것.

아래 JSON 형식으로만 답하라:
{{"sentiment": "<긍정|부정|중립>"}}"""
try:
    sd = generate_json(sent_prompt)
    sent = (sd.get("sentiment", "") or "").strip()
except Exception:
    sent = ""
if sent not in ("긍정", "부정", "중립"):
    sent = "중립"
cur.execute(
    "INSERT INTO daily (date, url, title, source, sentiment, tickers, brief, summary_easy, glossary, pick_reason) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (iso, pick["url"], pick["title"], pick["source"], sent, pick["tickers"],
     data.get("brief", ""), data.get("summary_easy", ""), json.dumps(data.get("glossary", []), ensure_ascii=False), data.get("pick_reason", "")))
conn.commit()
conn.close()
print(f"{iso}: [{idx}] {pick['title'][:50]} ({sent}) — 큐레이션 완료")
