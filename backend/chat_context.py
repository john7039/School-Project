"""질문에서 '답하는 데 필요한 것' 만 골라 온다. 채팅의 핵심이 여기다.

왜 이게 핵심인가 —
  LLM 은 우리 DB 를 모른다. 아무것도 안 주면 지어낸다. 전부 주면 느리고(실측:
  2,200토큰이면 맥북 M1 Max 에서 9.7초, 서버 VM 에서 65초) 모델이 헷갈린다.
  **질문에 맞는 것만 300~800토큰으로 주면 1~2초에 제대로 답한다.**
  모델을 바꾸는 것보다 여기를 손보는 쪽이 훨씬 크게 바뀐다.

⚠️ 숫자는 LLM 에게 계산시키지 않는다.
  "3.88 - 3.04 는?" 을 시키면 틀리고, 틀려도 아무도 모른다. 금리차·상승률·
  범위는 전부 코드가 계산해서 **완성된 문장 조각**으로 넘긴다. LLM 이 하는 일은
  그 조각들을 읽기 좋게 엮는 것뿐이다.
  (경제지표 탭에서 '업종 판단은 AI 가 아니라 계산' 으로 간 것과 같은 판단이다.)

⚠️ 지표 단위는 `indicators.build()` 를 그대로 쓴다. 다시 구현하지 않는다.
  지수는 비율(%), 금리·실업률은 차이(%p) 다. 이걸 한 번 더 짜면 한 번 더 틀린다.

⚠️ 아무것도 안 걸리면 LLM 을 아예 부르지 않는다.
  "파이썬 알려줘" 같은 질문에 호출을 쓰면 공개 사이트에서 공짜 챗봇이 된다.
  `matched=False` 를 돌려주고 호출부가 안내문으로 끝낸다. 속도 제한의 1차 방어선.
"""

import datetime
import re

import tickers

# ── 사전 ──
# 지표는 (country, name) 으로 찾는다. indicators.SPEC 과 같은 키다.
_IND = {
    "CPI": ["물가", "인플레", "인플레이션", "cpi", "소비자물가", "장바구니", "물가상승"],
    "금리": ["금리", "기준금리", "콜금리", "이자율", "연준", "fomc", "한국은행", "금리차"],
    "실업률": ["실업", "일자리", "고용", "취업난", "실업률"],
    "수출": ["수출"],
    "수입": ["수입", "원자재", "원유"],
}
_FX = ["환율", "달러", "원화", "유로", "원달러", "원/달러", "원유로", "엔화", "환전"]
_ART = ["기사", "뉴스", "오늘", "소식", "이슈", "추천"]

# 나라를 가리키는 말. 없으면 둘 다 넣는다.
_KR = ["한국", "우리나라", "국내", "원화", "한은", "한국은행", "코스피", "코스닥"]
_US = ["미국", "연준", "fed", "fomc", "달러", "나스닥", "뉴욕"]

# ⚠️ 2글자 미만 별칭은 안 쓴다. 문장 안에서 아무 데나 걸린다
#    ('에' 가 '에코프로' 에, 'A' 가 'AI' 에).
_MIN_ALIAS = 2

# 토큰 어림수 — 2026-11-07 실측에서 4,426바이트가 2,219토큰이었다(qwen2.5).
# 바이트를 2로 나누면 대충 맞는다. 정확할 필요는 없고 예산만 지키면 된다.
_BYTES_PER_TOKEN = 2


def _tokens(text):
    return len(text.encode("utf-8")) // _BYTES_PER_TOKEN


def _norm(q):
    return (q or "").lower().replace(" ", "")


def _has(q, words):
    """⚠️ 한국어는 조사가 붙는다('금리가', '환율은'). 단어 경계를 요구하면
    다 놓치므로 부분 문자열로 본다. 영문 별칭만 경계를 본다."""
    n = _norm(q)
    for w in words:
        w = w.lower()
        if w.isascii():
            if re.search(r"\b%s\b" % re.escape(w), n):
                return True
        elif w in n:
            return True
    return False


def _countries(q):
    kr, us = _has(q, _KR), _has(q, _US)
    if kr and not us:
        return ["KR"]
    if us and not kr:
        return ["US"]
    return ["US", "KR"]          # 안 밝혔으면 둘 다 (금리차 질문이 여기 걸린다)


