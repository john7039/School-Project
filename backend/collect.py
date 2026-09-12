import os
import sqlite3
import yfinance as yf
from fredapi import Fred
from dotenv import load_dotenv

load_dotenv()
FRED_KEY = os.environ["FRED_API_KEY"]

conn = sqlite3.connect("econ.db")
cur = conn.cursor()

# 주가 (AAPL)
data = yf.Ticker("AAPL").history(period="5d")
for date, row in data.iterrows():
    cur.execute("INSERT INTO prices (ticker, date, open, close) VALUES (?, ?, ?, ?)", ("AAPL", str(date.date()), row["Open"], row["Close"]))

# 지표 (CPI)
fred = Fred(api_key=FRED_KEY)
cpi = fred.get_series("CPIAUCSL").tail()
for date, value in cpi.items():
    cur.execute("INSERT INTO indicators (name, date, value) VALUES (?, ?, ?)", ("CPI", str(date.date()), float(value)))

conn.commit()
conn.close()
print("저장 완료")
