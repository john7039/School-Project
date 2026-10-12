"""환율 수집 — 원/달러·원/유로 (yfinance, 무료·키 불필요).
기존 주가 수집과 동일하게 UPSERT로 축적(과거가 쌓여야 추이·그래프 가능)."""
import sqlite3
import yfinance as yf

PAIRS = {"USDKRW": "USDKRW=X", "EURKRW": "EURKRW=X"}

conn = sqlite3.connect("econ.db")
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS fx (
  pair TEXT,
  date TEXT,
  rate REAL,
  UNIQUE(pair, date)
)""")
conn.commit()

total = 0
for pair, symbol in PAIRS.items():
    try:
        data = yf.Ticker(symbol).history(period="6mo")
        if data.empty:
            print(f"환율 {pair}: 데이터 없음 (건너뜀)")
            continue
        n = 0
        for date, row in data.iterrows():
            rate = row["Close"]
            if rate != rate:  # NaN 제외
                continue
            cur.execute("INSERT OR REPLACE INTO fx (pair, date, rate) VALUES (?, ?, ?)",
                        (pair, str(date.date()), float(rate)))
            n += 1
        conn.commit()  # 쌍별로 바로 저장(뒤에서 실패해도 보존)
        total += n
        print(f"환율 {pair}: {n}일치 저장 (최신 {data.index[-1].date()} {data['Close'].iloc[-1]:.2f}원)")
    except Exception as e:
        print(f"환율 {pair} 실패: {e.__class__.__name__} (건너뜀)")

conn.close()
print(f"환율 수집 완료 (총 {total}행)")
