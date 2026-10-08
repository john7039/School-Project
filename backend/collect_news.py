import sqlite3
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

# 무료·키없음 RSS. 1) 야후 파이낸스 종목별(회사 뉴스) + 2) 구글뉴스 경제 검색(거시 뉴스)
TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "META"]
YAHOO = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US"

# 거시 경제 뉴스(영어) — 초보자 학습용 기사 풀 넓히기
GOOGLE_QUERIES = [
    "US economy", "Federal Reserve interest rates", "inflation CPI", "stock market",
]
GOOGLE = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
GOOGLE_LIMIT = 12  # 피드당 최근 N건만


def strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")


def save(cur, title, desc, src, pub, tickers, link):
    if not title or not link:
        return 0
    try:
        published = parsedate_to_datetime(pub).strftime("%Y%m%dT%H%M%S")
    except Exception:
        return 0
    cur.execute(
        "INSERT OR IGNORE INTO news (title, summary, source, published, sentiment, tickers, url) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, desc, src, published, "", tickers, link))
    return cur.rowcount


conn = sqlite3.connect("econ.db")
cur = conn.cursor()
total = 0

# 1) 야후 종목별 (회사 뉴스 → 종목별 탭 관련 뉴스에도 쓰임)
for t in TICKERS:
    try:
        root = ET.fromstring(fetch(YAHOO.format(t=t)))
    except Exception as e:
        print(f"야후 {t} 실패: {e.__class__.__name__} (건너뜀)")
        continue
    for item in root.iter("item"):
        total += save(cur,
                      (item.findtext("title") or "").strip(),
                      strip_html(item.findtext("description") or ""),
                      (item.findtext("source") or "Yahoo Finance").strip(),
                      item.findtext("pubDate") or "",
                      t,
                      (item.findtext("link") or "").strip())

# 2) 구글뉴스 경제 검색 (거시 뉴스 → tickers="경제"로 태깅, 종목 필터엔 안 걸림)
for q in GOOGLE_QUERIES:
    try:
        root = ET.fromstring(fetch(GOOGLE.format(q=urllib.parse.quote(q))))
    except Exception as e:
        print(f"구글 '{q}' 실패: {e.__class__.__name__} (건너뜀)")
        continue
    qlow = {x.lower() for x in GOOGLE_QUERIES}
    for item in list(root.iter("item"))[:GOOGLE_LIMIT]:
        title = (item.findtext("title") or "").strip()
        src = (item.findtext("source") or "Google News").strip()
        # 구글뉴스 제목은 "헤드라인 - 출처" 형태 → 출처 꼬리 제거
        if src and title.endswith(" - " + src):
            title = title[: -(len(src) + 3)].strip()
        # 보일러플레이트(검색어 메아리)·너무 짧은 제목 제외
        if title.lower() in qlow or len(title) < 20:
            continue
        total += save(cur, title,
                      strip_html(item.findtext("description") or ""),
                      src,
                      item.findtext("pubDate") or "",
                      "경제",
                      (item.findtext("link") or "").strip())

conn.commit()
conn.close()
print(f"뉴스 수집 완료 (신규 {total}건)")
