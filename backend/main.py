from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import json
import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect("econ.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/prices")
def list_prices():
    conn = get_db()
    rows = conn.execute("SELECT * FROM prices ORDER BY date DESC LIMIT 100").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/indicators")
def list_indicators():
    conn = get_db()
    rows = conn.execute("SELECT * FROM indicators ORDER BY date DESC LIMIT 50").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def pct_change(conn, ticker, start_date, days, window=7):
    """발표일(start_date) 직후 거래일 종가 → days 거래일 뒤 종가의 등락률(%).

    발표일이 주말·공휴일이면 다음 거래일이 기준일이 된다(정상).
    다만 기준일이 발표일에서 window 일 넘게 떨어져 있으면 그 발표는 주가
    데이터 범위 밖이라는 뜻이라 None 을 돌려준다. 이 가드가 없던 동안에는
    범위 밖 발표가 조용히 '보유한 첫 행'을 집어와, 서로 다른 발표 21건이
    모두 같은 하루(2024-09-16)로 뭉개져 통계가 틀렸다.
    """
    rows = conn.execute(
        "SELECT date, close FROM prices WHERE ticker=? AND date>=? ORDER BY date ASC LIMIT ?",
        (ticker, start_date, days + 1)
    ).fetchall()
    if len(rows) < days + 1:
        return None
    gap = (datetime.date.fromisoformat(rows[0]["date"])
           - datetime.date.fromisoformat(start_date)).days
    if gap > window:
        return None
    base = rows[0]["close"]
    after = rows[days]["close"]
    if not base or after is None:   # 미완성 봉 등으로 close 가 비어 있는 행 방어
        return None
    return round((after - base) / base * 100, 2)

@app.get("/api/analysis")
def analysis():
    conn = get_db()
    indicators = conn.execute("SELECT DISTINCT name FROM indicators").fetchall()
    tickers = [r["ticker"] for r in conn.execute("SELECT DISTINCT ticker FROM prices").fetchall()]
    result = []
    for ind in indicators:
        name = ind["name"]
        # 기준월(date)이 아니라 FRED 실제 발표일(release_date)로 반응을 측정한다.
        # 예: 2026-09 CPI 는 2026-10-14 발표 → 10/14 기준으로 봐야 '발표 반응'이다.
        releases = conn.execute(
            "SELECT COALESCE(release_date, date) d FROM indicators "
            "WHERE name=? AND release_date IS NOT NULL AND release_date<>'' ORDER BY d ASC",
            (name,)).fetchall()
        dates = [r["d"] for r in releases]
        per_ticker = []
        for ticker in tickers:
            for days in (1, 5):
                changes = [pct_change(conn, ticker, d, days) for d in dates]
                changes = [c for c in changes if c is not None]
                if not changes:
                    continue
                avg = round(sum(changes) / len(changes), 2)
                up = sum(1 for c in changes if c > 0)
                per_ticker.append({
                    "ticker": ticker,
                    "days": days,
                    "avg_pct": avg,
                    "up": up,
                    "total": len(changes),
                    "latest_pct": changes[-1],
                })
        result.append({
            "indicator": name,
            "release_count": len(dates),            # 발표일을 아는 건수
            "window": [dates[0], dates[-1]] if dates else None,
            "reactions": per_ticker,                # 각 항목의 total = 실제 집계된 발표 수
        })
    conn.close()
    return result

@app.get("/api/news")
def list_news():
    conn = get_db()
    rows = conn.execute("SELECT title, summary, source, published, sentiment, tickers, url FROM news ORDER BY published DESC LIMIT 30").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/daily")
def list_daily():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, url, title, source, sentiment, tickers, brief, summary_easy, glossary, pick_reason "
            "FROM daily ORDER BY date DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["glossary"] = json.loads(d["glossary"]) if d["glossary"] else []
        except (ValueError, TypeError):
            d["glossary"] = []
        out.append(d)
    return out

@app.get("/api/company/{ticker}")
def company(ticker: str):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT ticker, date, close, change_pct, volume, news_json, ai_summary "
            "FROM company_daily WHERE ticker=? ORDER BY date DESC",
            (ticker.upper(),)
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        raw = d.pop("news_json", None)
        try:
            d["news"] = json.loads(raw) if raw else []
        except (ValueError, TypeError):
            d["news"] = []
        out.append(d)
    return out


@app.get("/api/fx")
def fx(days: int = 15):
    """환율 — 날짜별 기록(값·증감·AI 분석, 최신순) + 최근 추이(그래프용)."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, usdkrw, usdkrw_chg, eurkrw, eurkrw_chg, ai_summary "
            "FROM fx_daily ORDER BY date DESC LIMIT ?", (days,)).fetchall()
        series = {}
        for pair in ("USDKRW", "EURKRW"):
            srows = conn.execute(
                "SELECT date, rate FROM fx WHERE pair=? ORDER BY date DESC LIMIT ?",
                (pair, days)).fetchall()
            series[pair] = [dict(r) for r in srows]
    except sqlite3.OperationalError:
        conn.close()
        return {"days": [], "series": {}}
    conn.close()
    return {"days": [dict(r) for r in rows], "series": series}
