"""사용자가 검색한 단어로 그 자리에서 뉴스를 받아온다.

왜 필요한가 — 지금까지는 Finnhub 에서 우리 7종목과 일반 경제만 미리 모아
두고 그 안에서 검색했다. 서랍에 없는 단어는 영영 0건이었다. '현대차' 를
검색하면 기사가 19건도 아니고 0건이었다. 구글에서 검색하면 나오는데.

Google 뉴스 RSS 는 검색어를 그대로 받고, 한국어 기사를 돌려주고, API 키도
필요 없다. 'when:1d' 로 오늘 기사만 받을 수도 있다.

한계도 분명하다 —
  · 본문 요약이 없다. description 이 제목을 그대로 반복한 것뿐이다.
    그래서 분석이 '제목을 근거로' 이뤄진다. 화면에도 그렇게 밝힌다.
  · 외부에 의존한다. 막히거나 느려지면 검색이 실패하므로, 부르는 쪽에서
    기존 DB 검색으로 넘어갈 수 있게 예외를 그대로 올린다.
  · 스포츠·연예가 섞인다. '기아' 를 검색하면 기아 타이거즈가 나온다.
    newsfilter.keep() 으로 거른다.
"""
import datetime
import email.utils
import html
import re
import sqlite3
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from newsfilter import keep

FEED = ("https://news.google.com/rss/search"
        "?q={q}&hl=ko&gl=KR&ceid=KR:ko")

# 회사명만 넣으면 경제와 무관한 기사가 잔뜩 온다. '카카오' 로는 관광·생활
# 기사가, '네이버' 로는 블로그 글이 올라왔다. 검색어에 경제 맥락을 OR 로
# 붙이면 건수는 절반쯤 줄지만 남는 게 전부 경제 기사다.
#   카카오: 52건 → 27건 (카카오게임즈 매출·주가 기사로 바뀜)
#   현대차: 47건 → 21건 (전부 경제)
ECON_HINT = "(주가 OR 실적 OR 매출 OR 투자 OR 시장 OR 경제)"
UA = {"User-Agent": "Mozilla/5.0 (compatible; econ-piece/1.0)"}


def _to_stamp(pubdate):
    """'Sun, 25 Oct 2026 00:37:00 GMT' -> '20261025T003700' (기존 형식에 맞춤)."""
    try:
        dt = email.utils.parsedate_to_datetime(pubdate)
        return dt.strftime("%Y%m%dT%H%M%S")
    except Exception:
        return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")


def _strip(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def fetch(keyword, days=1, timeout=15):
    """키워드로 기사 목록을 받아온다. [(title, source, stamp, url), ...]

    days 를 주면 'when:Nd' 를 붙여 최근 N일로 좁힌다. 날짜를 좁히면 수가
    줄지만 '오늘의 경제' 라는 목적에 맞고, 잡음도 함께 줄어든다.
    """
    q = f"{keyword} {ECON_HINT}"
    if days:
        q += f" when:{days}d"
    url = FEED.format(q=urllib.parse.quote(q))
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        root = ET.fromstring(r.read())

    out = []
    for it in root.findall(".//item"):
        title = _strip(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        out.append((title,
                    _strip(it.findtext("source")) or "Google 뉴스",
                    _to_stamp(it.findtext("pubDate")),
                    link))
    return out


def collect(conn, keyword, days=1):
    """받아온 기사를 news 에 저장하고 (받음, 거름, 새로 저장) 을 돌려준다.

    tickers 를 '검색' 으로 표시한다. 종목 태그가 아니라 검색으로 들어온
    기사라는 뜻이고, 매일 추천 후보에서 빼기 위한 구분이기도 하다.
    중복은 news 의 UNIQUE(title, published) 가 막는다.
    """
    rows = fetch(keyword, days=days)
    kept = [r for r in rows if keep(r[0], r[1])]

    cur = conn.cursor()
    before = cur.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    cur.executemany(
        "INSERT OR IGNORE INTO news "
        "(title, summary, source, published, sentiment, tickers, url, title_ko) "
        "VALUES (?, '', ?, ?, '', '검색', ?, ?)",
        [(t, s, p, u, t) for t, s, p, u in kept])
    conn.commit()
    after = cur.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    return len(rows), len(rows) - len(kept), after - before


def ensure_table(conn):
    """키워드를 하루에 한 번만 받아오기 위한 기록."""
    conn.execute("""CREATE TABLE IF NOT EXISTS rss_fetch (
        keyword TEXT, day TEXT, got INTEGER, dropped INTEGER, added INTEGER,
        created TEXT, PRIMARY KEY (keyword, day))""")
    conn.commit()


def fetched_today(conn, keyword, day):
    r = conn.execute("SELECT 1 FROM rss_fetch WHERE keyword=? AND day=?",
                     (keyword, day)).fetchone()
    return r is not None


def collect_once(conn, keyword, day, days=1):
    """하루에 한 번만 받아온다. 이미 받았으면 아무것도 안 하고 False.

    매 검색마다 외부를 부르면 느리고 상대 서버에도 무례하다. 같은 날
    같은 단어는 이미 DB 에 들어와 있으므로 다시 받을 이유가 없다.
    """
    ensure_table(conn)
    if fetched_today(conn, keyword, day):
        return False
    got, dropped, added = collect(conn, keyword, days=days)
    conn.execute(
        "INSERT OR REPLACE INTO rss_fetch "
        "(keyword, day, got, dropped, added, created) "
        "VALUES (?,?,?,?,?,datetime('now'))",
        (keyword, day, got, dropped, added))
    conn.commit()
    return True


if __name__ == "__main__":
    import sys
    kw = sys.argv[1] if len(sys.argv) > 1 else "현대차"
    c = sqlite3.connect("econ.db")
    got, dropped, added = collect(c, kw)
    print(f"'{kw}' — 받음 {got} · 경제무관 거름 {dropped} · 새로 저장 {added}")
    c.close()
