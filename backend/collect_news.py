import os
import sqlite3
import re
import json
import datetime
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv

load_dotenv()
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")

TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "META"]
COMPANY_LIMIT = 25   # 종목당 최근 N건
GENERAL_LIMIT = 30   # 일반 경제 뉴스 N건


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=25).read())


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")


def strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()


def unix_to_ymd(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")


def save(cur, title, summary, source, published, tickers, url):
    if not title or not url:
        return 0
    cur.execute(
        "INSERT OR IGNORE INTO news (title, summary, source, published, sentiment, tickers, url) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title.strip(), strip_html(summary)[:500], (source or "").strip(), published, "", tickers, url.strip()))
    return cur.rowcount


# ---- 1순위: Finnhub ----
def collect_finnhub(cur):
    total = 0
    today = datetime.date.today().isoformat()
    frm = (datetime.date.today() - datetime.timedelta(days=4)).isoformat()
    # 종목별 뉴스
    for t in TICKERS:
        arr = fetch_json(f"https://finnhub.io/api/v1/company-news?symbol={t}&from={frm}&to={today}&token={FINNHUB_KEY}")
        arr = sorted(arr, key=lambda a: a.get("datetime", 0), reverse=True)[:COMPANY_LIMIT]
        for a in arr:
            try:
                pub = unix_to_ymd(a["datetime"])
            except Exception:
                continue
            total += save(cur, a.get("headline", ""), a.get("summary", ""), a.get("source", "Finnhub"), pub, t, a.get("url", ""))
    # 일반 경제 뉴스
    arr = fetch_json(f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_KEY}")
    arr = sorted(arr, key=lambda a: a.get("datetime", 0), reverse=True)[:GENERAL_LIMIT]
    for a in arr:
        try:
            pub = unix_to_ymd(a["datetime"])
        except Exception:
            continue
        total += save(cur, a.get("headline", ""), a.get("summary", ""), a.get("source", "Finnhub"), pub, "경제", a.get("url", ""))
    return total


# ---- fallback: RSS (야후 종목별 + 구글뉴스 경제) ----
def collect_rss(cur):
    total = 0
    for t in TICKERS:
        try:
            root = ET.fromstring(fetch_text(f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US"))
        except Exception:
            continue
        for item in root.iter("item"):
            try:
                pub = parsedate_to_datetime(item.findtext("pubDate") or "").strftime("%Y%m%dT%H%M%S")
            except Exception:
                continue
            total += save(cur, item.findtext("title") or "", item.findtext("description") or "",
                          item.findtext("source") or "Yahoo Finance", pub, t, item.findtext("link") or "")
    for q in ["US economy", "Federal Reserve interest rates", "inflation CPI", "stock market"]:
        try:
            root = ET.fromstring(fetch_text(f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US&ceid=US:en"))
        except Exception:
            continue
        for item in list(root.iter("item"))[:12]:
            title = (item.findtext("title") or "").strip()
            src = (item.findtext("source") or "Google News").strip()
            if src and title.endswith(" - " + src):
                title = title[: -(len(src) + 3)].strip()
            if title.lower() == q.lower() or len(title) < 20:
                continue
            try:
                pub = parsedate_to_datetime(item.findtext("pubDate") or "").strftime("%Y%m%dT%H%M%S")
            except Exception:
                continue
            total += save(cur, title, item.findtext("description") or "", src, pub, "경제", item.findtext("link") or "")
    return total


conn = sqlite3.connect("econ.db")
cur = conn.cursor()
try:
    if not FINNHUB_KEY:
        raise RuntimeError("FINNHUB_KEY 없음")
    total = collect_finnhub(cur)
    src = "Finnhub"
except Exception as e:
    print(f"Finnhub 실패({e.__class__.__name__}) → RSS fallback")
    total = collect_rss(cur)
    src = "RSS"
conn.commit()
conn.close()
print(f"뉴스 수집 완료 ({src}, 신규 {total}건)")
