import os
import sqlite3
import time
import yfinance as yf
from fredapi import Fred
from dotenv import load_dotenv

load_dotenv()
FRED_KEY = os.environ["FRED_API_KEY"]

TICKERS = ["AAPL", "MSFT", "GOOGL", "TSLA"]
INDICATORS = {"CPI": "CPIAUCSL", "금리": "FEDFUNDS", "실업률": "UNRATE"}

conn = sqlite3.connect("econ.db")
cur = conn.cursor()

# 주가 (종목별로 실패해도 나머지 계속)
for ticker in TICKERS:
    try:
        data = yf.Ticker(ticker).history(period="2y")
        for date, row in data.iterrows():
            cur.execute(
                "INSERT OR IGNORE INTO prices (ticker, date, open, close) VALUES (?, ?, ?, ?)",
                (ticker, str(date.date()), row["Open"], row["Close"]))
    except Exception as e:
        print(f"주가 {ticker} 실패: {e.__class__.__name__} (건너뜀)")

conn.commit()  # 주가 먼저 저장 -> 지표가 실패해도 주가는 유지됨

# 경제지표 (시리즈별 3회 재시도, 실패해도 나머지 계속)
fred = Fred(api_key=FRED_KEY)
for name, series_id in INDICATORS.items():
    for attempt in range(3):
        try:
            series = fred.get_series(series_id, observation_start="2023-01-01")
            for date, value in series.items():
                if value == value:  # NaN 아닌 값만
                    cur.execute(
                        "INSERT OR IGNORE INTO indicators (name, date, value) VALUES (?, ?, ?)",
                        (name, str(date.date()), float(value)))
            break
        except Exception as e:
            if attempt < 2:
                print(f"지표 {name} 재시도 {attempt + 1}/3 ({e.__class__.__name__}) ...")
                time.sleep(5)
            else:
                print(f"지표 {name} 실패: {e.__class__.__name__} (건너뜀)")

conn.commit()
conn.close()
print("수집 완료")
