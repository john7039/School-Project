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
# ⚠️ 저장된 AI 분석은 **"오늘 코스피는…" 으로 시작한다.** 그 '오늘' 은 쓴 날이지
#   지금이 아니다. 그대로 넘겼더니 11-04 분석을 받아온 11-11 시세와 묶어
#   "같은 날 종가 210,500원" 이라고 답했다.
#   날짜로 바꿔 넣고, 너무 오래된 건 아예 안 넣는다.
_ANALYSIS_MAX_DAYS = 3


def _p_analysis(conn, tk):
    d = conn.execute("SELECT date, ai_summary FROM company_daily WHERE ticker=?"
                     " AND IFNULL(ai_summary,'')<>'' ORDER BY date DESC LIMIT 1",
                     (tk,)).fetchone()
    if not d:
        return None
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(d["date"])).days
    except Exception:
        return None
    if age > _ANALYSIS_MAX_DAYS:
        return None               # 지금 수치를 물었는데 일주일 전 해설은 헷갈리기만 한다
    when = "%d월 %d일" % (int(d["date"][5:7]), int(d["date"][8:10]))
    txt = d["ai_summary"][:160].replace("오늘", when)
    return "  %s 분석 — %s" % (when, txt)


# ⚠️ 주가·지수는 **하루만 지나도 낡은 값**이다. 5일로 뒀더니 코스피를 물었을 때
#    닷새 전(11-06) 수치를 "2026-11-06 기준" 이라고만 하고 넘겼다 — 날짜는
#    맞지만 "지금 값은 다른 데 있다" 를 안 알려줬다.
#    오늘 것이 아니면 **항상** 며칠 전인지와 어디서 지금 값을 보는지 적는다.
_STALE_DAYS = 0


def _unit_of(tk):
    """저장된 값에만 쓴다. 받아온 값은 stockquote 가 단위를 같이 준다."""
    if tk.startswith("^"):
        return ""                 # 지수는 통화가 아니다. 코스피는 '원' 이 아니다
    return "원" if tk.endswith((".KS", ".KQ")) else "달러"


def _p_live(tk, nm):
    """⚠️ 처음엔 '채팅은 DB 만 본다' 로 했는데 틀렸다.

    "코스피 알려줘" 에 "저장된 건 닷새 전 것뿐이니 종목별 탭에 가보세요" 는
    답이 아니다. 묻는 사람은 **지금 수치**를 원한다.

    안 붙였던 이유 셋이 전부 약했다 —
      "3~4초 느려진다"      로컬 폴백은 7~10초고 그건 받아들였다
      "남용 통로가 된다"     사전에 걸린 종목만 부른다. 분당 6회 제한도 있다
      "같은 일을 두 군데서"   그 원칙은 **중복 화면**을 피하라는 것이지
                          같은 데이터 소스를 재사용하지 말라는 게 아니다

    `stockquote.quote()` 는 TTL 캐시가 있고 지수 단위도 이미 처리한다.
    """
    try:
        import stockquote
        return stockquote.quote(tk)
    except Exception as e:
        print("  채팅 시세 조회 실패 %s: %s" % (tk, e.__class__.__name__))
        return None


