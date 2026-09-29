import sqlite3
from llm import generate_json

TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "META"]
NAMES = {"AAPL": "애플", "MSFT": "마이크로소프트", "NVDA": "엔비디아",
         "AMZN": "아마존", "GOOGL": "알파벳(구글)", "TSLA": "테슬라", "META": "메타"}
DAYS = 7  # 종목별 최근 며칠치 브리핑

import json

conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS company_daily (
  ticker TEXT,
  date TEXT,
  close REAL,
  change_pct REAL,
  volume INTEGER,
  news_json TEXT,
  ai_summary TEXT,
  PRIMARY KEY (ticker, date)
)""")
conn.commit()

for t in TICKERS:
    rows = cur.execute(
        "SELECT date, close, volume FROM prices WHERE ticker=? ORDER BY date DESC LIMIT ?",
        (t, DAYS + 1)).fetchall()

    for i in range(len(rows) - 1):
        r = rows[i]
        prev = rows[i + 1]
        date = r["date"]

        if cur.execute("SELECT 1 FROM company_daily WHERE ticker=? AND date=?", (t, date)).fetchone():
            continue  # 이미 있음 (고정)

        close = r["close"]
        pclose = prev["close"]
        change = round((close - pclose) / pclose * 100, 2) if pclose else 0.0
        volume = r["volume"]

        ymd = date.replace("-", "")
        news = cur.execute(
            "SELECT title, sentiment FROM news WHERE tickers LIKE ? AND substr(published,1,8)=? LIMIT 5",
            (f"%{t}%", ymd)).fetchall()
        news_list = [{"title": n["title"], "sentiment": n["sentiment"]} for n in news]
        news_txt = "; ".join(n["title"] for n in news) or "관련 뉴스 없음"

        flow = ("상승 + 거래 활발 → 매수세" if change > 0.5
                else "하락 + 거래 → 매도세" if change < -0.5
                else "보합")

        prompt = f"""{NAMES[t]}({t})의 {date} 주식 상황이다.
종가 {close}, 전일 대비 {change}%, 거래량 {volume}. (추정 흐름: {flow})
관련 뉴스: {news_txt}

경제 초보자에게 "오늘 이 회사가 어땠는지"를 2~3문장으로 쉽게 설명하라.
매수세/매도세는 거래량과 등락으로 추정해 표현하고, 뉴스가 있으면 왜 그렇게 움직였는지 연결하라.
아래 JSON 형식으로만 한국어로 답하라:
{{"ai_summary": "<초보자용 설명>"}}"""

        try:
            data = generate_json(prompt)
            summary = data["ai_summary"]
        except Exception as e:
            print(f"{t} {date}: 실패 ({e.__class__.__name__}) — 다음 실행에서 재시도")
            continue

        cur.execute(
            "INSERT OR IGNORE INTO company_daily (ticker, date, close, change_pct, volume, news_json, ai_summary) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (t, date, close, change, volume, json.dumps(news_list, ensure_ascii=False), summary))
        conn.commit()
        print(f"{t} {date}: {change}% ({len(news_list)} news)")

conn.close()
print("종목별 큐레이션 완료")
