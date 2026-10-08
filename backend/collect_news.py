import sqlite3
import re
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

# 야후 파이낸스 종목별 RSS (키·할당량 없음). Alpha Vantage 뉴스 유료화 대체.
TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "META"]
FEED = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US"


def strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")


conn = sqlite3.connect("econ.db")
cur = conn.cursor()

total = 0
for t in TICKERS:
    try:
        root = ET.fromstring(fetch(FEED.format(t=t)))
    except Exception as e:
        print(f"뉴스 {t} 실패: {e.__class__.__name__} (건너뜀)")
        continue

    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = strip_html(item.findtext("description") or "")
        src = (item.findtext("source") or "Yahoo Finance").strip()
        pub = item.findtext("pubDate") or ""
        if not title or not link:
            continue
        try:
            published = parsedate_to_datetime(pub).strftime("%Y%m%dT%H%M%S")
        except Exception:
            continue
        cur.execute(
            "INSERT OR IGNORE INTO news (title, summary, source, published, sentiment, tickers, url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, desc, src, published, "", t, link))
        total += cur.rowcount

conn.commit()
conn.close()
print(f"뉴스 수집 완료 (신규 {total}건)")
