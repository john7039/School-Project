import os
import sqlite3
import yfinance as yf
from fredapi import Fred
from dotenv import load_dotenv

load_dotenv()
FRED_KEY = os.environ["FRED_API_KEY"]

TICKERS = ["AAPL", "MSFT", "GOOGL", "TSLA"]
INDICATORS = {"CPI": "CPIAUCSL", "금리": "FEDFUNDS", "실업률": "UNRATE"}

conn = sqlite3.connect("econ.db")
cur = conn.cursor()

cur.execute("DELETE FROM prices")
cur.execute("DELETE FROM indicators")

# 주가 (여러 종목)
for ticker in TICKERS:
    data = yf.Ticker(ticker).history(period="5d")
    for date, row in data.iterrows():
        cur.execute("INSERT INTO prices (ticker, date, open, close) VALUES (?, ?, ?, ?)", (ticker, str(date.date()), row["Open"], row["Close"]))

# 지표 (여러 개)
fred = Fred(api_key=FRED_KEY)
for name, series_id in INDICATORS.items():
    series = fred.get_series(series_id).tail()
    for date, value in series.items():
        cur.execute("INSERT INTO indicators (name, date, value) VALUES (?, ?, ?)", (name, str(date.date()), float(value)))

conn.commit()
conn.close()
print("저장 완료:", len(TICKERS), "종목 /", len(INDICATORS), "지표")
