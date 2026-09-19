from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import json

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

def pct_change(conn, ticker, start_date, days):
    rows = conn.execute(
        "SELECT date, close FROM prices WHERE ticker=? AND date>=? ORDER BY date ASC LIMIT ?",
        (ticker, start_date, days + 1)
    ).fetchall()
    if len(rows) < days + 1:
        return None
    base = rows[0]["close"]
    after = rows[days]["close"]
    if base == 0:
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
        releases = conn.execute("SELECT date FROM indicators WHERE name=? ORDER BY date ASC", (name,)).fetchall()
        dates = [r["date"] for r in releases]
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
        result.append({"indicator": name, "release_count": len(dates), "reactions": per_ticker})
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
            "SELECT date, url, title, source, sentiment, tickers, summary_easy, glossary, pick_reason "
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
