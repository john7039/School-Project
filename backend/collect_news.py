import os
import sqlite3
import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.environ["ALPHA_VANTAGE_KEY"]
TICKERS = ["AAPL", "MSFT", "GOOGL", "TSLA"]

conn = sqlite3.connect("econ.db")
cur = conn.cursor()

for ticker in TICKERS:
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&limit=10&apikey={KEY}"
    r = requests.get(url)
    data = r.json()
    feed = data.get("feed", [])
    for item in feed:
        title = item.get("title", "")
        summary = item.get("summary", "")
        source = item.get("source", "")
        published = item.get("time_published", "")
        overall = item.get("overall_sentiment_label", "")
        rel = [t["ticker"] for t in item.get("ticker_sentiment", [])]
        tickers_str = ",".join(rel)
        link = item.get("url", "")
        cur.execute("INSERT OR IGNORE INTO news (title, summary, source, published, sentiment, tickers, url) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, summary, source, published, overall, tickers_str, link))

conn.commit()
conn.close()
print("뉴스 수집 완료")