def _p_stock(conn, tk, notes, live=False):
    nm = tickers.name_of(tk) or tk
    cur = _unit_of(tk)

    q = _p_live(tk, nm) if live else None
    if q and q.get("price") is not None:
        u = q.get("unit") or ""
        L = ["%s (%s) · %s%s" % (q.get("short_name") or nm, tk,
                                 q.get("state_ko") or "", 
                                 " · %s 기준" % q["quote_time"] if q.get("quote_time") else "")]
        L.append("  %s%s%s" % (format(q["price"], ",.%df" % (q.get("decimals") or 0)), u,
                               " (전일 대비 %+.2f%%)" % q["pct"] if q.get("pct") is not None else ""))
        if q.get("state_note"):
            L.append("  " + q["state_note"])
        # 받아온 지금 값 + 저장해 둔 최근 흐름·분석을 같이 준다
        rows = conn.execute(
            "SELECT date, close FROM prices WHERE ticker=? ORDER BY date DESC LIMIT 6",
            (tk,)).fetchall()
        if rows:
            L.append("  최근 종가 " + " ".join(
                "%s %.2f" % (r["date"][5:], r["close"]) for r in reversed(rows)))
        a = _p_analysis(conn, tk)
        if a:
            L.append(a)
        return nm, "\n".join(L)

    rows = conn.execute(
        "SELECT date, close FROM prices WHERE ticker=? ORDER BY date DESC LIMIT 6",
        (tk,)).fetchall()
    if rows:
        c0, c1 = rows[0], (rows[1] if len(rows) > 1 else None)
        gap = (datetime.date.today() - datetime.date.fromisoformat(c0["date"])).days
        L = ["%s (%s) · %s 종가 기준" % (nm, tk, c0["date"])]
        if c1 and c1["close"]:
            L.append("  %s%s (전일 대비 %+.2f%%)" % (
                format(c0["close"], ",.2f"), cur,
                (c0["close"] - c1["close"]) / c1["close"] * 100))
        L.append("  최근 종가 " + " ".join(
            "%s %.2f" % (r["date"][5:], r["close"]) for r in reversed(rows)))
        if gap > 3:
            # 주말·휴장이면 2~3일은 정상이다. 그보다 길면 수집이 밀린 것이다.
            L.append("  ⚠️ %d일 전 자료다. 그 뒤로 쌓인 게 없다." % gap)
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
            # ⚠️ 프롬프트에 적어도 LLM 이 흘린다 — 코스피 답에서 "지금 값이
            #    아니다" 가 빠지고 "저희가 보유한 최신 자료입니다" 로 바뀌었다.
            #    2~3문장 제한에 밀린다. **코드가 답 뒤에 붙여 보장한다.**
            notes.append("%s는 저장된 게 %s 자료뿐이에요. 지금 값은 "
                         "종목별 탭에서 검색하면 그 자리에서 받아옵니다."
                         % (nm, d["date"]))
            # ⚠️ 오래된 값을 '지금 값' 처럼 말하면 거짓말이 된다. 날짜를 앞세우고
            #    **지금 값을 어디서 보는지**까지 적는다. 둘 다 있어야 쓸모가 있다.
            return nm, ("%s · 저희가 들고 있는 건 %s 자료뿐입니다 (%d일 전).\n"
                        "  그때 %s%s%s\n"
                        "  **지금 값이 아닙니다.** 지금 값은 종목별 탭에서 "
                        "검색하면 그 자리에서 받아옵니다."
                        % (nm, d["date"], old,
                           format(d["close"], ",.2f") if d["close"] else "-", cur,
                           " (%+.2f%%)" % d["change_pct"] if d["change_pct"] else ""))
        L = ["%s (%s) · %s 기준" % (nm, tk, d["date"])]
        if d["close"]:
            L.append("  %s%s%s" % (format(d["close"], ",.2f"), cur,
                                   " (%+.2f%%)" % d["change_pct"] if d["change_pct"] else ""))

    a = _p_analysis(conn, tk)
    if a:
        L.append(a)
    return nm, "\n".join(L)


# ⚠️ 모아둔 뉴스 21,000건을 안 보고 있었다.
#   "젠슨황 요즘 이슈 있던데" 에 "자료에 없다" 고 답했는데, 그 이름이 우리
#   DB 기사 244건에 들어 있었다. daily(AI 가 고른 63건)만 보고 news 는
#   아예 안 봤다.
#
#   main.py 의 search_news() 를 그대로 쓰지 않는 이유 — 그 함수는 처음 보는
#   단어를 **그 자리에서 구글 뉴스에서 받아온다**(최대 15초). 채팅의 POST 는
#   즉시 답해야 하고, 아무 단어나 외부 호출을 일으키면 남용 통로가 된다.
#   **채팅은 DB 만 본다.** 없으면 기사 검색 탭으로 보낸다(거기가 받아오는 자리다).
_NEWS_MAX = 4
_NEWS_SUMMARY = 110


