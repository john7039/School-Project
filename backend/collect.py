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

for ticker in TICKERS:
    data = yf.Ticker(ticker).history(period="2y")
    for date, row in data.iterrows():
        cur.execute("INSERT OR IGNORE INTO prices (ticker, date, open, close) VALUES (?, ?, ?, ?)", (ticker, str(date.date()), row["Open"], row["Close"]))

fred = Fred(api_key=FRED_KEY)
for name, series_id in INDICATORS.items():
    series = fred.get_series(series_id, observation_start="2023-01-01")
    for date, value in series.items():
        if value == value:
            cur.execute("INSERT OR IGNORE INTO indicators (name, date, value) VALUES (?, ?, ?)", (name, str(date.date()), float(value)))

conn.commit()
conn.close()
print("수집 완료")