def _stocks(q):
    """문장 안에서 아는 종목 이름을 훑는다.

    tickers.resolve() 는 검색창용이라 '질문 전체 = 종목명' 을 가정한다.
    채팅은 문장이라 별칭을 하나씩 훑어야 한다."""
    n = _norm(q)
    found = []
    for alias, tk in tickers.ALIASES.items():
        if len(alias) < _MIN_ALIAS:
            continue
        hit = (re.search(r"\b%s\b" % re.escape(alias), n)
               if alias.isascii() else alias in n)
        if hit and tk not in found:
            found.append(tk)
    return found[:3]             # 한 질문에 세 종목이면 충분하다


# ── 조각 만들기 ──
# 각 함수는 (라벨, 본문) 을 돌려준다. 본문은 **이미 완성된 문장**이어야 한다 —
# LLM 이 계산하거나 해석할 거리를 남기지 않는다.

def _p_indicator(d):
    """indicators.build() 한 항목 → 조각."""
    L = ["%s %s · %s 기준%s" % (
        "미국" if d["country"] == "US" else "한국", d["label"], d["month"],
        # released 는 이미 '11/2 발표' 꼴이다. '발표' 를 또 붙이면 두 번 나온다.
        " · %s" % d["released"] if d.get("released") else "")]
    h = d["headline"]
    # headline 은 {value, unit, decimals} 다. 화면(IndCard)과 같은 규칙으로 쓴다 —
    # 지수는 상승률이라 부호를 붙이고, 금리·실업률은 값 자체라 안 붙인다.
    head = "%s%.*f%s" % ("+" if d["unit"] == "index" and h["value"] > 0 else "",
                         h["decimals"], h["value"], h["unit"])
    L.append("  지금 %s%s" % (head, " (작년 같은 달 대비)" if d["unit"] == "index" else ""))
    b = d.get("band")
    if b:
        lvl = {"low": "낮은 쪽", "mid": "중간", "high": "높은 쪽"}[b["level"]]
        L.append("  최근 %s년 범위 %s~%s 중 %s" % (b["years"], b["lo"], b["hi"], lvl))
    if d.get("note"):
        L.append("  " + d["note"])
    pts = (d.get("chart") or {}).get("points") or []
    if len(pts) >= 2:
        tail = pts[-6:]
        L.append("  최근 추이 " + " ".join("%s %s" % (p["t"], p["rate"]) for p in tail))
    if d.get("brief"):
        L.append("  (%s)" % d["brief"])
    return "%s %s" % (d["country"], d["label"]), "\n".join(L)


def _p_rategap(items):
    """한·미 금리차. ⚠️ 여기서 코드가 빼준다 — LLM 에게 시키면 틀린다."""
    us = next((x for x in items if x["country"] == "US" and x["name"] == "금리"), None)
    kr = next((x for x in items if x["country"] == "KR" and x["name"] == "금리"), None)
    if not (us and kr):
        return None
    ku = {p["t"]: p["rate"] for p in kr["chart"]["points"]}
    pts = [(p["t"], p["rate"], ku[p["t"]]) for p in us["chart"]["points"] if p["t"] in ku]
    if len(pts) < 2:
        return None
    t, u, k = pts[-1]
    gaps = [(a, b - c) for a, b, c in pts]
    wt, wg = max(gaps, key=lambda g: g[1])
    inv = sum(1 for _, g in gaps if g > 0)
    return "한·미 금리차", (
        "한·미 금리차 · %s 기준\n"
        "  미국 %.2f%% − 한국 %.2f%% = %+.2f%%p (미국이 %s)\n"
        "  겹치는 %d개월 중 미국이 높았던 달 %d개\n"
        "  가장 벌어졌을 때 %s 의 %+.2f%%p"
        % (t, u, k, u - k, "높음" if u > k else "낮음", len(gaps), inv, wt, wg))


