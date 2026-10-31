from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import json
import re
import threading
import time
import datetime

from search_terms import POPULAR, expand

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

# 한국어에는 띄어쓰기 경계가 없어서 부분 일치로 두면 엉뚱한 데 걸린다.
# 실제로 '인텔' 이 번역 제목의 "슈퍼 인텔리전스" 에 걸렸다. '비자'⊂'비자금',
# '포드'⊂'옥스포드' 도 같은 함정이다.
#
# 대신 조사는 허용해야 한다 — "인텔은", "인텔이", "삼성의" 는 걸려야 하니까.
# 그래서 "검색어 뒤에 조사가 붙거나, 한글이 아닌 것이 오면 일치" 로 본다.
_PARTICLES = ("으로서", "으로써", "이라고", "에게서", "으로", "에서", "에게", "부터",
              "까지", "보다", "처럼", "라고", "한테", "께서", "이나", "밖에",
              "조차", "마저", "이란", "이는", "은", "는", "이", "가", "을", "를",
              "의", "에", "와", "과", "도", "만", "로", "나", "든", "뿐", "들")
_HANGUL = re.compile(r"[가-힣]")


def _ko_contains(term, text):
    """한국어 검색어가 text 안에 '낱말로' 들어 있는지.

    앞뒤가 한글로 이어지면 더 긴 낱말의 일부이므로 일치로 보지 않는다.
    단, 뒤에 붙은 것이 조사면 일치로 본다.
    """
    start = 0
    while True:
        i = text.find(term, start)
        if i < 0:
            return False
        start = i + 1

        if i > 0 and _HANGUL.match(text[i - 1]):
            continue                      # 앞이 한글 — 더 긴 낱말의 일부

        rest = text[i + len(term):]
        if not rest or not _HANGUL.match(rest[0]):
            return True                   # 뒤가 끝이거나 한글이 아님
        for part in _PARTICLES:           # 긴 조사부터 본다
            if rest.startswith(part):
                after = rest[len(part):]
                if not after or not _HANGUL.match(after[0]):
                    return True
    return False


def _first_match(terms, text):
    """terms 중 text 안에 실제로 있는 첫 표현을 돌려준다(없으면 None).

    영어 표현은 단어 경계를 요구한다 — 안 그러면 'rates' 가 'corporates' 에,
    'rate' 가 'accurate' 에 걸려서 엉뚱한 기사가 검색 결과에 섞인다.
    한국어는 조사까지 감안한 _ko_contains 로 본다.
    """
    if not text:
        return None
    low = text.lower()
    for t in terms:
        if re.search(r"[A-Za-z0-9]", t):
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(t.lower())
                         + r"(?![A-Za-z0-9])", low):
                return t
        elif _ko_contains(t.lower(), low):
            return t
    return None