# 질문에서 '찾아볼 만한 말' 을 뽑는다.
#
# ⚠️ search_terms.expand() 는 **검색창용**이다 — "질문 전체 = 검색어" 를
#    가정해서, 문장을 넣으면 문장 전체를 한 덩어리로 돌려준다.
#    expand("젠슨황 요즘 이슈가 있던데") → ['젠슨황 요즘 이슈가 있던데']
#    그 문장이 기사 제목에 통째로 들어 있을 리가 없다. 그래서 0건이 됐다.
_STOP = {
    "요즘", "지금", "오늘", "어제", "내일", "최근", "이슈", "소식", "기사", "뉴스",
    "관련", "무슨", "어떤", "어때", "어떠", "어떻게", "있어", "있나", "있는", "있었",
    "있던데", "뭐야", "뭔가", "알려줘", "알려", "해줘", "대해", "대한", "그리고",
    "근데", "진짜", "정도", "같은", "같아", "때문", "하는", "하고", "입니다",
    "인가요", "인가", "일까", "일까요", "건가", "건데", "는데", "던데", "에서",
    "에게", "으로", "하기", "되는", "된다", "한다", "이라", "라고",
    "누구", "누구야", "누가", "어디", "언제", "얼마", "얼마나", "제발", "그래",
    "아니", "맞아", "그럼", "이거", "저거", "그거", "먹지", "하지", "보자",
}
# ⚠️ 1건짜리는 버린다. 물어볼 만한 주제면 보통 두 건 이상 있다.
#    '먹지' 가 기사 하나에 걸려서 "밥 뭐 먹지" 가 통과했다.
_WORD_MIN_HITS = 2
_WORD_MAX_HITS = 1200     # 21,000건 중 1,200건 넘게 걸리면 일반어다


def _candidates(q):
    raw = re.findall(r"[가-힣]{2,}|[A-Za-z]{2,}|\d{4,}", q)
    out = []
    for w in raw:
        if w.lower() in _STOP or w in _STOP:
            continue
        cands = [w]
        # ⚠️ 한국어는 외국 이름을 **띄어 쓴다** — DB 에는 '젠슨 황' 인데
        #    질문은 '젠슨황' 이다. 그래서 띄어쓰기를 넣어본다.
        #    끝 글자를 떼는 방식으로 했다가 크게 틀렸다 —
        #    '파이썬'→'파이' 가 '파이낸셜' 에, '누구야'→'누구' 가 아무 데나
        #    걸려서 범위 밖 질문이 전부 통과했다. 자르면 **다른 말**이 된다.
        if re.fullmatch(r"[가-힣]{3,6}", w):
            cands += [w[:i] + " " + w[i:] for i in range(2, len(w))]
        for c in cands:
            if c not in out and c.lower() not in _STOP and len(c) >= 2:
                out.append(c)
    return out[:10]


def _like(t):
    esc = t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + esc + "%"