def _p_fx(conn):
    cur = conn.execute("SELECT pair, rate, prev_close, market_time, market_state"
                       " FROM fx_live")
    rows = {r["pair"]: r for r in cur.fetchall()}
    if not rows:
        return None
    L = ["지금 환율 (야후 지연 시세 · 5분마다 갱신)"]
    for pair, nm in (("USDKRW", "원/달러"), ("EURKRW", "원/유로")):
        r = rows.get(pair)
        if not r or r["rate"] is None:
            continue
        chg = (r["rate"] - r["prev_close"]) if r["prev_close"] else None
        L.append("  %s %s원%s · %s 기준" % (
            nm, format(r["rate"], ",.2f"),
            "" if chg is None else " (전일 종가 대비 %+.2f원)" % chg,
            (r["market_time"] or "")[:16].replace("T", " ")))
    days = conn.execute("SELECT date, rate FROM fx WHERE pair='USDKRW'"
                        " ORDER BY date DESC LIMIT 5").fetchall()
    if days:
        L.append("  원/달러 최근 종가 " +
                 " ".join("%s %.2f" % (d["date"][5:], d["rate"]) for d in reversed(days)))
    return "환율", "\n".join(L)


def _p_articles(conn, n=2):
    # ⚠️ daily 는 "어느 날 어느 기사를 골랐나" 만 들고 있다. 내용은
    #    article_analysis 에 있다 (/api/daily 가 하는 것과 같은 조인).
    rows = conn.execute(
        "SELECT d.date, COALESCE(a.title, d.title) AS title, a.title_ko,"
        "       COALESCE(a.source, d.source) AS source,"
        "       COALESCE(a.sentiment, d.sentiment) AS sentiment,"
        "       COALESCE(a.brief, d.brief) AS brief, a.impacts"
        "  FROM daily d LEFT JOIN article_analysis a ON a.url = d.url"
        " ORDER BY d.date DESC LIMIT ?", (n,)).fetchall()
    if not rows:
        return None
    import json
    L = ["AI 가 고른 기사 (최신 %d건)" % len(rows)]
    for r in rows:
        L.append("  [%s · %s · %s] %s" % (
            r["date"], r["sentiment"] or "-", r["source"], r["title_ko"] or r["title"]))
        if r["brief"]:
            L.append("    " + r["brief"])
        try:
            imp = json.loads(r["impacts"] or "[]")[:3]
            if imp:
                L.append("    영향 " + " · ".join(
                    "%s %s%s" % (i["company"], i["sentiment"],
                                 "(추정)" if i.get("kind") == "간접" else "")
                    for i in imp))
        except Exception:
            pass
    return "기사", "\n".join(L)


# ⚠️ 주가는 DB 에 다 있지 않다. 매일 쌓는 건 미국 7종목뿐이고, 나머지는
#    종목별 탭이 **물어볼 때 야후에서 그 자리에서** 받아온다(검색된 적 있는
#    종목만 company_daily 에 한 건씩 남는다).
#    채팅에서 야후를 부르면 3~4초가 더 붙는다. 그래서 여기서는 **저장된 것만**
#    쓰고, 없으면 종목별 탭으로 안내한다. 같은 일을 두 군데서 하지 않는다.
_STALE_DAYS = 5


def _p_stock(conn, tk):
    nm = tickers.name_of(tk) or tk
    won = tk.endswith((".KS", ".KQ")) or tk.startswith("^KS")
    cur = "원" if won else "달러"

    rows = conn.execute(
        "SELECT date, close FROM prices WHERE ticker=? ORDER BY date DESC LIMIT 6",
        (tk,)).fetchall()
    if rows:
        c0, c1 = rows[0], (rows[1] if len(rows) > 1 else None)
        L = ["%s (%s) · %s 종가 기준" % (nm, tk, c0["date"])]
        if c1 and c1["close"]:
            L.append("  %s%s (전일 대비 %+.2f%%)" % (
                format(c0["close"], ",.2f"), cur,
                (c0["close"] - c1["close"]) / c1["close"] * 100))
        L.append("  최근 종가 " + " ".join(
            "%s %.2f" % (r["date"][5:], r["close"]) for r in reversed(rows)))
    else:
        L = None

    d = conn.execute(
        "SELECT date, close, change_pct, ai_summary FROM company_daily"
        " WHERE ticker=? ORDER BY date DESC LIMIT 1", (tk,)).fetchone()

    if L is None:
        if not d:
            # 사전엔 있는데 가진 자료가 없다. 조용히 빠지지 말고 그렇다고 말한다.
            return nm, ("%s 는 지금 저장된 자료가 없습니다.\n"
                        "  종목별 탭에서 검색하면 그 자리에서 받아와 분석합니다."
                        % nm)
        old = (datetime.date.today()
               - datetime.date.fromisoformat(d["date"])).days
        if old > _STALE_DAYS:
            # ⚠️ 오래된 값을 '지금 주가' 처럼 말하면 거짓말이 된다. 날짜를 앞세운다.
            return nm, ("%s · 마지막으로 저장된 건 %s 자료입니다 (%d일 전).\n"
                        "  그때 %s%s%s\n"
                        "  지금 값은 종목별 탭에서 검색하면 받아옵니다."
                        % (nm, d["date"], old,
                           format(d["close"], ",.2f") if d["close"] else "-", cur,
                           " (%+.2f%%)" % d["change_pct"] if d["change_pct"] else ""))
        L = ["%s (%s) · %s 기준" % (nm, tk, d["date"])]
        if d["close"]:
            L.append("  %s%s%s" % (format(d["close"], ",.2f"), cur,
                                   " (%+.2f%%)" % d["change_pct"] if d["change_pct"] else ""))

    if d and d["ai_summary"]:
        L.append("  AI 분석(%s) %s" % (d["date"], d["ai_summary"][:160]))
    return nm, "\n".join(L)