@app.get("/api/news/search")
def search_news(q: str = "", limit: int = 30):
    """제목·요약·한국어 제목에서 검색어를 찾는다.

    수집한 기사가 전부 영어라, 한국어로 검색하면 그대로는 한 건도 안 걸린다.
    그래서 두 가지를 같이 쓴다 —
      1) search_terms 사전으로 한국어 검색어를 영어 표현들로 넓히고,
      2) 번역이 채워진 기사는 title_ko 에서 한국어 그대로 찾는다.
    무엇으로 찾았는지(expanded)를 함께 돌려줘서, 화면이
    "'금리' → interest rate 로 찾았습니다" 처럼 보여줄 수 있게 한다.
    """
    terms = expand(q)
    if not terms:
        return {"query": q, "expanded": [], "count": 0, "items": [],
                "suggest": POPULAR}

    # 미리 모아둔 기사만 뒤지면 서랍에 없는 단어는 영영 0건이다. '현대차' 가
    # 그랬다. 그래서 처음 보는 단어는 그 자리에서 Google 뉴스에 물어본다.
    # 같은 날 같은 단어는 이미 DB 에 들어와 있으므로 하루 한 번만 받는다.
    #
    # 실패해도 검색은 계속된다 — 받아오던 게 막히면 기존 DB 검색으로 넘어간다.
    # 외부에 기대는 기능이라 이 이중화가 없으면 구글이 막히는 순간 검색이 통째로
    # 죽는다. collect_news.py 가 Finnhub↔RSS 로 하는 것과 같은 방식이다.
    live = False
    try:
        import rss_search
        c0 = get_db()
        live = rss_search.collect_once(c0, q, _latest_day(c0))
        c0.close()
    except Exception as e:
        print(f"검색 중 기사 수집 실패({e.__class__.__name__}) — 기존 DB 로 진행")

    limit = max(1, min(limit, 100))
    conds, params = [], []
    for t in terms:
        # LIKE 와일드카드가 검색어에 들어 있어도 글자 그대로 찾게 이스케이프
        esc = t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pat = "%" + esc + "%"
        conds.append(
            "(title LIKE ? ESCAPE '\\' "
            "OR IFNULL(title_ko,'') LIKE ? ESCAPE '\\' "
            "OR IFNULL(summary,'') LIKE ? ESCAPE '\\')")
        params += [pat, pat, pat]

    conn = get_db()
    # LIKE 는 단어 안쪽에도 걸린다("rates" 가 "corporates" 에). 그래서 SQL 은
    # 후보를 넉넉히 추리는 데만 쓰고, 실제 판정은 아래 단어 경계 검사로 한다.
    rows = conn.execute(
        "SELECT title, title_ko, summary, source, published, tickers, url FROM news "
        "WHERE " + " OR ".join(conds) + " ORDER BY published DESC LIMIT ?",
        params + [min(limit * 10, 300)]
    ).fetchall()
    conn.close()

    out = []
    for r in rows:
        d = dict(r)
        title_hay = (d["title"] or "") + " " + (d["title_ko"] or "")
        hit = _first_match(terms, title_hay)
        where = "제목"
        if not hit:
            hit = _first_match(terms, d["summary"] or "")
            where = "요약"
        if not hit:
            continue          # LIKE 로만 걸린 단어 안쪽 오탐 — 버린다
        d["matched"] = hit
        d["matched_in"] = where
        d["_score"] = 2 if where == "제목" else 1
        out.append(d)

    # 제목에서 걸린 기사를 먼저, 그 안에서 최신순
    out.sort(key=lambda d: (d["_score"], d["published"] or ""), reverse=True)
    out = out[:limit]
    for d in out:
        d.pop("_score", None)
    res = {"query": q, "expanded": terms, "count": len(out), "items": out,
           "live": live}
    if not out:
        # 기사가 없는 단어도 있다. 수집이 미국 기사 중심이라 '현대차'·'기아'
        # 같은 건 0건이다. 빈 화면만 주지 말고 눌러볼 것을 같이 준다.
        res["suggest"] = POPULAR
    return res



# 분석을 HTTP 요청 안에서 끝내지 않는 이유 —
# 분석 한 건이 66~112초 걸리는데 nginx 의 proxy_read_timeout 기본값이 60초다.
# 실제로 '유가' 를 분석시켰더니 60초에 연결이 끊겨 화면에서 아무 일도 일어나지
# 않았다. 타임아웃만 늘려도 브라우저와 Tailscale Funnel 에 각자 타임아웃이
# 있으므로, 긴 작업을 연결에 매달아 두는 구조 자체를 바꾼다.
#
# 요청은 작업만 띄우고 바로 돌아오고, 화면이 몇 초마다 상태를 물어본다.
_JOBS = {}                      # keyword -> {"started": float, "error": str|None}
_JOBS_LOCK = threading.Lock()
# CPU 한 대로 모델을 돌리므로 동시에 두 건을 돌리면 둘 다 느려진다. 한 번에 하나.
_ANALYZE_LOCK = threading.Lock()


def _job_state(q):
    with _JOBS_LOCK:
        j = _JOBS.get(q)
        return dict(j) if j else None


def _run_analysis(q, day0, cands, range_label, redo):
    """백그라운드에서 고르기 → 분석 → 저장까지. 실패해도 상태에 남긴다."""
    import analyze
    started = time.time()
    try:
        with _ANALYZE_LOCK:
            conn = get_db()
            _ensure_tables(conn)
            try:
                idx = analyze.pick(cands, topic=q)
            except Exception:
                idx = 0
            art = cands[idx]

            row = None if redo else conn.execute(
                "SELECT 1 FROM article_analysis WHERE url=?", (art["url"],)).fetchone()
            if row is None:
                res = analyze.full(art["title"], art["summary"], art["tickers"])
                if not res["summary_easy"]:
                    raise RuntimeError("설명 생성 실패")
                _save_analysis(conn, art, res)
                # 어느 쪽으로 분석했는지 로그에 남긴다. 백엔드를 재시작하지
                # 않으면 옛 llm.py 가 메모리에 남아 외부 API 설정이 반영되지
                # 않는데, 겉으로는 느려진 것 말고 차이가 안 보인다.
                import llm
                took = time.time() - started
                print(f"  분석 완료 '{q}' — {llm.last_provider} · {took:.0f}초",
                      flush=True)

            conn.execute(
                "INSERT OR REPLACE INTO search_keyword "
                "(keyword, day, url, range_label, candidates, created) "
                "VALUES (?,?,?,?,?,datetime('now'))",
                (q, day0, art["url"], range_label, len(cands)))
            conn.commit()
            conn.close()
        with _JOBS_LOCK:
            _JOBS.pop(q, None)
    except Exception as e:
        with _JOBS_LOCK:
            _JOBS[q] = {"started": _JOBS.get(q, {}).get("started", time.time()),
                        "error": f"{e.__class__.__name__}: {e}"[:200]}