def _p_news(conn, q):
    from search_terms import expand
    # 사전에 있는 말은 영어로도 넓혀서 같이 찾는다(기사가 영어라서).
    terms = [t for t in (expand(q) or [])[1:] if len(t) >= 2] + _candidates(q)
    if not terms:
        return None

    # ⚠️ 어느 말로 찾을지 **건수로 고른다.** 0건이면 없는 말이고, 너무 많이
    #    걸리면 일반어다('있던' 같은 것). 적게 걸리는 말이 가장 구체적이다.
    scored = []
    for t in terms:
        pat = _like(t)
        n = conn.execute(
            "SELECT COUNT(*) FROM news WHERE title LIKE ? ESCAPE '\\'"
            " OR IFNULL(title_ko,'') LIKE ? ESCAPE '\\'"
            " OR IFNULL(summary,'') LIKE ? ESCAPE '\\'", (pat, pat, pat)).fetchone()[0]
        if _WORD_MIN_HITS <= n <= _WORD_MAX_HITS:
            scored.append((n, t))
    if not scored:
        return None
    scored.sort()
    use = [t for _, t in scored[:3]]

    conds, params = [], []
    for t in use:
        pat = _like(t)
        conds.append("(title LIKE ? ESCAPE '\\' OR IFNULL(title_ko,'') LIKE ? ESCAPE '\\'"
                     " OR IFNULL(summary,'') LIKE ? ESCAPE '\\')")
        params += [pat, pat, pat]
    rows = conn.execute(
        "SELECT published, COALESCE(title_ko, title) AS t, title, source, summary"
        "  FROM news WHERE " + " OR ".join(conds) +
        " ORDER BY published DESC LIMIT ?", params + [_NEWS_MAX]).fetchall()
    if not rows:
        return None
    L = ["'%s' 로 찾은 기사 (최신 %d건 · 전부 지나간 기사다)"
         % (" · ".join(use), len(rows))]
    for r in rows:
        day = (r["published"] or "")[:8]
        day = "%s-%s-%s" % (day[:4], day[4:6], day[6:8]) if len(day) == 8 else day
        L.append("  [%s · %s] %s" % (day, r["source"] or "-", r["t"]))
        if r["summary"]:
            L.append("    " + re.sub(r"\s+", " ", r["summary"])[:_NEWS_SUMMARY])
    return "기사 검색", "\n".join(L)


# ── 조립 ──

BUDGET = 800          # 토큰. 작게 시작한다 — 늘리는 건 쉽고 줄이는 건 어렵다.


def build(conn, question, budget=BUDGET, live=False):
    """질문 → 근거 조각들.

    돌려주는 것
      matched   하나라도 걸렸나. False 면 **LLM 을 부르지 말 것**

    live=True — 종목·지수는 야후에서 **지금 값을 받아온다**(1~3초).
      POST 핸들러(probe)는 즉시 답해야 하므로 False 로 부르고,
      백그라운드 작업에서 True 로 다시 만든다.
      context   프롬프트에 끼울 문자열
      sources   화면에 "무엇을 봤는지" 로 보여줄 라벨들
      tokens    어림 토큰 수
      dropped   예산 때문에 버린 조각 수
    """
    import indicators

    q = question or ""
    pieces = []                       # (우선순위, 라벨, 본문)
    notes = []                        # 답 뒤에 **반드시** 붙일 말 (LLM 이 흘려도)

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
        p = _p_stock(conn, tk, notes, live)
        if p:
            pieces.append((1,) + p)

    # ④ 기사 — 다른 게 아무것도 안 걸렸을 때만 넉넉히 넣는다.
    #    "금리 어때?" 에 기사까지 끼워 넣으면 예산만 먹고 답은 흐려진다.
    if _has(q, _ART):
        p = _p_articles(conn, 2 if pieces else 3)
        if p:
            pieces.append((2,) + p)

    # ⑤ **모아둔 기사는 항상 찾아본다** (2ms). 사전에 없는 사람 이름·사건이
    #    여기 걸린다 — '젠슨황' 이 244건 있었다.
    #
    #    ⚠️ 처음엔 "아무것도 안 걸렸을 때만" 으로 했는데 틀렸다.
    #    "젠슨황 요즘 **이슈** 있던데" 는 '이슈' 가 _ART 에 걸려서 **오늘의
    #    기사 3건**(젠슨황과 무관)이 갔고, LLM 이 정직하게 "자료에 없다" 고
    #    답했다. 걸렸다고 해서 **맞는 게** 걸린 건 아니다.
    #    찾은 기사를 오늘의 기사보다 앞에 둔다(우선순위 1 vs 2).
    p = _p_news(conn, q)
    if p:
        pieces.append((1,) + p)

    if not pieces:
        return {"matched": False, "context": "", "sources": [],
                "tokens": 0, "dropped": 0, "notes": []}

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
        "notes": notes,
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