# ── 조립 ──

BUDGET = 800          # 토큰. 작게 시작한다 — 늘리는 건 쉽고 줄이는 건 어렵다.


def build(conn, question, budget=BUDGET):
    """질문 → 근거 조각들.

    돌려주는 것
      matched   하나라도 걸렸나. False 면 **LLM 을 부르지 말 것**
      context   프롬프트에 끼울 문자열
      sources   화면에 "무엇을 봤는지" 로 보여줄 라벨들
      tokens    어림 토큰 수
      dropped   예산 때문에 버린 조각 수
    """
    import indicators

    q = question or ""
    pieces = []                       # (우선순위, 라벨, 본문)

    # ① 지표 — 질문에 걸린 것만. 걸리면 그 나라 것만.
    want = [k for k, words in _IND.items() if _has(q, words)]
    if want:
        items = indicators.build(conn)
        cc = _countries(q)
        for name in want:
            for d in items:
                if d["name"] == name and d["country"] in cc:
                    pieces.append((0,) + _p_indicator(d))
        # 금리를 물었고 나라를 안 밝혔으면 금리차가 거의 항상 답의 일부다
        if "금리" in want and len(cc) == 2:
            gap = _p_rategap(items)
            if gap:
                pieces.append((0,) + gap)

    # ② 환율
    if _has(q, _FX):
        p = _p_fx(conn)
        if p:
            pieces.append((1,) + p)

    # ③ 종목
    for tk in _stocks(q):
        p = _p_stock(conn, tk)
        if p:
            pieces.append((1,) + p)

    # ④ 기사 — 다른 게 아무것도 안 걸렸을 때만 넉넉히 넣는다.
    #    "금리 어때?" 에 기사까지 끼워 넣으면 예산만 먹고 답은 흐려진다.
    if _has(q, _ART):
        p = _p_articles(conn, 2 if pieces else 3)
        if p:
            pieces.append((2,) + p)

    if not pieces:
        return {"matched": False, "context": "", "sources": [],
                "tokens": 0, "dropped": 0}

    # 예산 안에서 자른다. 우선순위 → 넣은 순서.
    pieces.sort(key=lambda p: p[0])
    kept, used, dropped = [], 0, 0
    for _, label, body in pieces:
        t = _tokens(body)
        if used + t > budget and kept:
            dropped += 1
            continue
        kept.append((label, body))
        used += t

    return {
        "matched": True,
        "context": "\n\n".join(b for _, b in kept),
        "sources": [l for l, _ in kept],
        "tokens": used,
        "dropped": dropped,
    }


# ⚠️ 규칙이 못 잡은 질문을 남긴다. 사전을 뭘로 늘릴지가 데이터로 나온다
#    ('유가' 가 0건이어서 업종 검색을 만들었던 것과 같은 길).
def log_miss(conn, question):
    conn.execute("CREATE TABLE IF NOT EXISTS chat_miss ("
                 " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " question TEXT, asked_at TEXT)")
    conn.execute("INSERT INTO chat_miss (question, asked_at) VALUES (?, ?)",
                 (question[:300], datetime.datetime.now().isoformat(timespec="seconds")))
    conn.commit()