# 날짜 사다리 — 오늘 기사가 적으면 범위를 넓히되, 넓혔다는 걸 화면에 밝힌다.
# 오늘 수집량은 평균 150건이지만 키워드로 좁히면 편차가 크다. 실측으로
# 인공지능 30건 / 테슬라 19건인데 금리·환율·고용은 2건뿐이다. 2건 중에
# 고르는 건 고르는 게 아니므로, 8건이 될 때까지 단계적으로 넓힌다.
# 마지막 칸은 prune_news.py 의 KEEP_DAYS 와 짝이다. 그보다 오래된 기사는
# 지워지므로 "전체 기간" 이라고 쓰면 화면이 거짓말을 한다. 둘을 함께 고칠 것.
LADDER = [("오늘", 0), ("최근 3일", 2), ("최근 7일", 6), ("최근 한 달", 29)]
MIN_CANDIDATES = 8


def _latest_day(conn=None):
    """오늘 날짜(KST, YYYYMMDD). 캐시 키이자 날짜 사다리의 기준일.

    처음에는 'news 에 들어온 가장 최근 날짜' 를 썼다. Finnhub 기사가 UTC 라
    한국 날짜보다 하루 늦게 들어오는 걸 감안한 것이었는데, 검색으로 오늘
    기사를 받아오기 시작하면서 문제가 됐다 — 기사가 하나 들어오는 순간
    기준일이 하루 넘어가고, 그날 미리 계산해 둔 키워드 7개가 **한꺼번에**
    무효가 됐다. 화면에서는 "눌러도 아무 반응이 없는" 것으로 보였다.

    달력 날짜는 하루에 한 번만 바뀌므로 캐시가 흔들리지 않는다. Finnhub 의
    하루 지연은 날짜 사다리(오늘→3일→7일)가 알아서 흡수한다.
    """
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=9)).strftime("%Y%m%d")


def _kst_ymd(published):
    """UTC 로 저장된 published 를 KST 달력 날짜(YYYYMMDD)로 바꾼다.

    news.published 는 UTC 다. 기준일(_latest_day)은 KST 달력 날짜다.
    그대로 앞 8자를 비교하면 **KST 00~09시에 나온 기사가 전부 "오늘"에서
    빠진다**. 실제로 '금리' 검색에서 오늘 기사가 UTC 기준 0건, KST 환산
    16건으로 갈렸고, 사다리가 "최근 3일" 로 내려간 뒤 거기서 고른 기사가
    정작 오늘 기사였다. 화면에는 "오늘 기사가 적어 최근 3일에서 골랐습니다"
    라고 떴다.
    """
    s = str(published or "")
    if len(s) < 8:
        return ""
    try:
        t = datetime.datetime(int(s[:4]), int(s[4:6]), int(s[6:8]),
                              int(s[9:11] or 0), int(s[11:13] or 0),
                              tzinfo=datetime.timezone.utc)
    except ValueError:
        return s[:8]
    return (t + datetime.timedelta(hours=9)).strftime("%Y%m%d")


def _candidates(items, day0):
    """사다리를 올라가며 후보가 MIN_CANDIDATES 이상 되는 첫 범위를 고른다."""
    if not day0:
        return items, "전체 기간"
    base = datetime.date(int(day0[:4]), int(day0[4:6]), int(day0[6:8]))
    for label, back in LADDER:
        if back is None:
            return items, label
        since = (base - datetime.timedelta(days=back)).strftime("%Y%m%d")
        sub = [i for i in items if _kst_ymd(i["published"]) >= since]
        if len(sub) >= MIN_CANDIDATES:
            return sub, label
    return items, "전체 기간"


