"""기존 company_daily 행을 삭제하지 않고 제자리에서 갱신.
최근 날짜의 ai_summary + 뉴스별 감정(Ollama 추론)을 다시 채운다."""
import sqlite3
import json
from llm import generate_json

TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "META"]
NAMES = {"AAPL": "애플", "MSFT": "마이크로소프트", "NVDA": "엔비디아",
         "AMZN": "아마존", "GOOGL": "알파벳(구글)", "TSLA": "테슬라", "META": "메타"}
SINCE = "2026-10-02"  # 이 날짜부터 갱신

conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

rows = cur.execute(
    "SELECT ticker, date, close, change_pct, volume FROM company_daily WHERE date>=? ORDER BY date, ticker",
    (SINCE,)).fetchall()
print(f"갱신 대상 {len(rows)}건")

for r in rows:
    t, date = r["ticker"], r["date"]
    change, volume = r["change_pct"], r["volume"]
    ymd = date.replace("-", "")
    news = cur.execute(
        "SELECT title FROM news WHERE tickers LIKE ? AND substr(published,1,8)=? LIMIT 5",
        (f"%{t}%", ymd)).fetchall()
    news_titles = [n["title"] for n in news]
    news_numbered = "\n".join(f"  [{j}] {ti}" for j, ti in enumerate(news_titles)) or "  (없음)"

    flow = ("상승 + 거래 활발 → 매수세" if change > 0.5
            else "하락 + 거래 → 매도세" if change < -0.5
            else "보합")

    prompt = f"""{NAMES[t]}({t})의 {date} 주식 상황이다.
종가 {r['close']}, 전일 대비 {change}%, 거래량 {volume}. (추정 흐름: {flow})
관련 뉴스(번호순):
{news_numbered}

경제 초보자에게 "오늘 이 회사가 어땠는지"를 2~3문장으로 쉽게 설명하라.
매수세/매도세는 거래량과 등락으로 추정해 표현하고, 뉴스가 있으면 왜 그렇게 움직였는지 연결하라.
또한 위 뉴스 각각이 이 회사에 주는 영향을 '긍정'/'부정'/'중립' 중 하나로 분류하라.
아래 JSON 형식으로만 한국어로 답하라:
{{"ai_summary": "<초보자용 설명>",
  "news_sentiments": [<뉴스 번호순으로 '긍정'/'부정'/'중립' 값, 뉴스 개수만큼>]}}"""

    try:
        data = generate_json(prompt)
        summary = data["ai_summary"]
    except Exception as e:
        print(f"{t} {date}: 실패 ({e.__class__.__name__}) — 건너뜀(기존 유지)")
        continue

    sents = data.get("news_sentiments", []) or []
    news_list = []
    for j, ti in enumerate(news_titles):
        s = (sents[j] if j < len(sents) else "")
        s = s.strip() if isinstance(s, str) else ""
        if s not in ("긍정", "부정", "중립"):
            s = "중립"
        news_list.append({"title": ti, "sentiment": s})

    cur.execute(
        "UPDATE company_daily SET news_json=?, ai_summary=? WHERE ticker=? AND date=?",
        (json.dumps(news_list, ensure_ascii=False), summary, t, date))
    conn.commit()
    print(f"{t} {date}: {change}% ({len(news_list)} news)")

conn.close()
print("종목별 감정 갱신 완료")