def _ensure_tables(conn):
    """분석은 기사(url) 단위로 저장한다.

    키워드 단위로 저장했더니 '테슬라' 와 '실적' 이 같은 기사를 골랐을 때
    60초짜리 분석을 두 번 돌렸다. 기사 단위로 두면 어느 입구로 들어오든
    한 번만 분석하고, 매일 추천·검색·지난 기록이 같은 결과를 가리킨다.
    """
    conn.execute("""CREATE TABLE IF NOT EXISTS article_analysis (
        url TEXT PRIMARY KEY,
        title TEXT, title_ko TEXT, source TEXT, published TEXT,
        pick_reason TEXT, brief TEXT, summary_easy TEXT,
        glossary TEXT, impacts TEXT,
        sentiment TEXT, sentiment_reason TEXT, created TEXT)""")
    # 본문 없이 제목만으로 분석했는지. 검색으로 들어온 기사(Google 뉴스 RSS)는
    # 제목 한 줄이 전부라, 같은 화면에 섞여 있으면 사용자가 구분할 수 없다.
    # 어디까지 믿어도 되는지는 사용자가 판단할 몫이니 숨기지 않고 표시한다.
    try:
        conn.execute("ALTER TABLE article_analysis ADD COLUMN title_only INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass            # 이미 있음
    # 키워드 -> 그날 고른 기사. 날(day)이 바뀌면 다시 고른다.
    conn.execute("""CREATE TABLE IF NOT EXISTS search_keyword (
        keyword TEXT, day TEXT, url TEXT,
        range_label TEXT, candidates INTEGER, created TEXT,
        PRIMARY KEY (keyword, day))""")
    conn.commit()


def _analysis_row(row):
    d = dict(row)
    for k in ("glossary", "impacts"):
        try:
            d[k] = json.loads(d[k]) if d[k] else []
        except (ValueError, TypeError):
            d[k] = []
    return d


def _save_analysis(conn, art, res):
    import analyze

    conn.execute(
        "INSERT OR REPLACE INTO article_analysis "
        "(url, title, title_ko, source, published, pick_reason, brief, "
        " summary_easy, glossary, impacts, sentiment, sentiment_reason, "
        " title_only, created) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
        (art["url"], art["title"], art.get("title_ko"), art["source"],
         art["published"], res["pick_reason"], res["brief"], res["summary_easy"],
         json.dumps(res["glossary"], ensure_ascii=False),
         json.dumps(res["impacts"], ensure_ascii=False),
         res["sentiment"], res["sentiment_reason"],
         0 if analyze._has_body(art["title"], art.get("summary")) else 1))
    conn.commit()


@app.get("/api/news/pick")
def pick_article(q: str = "", force: bool = False, redo: bool = False):
    """검색어에 맞는 기사 1건을 AI 가 골라 분석해서 돌려준다.

    분석 한 건에 1분쯤 걸린다 — 고르기 11초, 설명 32초, 기업별 영향 20초.
    로컬 모델을 CPU 로 돌리는 값이라 줄일 수 없다. 그래서 결과를 저장해 두고,
    자주 쓰는 단어는 아침 파이프라인에서 미리 채운다.

    status:
      ready   — 분석이 있다
      none    — 그 단어로 찾은 기사가 없다
      pending — 아직 분석 안 했다. force=true 로 다시 부르면 분석한다(1분)

    force 는 "없으면 지금 분석해라", redo 는 "있어도 다시 분석해라".
    프롬프트를 고쳤을 때 옛 분석이 그대로 남아 있으면 안 되므로 나눠 둔다.
    """
    if redo:
        force = True
    q = (q or "").strip()
    if not q:
        return {"status": "none", "query": q}

    conn = get_db()
    _ensure_tables(conn)
    day0 = _latest_day(conn)

    # 진행 중인 작업을 캐시보다 **먼저** 본다.
    # 순서를 반대로 했더니 재분석이 도는 중에 폴링이 옛 분석을 집어
    # "완료" 로 돌려줬다. 화면은 바뀐 줄 알지만 내용은 옛것이었다.
    # 이미 돌고 있으면 진행 상태를 돌려준다 (화면이 몇 초마다 물어본다)
    job = _job_state(q)
    if job:
        conn.close()
        if job.get("error"):
            with _JOBS_LOCK:
                _JOBS.pop(q, None)
            return {"status": "error", "query": q, "message": job["error"]}
        return {"status": "working", "query": q,
                "elapsed": int(time.time() - job["started"])}

    # 이미 오늘 이 단어로 고른 기사가 있으면 그 분석을 그대로
    hit = conn.execute(
        "SELECT k.url, k.range_label, k.candidates FROM search_keyword k "
        "WHERE k.keyword=? AND k.day=?", (q, day0)).fetchone()
    if hit and not force:
        row = conn.execute("SELECT * FROM article_analysis WHERE url=?",
                           (hit["url"],)).fetchone()
        if row:
            conn.close()
            return {"status": "ready", "query": q, "cached": True,
                    "range": hit["range_label"], "candidates": hit["candidates"],
                    **_analysis_row(row)}

    found = search_news(q=q, limit=100)
    if not found["items"]:
        conn.close()
        return {"status": "none", "query": q, "expanded": found["expanded"]}

    cands, range_label = _candidates(found["items"], day0)

    if not force:
        conn.close()
        return {"status": "pending", "query": q,
                "range": range_label, "candidates": len(cands),
                "expanded": found["expanded"]}

    # 분석은 백그라운드로 던지고 바로 돌아온다. 화면이 몇 초마다 다시 물어본다.
    rows = [{"title": i["title"], "title_ko": i["title_ko"],
             "tickers": i["tickers"] or "", "summary": i["summary"],
             "url": i["url"], "source": i["source"],
             "published": i["published"]} for i in cands]
    conn.close()

    with _JOBS_LOCK:
        _JOBS[q] = {"started": time.time(), "error": None}
    threading.Thread(target=_run_analysis,
                     args=(q, day0, rows, range_label, redo),
                     daemon=True).start()
    return {"status": "working", "query": q, "elapsed": 0,
            "range": range_label, "candidates": len(cands)}


@app.get("/api/daily")
def list_daily():
    """매일 고른 기사 목록.

    daily 는 "어느 날 어느 기사를 골랐나"만 들고 있고, 내용은
    article_analysis 에서 가져온다. 검색으로 만든 분석과 같은 테이블이라
    오늘 기사와 검색 기사가 항상 같은 모양이 된다.

    COALESCE 로 받치는 이유 — 아직 article_analysis 로 안 옮겨진 행이
    있어도 옛 daily 컬럼으로 화면이 비지 않게.
    """
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT d.date, d.url, d.tickers,
                   COALESCE(a.title, d.title)               AS title,
                   a.title_ko,
                   COALESCE(a.source, d.source)             AS source,
                   COALESCE(a.sentiment, d.sentiment)       AS sentiment,
                   a.sentiment_reason,
                   COALESCE(a.brief, d.brief)               AS brief,
                   COALESCE(a.summary_easy, d.summary_easy) AS summary_easy,
                   COALESCE(a.glossary, d.glossary)         AS glossary,
                   COALESCE(a.pick_reason, d.pick_reason)   AS pick_reason,
                   a.impacts,
                   COALESCE(a.title_only, 0)                AS title_only
            FROM daily d
            LEFT JOIN article_analysis a ON a.url = d.url
            ORDER BY d.date DESC""").fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("glossary", "impacts"):
            try:
                d[k] = json.loads(d[k]) if d[k] else []
            except (ValueError, TypeError):
                d[k] = []
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
    """환율 — 날짜별 기록(값·증감·AI 분석, 최신순) + 최근 추이(그래프용).

    값과 증감은 fx_daily 에 저장된 것을 쓰지 않고 fx 에서 조회 시점에 계산한다.

    환율은 24시간 거래라 수집 시각(15:40)에는 그날 종가가 아직 확정되지 않는다.
    fx 는 매일 6개월치를 다시 받아 INSERT OR REPLACE 하므로 스스로 정정되지만,
    fx_daily 는 한 번 쓰면 다시 보지 않는다. 그래서 두 곳에 같은 숫자를 두면
    같은 날짜에 서로 다른 값이 생긴다(2026-10-31 확인: 32일 중 13일 어긋남).
    숫자는 fx 한 곳에만 둔다.
    """
    conn = get_db()
    try:
        drows = conn.execute(
            "SELECT date, ai_summary FROM fx_daily ORDER BY date DESC LIMIT ?",
            (days,)).fetchall()
        # 증감에는 '직전 거래일'이 필요해서 days 로 자르지 않고 전부 받아 둔다(쌍당 150행 수준)
        rates = {}
        for pair in ("USDKRW", "EURKRW"):
            rates[pair] = [(r["date"], r["rate"]) for r in conn.execute(
                "SELECT date, rate FROM fx WHERE pair=? ORDER BY date DESC", (pair,)).fetchall()]
        # 현재 시세. 타이머를 아직 안 깔았으면 테이블이 없을 수 있다 — 없으면 빈 채로 간다.
        try:
            lrows = conn.execute("SELECT * FROM fx_live").fetchall()
        except sqlite3.OperationalError:
            lrows = []
        # 장 중 5분봉 — '오늘 얼마나 올랐다 내렸나'. 가장 최근 날짜 하루치만 보낸다.
        # period=1d 로 받은 봉이 자정을 넘어 이틀에 걸쳐 있으므로 날짜로 잘라야 한다.
        # 휴장이면 '마지막 장이 열린 날'이 나온다 — 그게 맞는 화면이다.
        intr = {}
        try:
            for pair in ("USDKRW", "EURKRW"):
                day = conn.execute(
                    "SELECT max(substr(ts,1,10)) FROM fx_intraday WHERE pair=?",
                    (pair,)).fetchone()[0]
                if not day:
                    continue
                intr[pair] = (day, conn.execute(
                    "SELECT ts, rate FROM fx_intraday WHERE pair=? AND ts LIKE ? ORDER BY ts",
                    (pair, day + "%")).fetchall())
        except sqlite3.OperationalError:
            intr = {}
    except sqlite3.OperationalError:
        conn.close()
        return {"days": [], "series": {}, "live": {}, "intraday": {}}
    conn.close()

    def at(pair, d):
        """d일(없으면 그 이전 가장 가까운 거래일) 종가와 직전 거래일 대비 증감"""
        seq = [x for x in rates[pair] if x[0] <= d]
        if not seq:
            return None, None
        if len(seq) < 2:
            return seq[0][1], None
        return seq[0][1], seq[0][1] - seq[1][1]

    out = []
    for r in drows:
        usd, usd_chg = at("USDKRW", r["date"])
        eur, eur_chg = at("EURKRW", r["date"])
        out.append({"date": r["date"], "ai_summary": r["ai_summary"],
                    "usdkrw": usd, "usdkrw_chg": usd_chg,
                    "eurkrw": eur, "eurkrw_chg": eur_chg})

    series = {p: [{"date": d, "rate": v} for d, v in rows[:days]] for p, rows in rates.items()}

    # 현재 시세 — 값만 주지 않고 '언제 기준인지'를 함께 준다.
    # yfinance 는 야후 지연 시세라 진짜 실시간이 아니고, 쌍마다 신선도가 다르다
    # (2026-10-31 실측: 같은 순간에 받아도 달러 32분 전 / 유로 396분 전).
    # stale_min 없이 값만 띄우면 6시간 묵은 값을 '현재'라고 보여주게 된다.
    now = datetime.datetime.now()
    live = {}
    for r in lrows:
        prev = r["prev_close"]
        chg = (r["rate"] - prev) if (r["rate"] is not None and prev) else None
        stale = None
        if r["market_time"]:
            try:
                mt = datetime.datetime.fromisoformat(r["market_time"])
                stale = int((now - mt).total_seconds() // 60)
            except ValueError:
                pass
        live[r["pair"]] = {
            "rate": r["rate"], "chg": chg,
            "pct": (chg / prev * 100) if (chg is not None and prev) else None,
            "bid": r["bid"], "ask": r["ask"],
            "market_time": r["market_time"], "market_state": r["market_state"],
            "fetched_at": r["fetched_at"], "stale_min": stale,
        }

    # 장 중 움직임 — 그래프용 점들과, 그래프 축에 쓸 기준값들.
    # 시작가·고가·저가를 함께 주는 이유: 선만 그리면 자동 스케일 때문에
    # 0.2% 움직임도 산맥처럼 보인다. 숫자가 같이 있어야 폭을 읽을 수 있다.
    intraday = {}
    for pair, (day, bars) in intr.items():
        pts = [{"t": b["ts"][11:16], "rate": b["rate"]} for b in bars]
        if len(pts) < 2:
            continue
        vals = [x["rate"] for x in pts]
        first, last = vals[0], vals[-1]
        intraday[pair] = {
            "day": day, "points": pts,
            "open": first, "last": last, "high": max(vals), "low": min(vals),
            "chg": last - first,
            "pct": ((last - first) / first * 100) if first else None,
            "span": max(vals) - min(vals),
        }

    return {"days": out, "series": series, "live": live, "intraday": intraday}
