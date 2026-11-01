"""종목 현재 시세 — yfinance 한 번 호출로 화면에 필요한 수치를 모은다.

환율의 fx_live 와 같은 역할이지만 저장 방식이 다르다. 환율은 통화쌍이 둘뿐이라
5분마다 미리 받아 DB 에 넣어 두면 됐다. 종목은 검색 대상이 수천 개라 미리
받아둘 수 없어서, 물어볼 때 받아오고 짧게만 기억한다.

⚠️ 미국 정규장은 한국시간 23:30~06:00 이다.
낮에 보는 사용자에게 '현재가' 는 사실 '어제 종가' 다. 그래서 market_state 를
반드시 같이 돌려준다 — 환율에서 '하루의 경계' 를 자정으로 잘못 잡았다가
오늘 그래프에 어제 꼬리가 섞였던 것과 같은 함정이다. 숫자만 보여주고 언제
기준인지 안 말하면 사용자는 지금 값이라고 믿는다.
"""
import datetime
import threading
import time

TTL = 60          # 같은 종목을 이 시간 안에 다시 물으면 받아온 값을 그대로 준다
_CACHE = {}
_LOCK = threading.Lock()

STATE_KO = {
    "REGULAR":  ("정규장", "지금 거래 중입니다"),
    "PRE":      ("장 시작 전", "정규장 전 거래입니다"),
    "PREPRE":   ("장 시작 전", "곧 장이 열립니다"),
    "POST":     ("장 마감 후", "마감 후 거래입니다"),
    "POSTPOST": ("장 마감 후", "마감 후 거래가 끝났습니다"),
    "CLOSED":   ("마감", "미국장은 한국시간 23:30~06:00 에 열립니다"),
}


def _num(v):
    """yfinance 가 None·문자열·NaN 을 섞어 주므로 숫자만 통과시킨다."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f      # NaN 걸러내기


def _ts(unix):
    """yfinance 의 regularMarketTime 은 유닉스 초다. 서버 시간대(KST)로 바꾼다."""
    u = _num(unix)
    if not u:
        return None
    try:
        return datetime.datetime.fromtimestamp(u).isoformat(timespec="minutes")
    except (OSError, OverflowError, ValueError):
        return None


# 통화로 거래소 시간대를 안다. 거래일은 그 거래소의 시각으로 잘라야 한다.
#
# 미국만 있을 때는 America/New_York 으로 고정해도 됐다. 한국 종목이 들어오면
# 달라진다 — 삼성전자가 10-30 15:30(KST)에 마감하면 거래일은 10-30 인데,
# 뉴욕 시각으로 자르면 10-30 02:30 이라 우연히 같을 뿐이다. 우연에 기대면
# 언젠가 하루 어긋난다. 환율의 '하루' 를 자정으로 잡았다가 틀린 자리와 같다.
EXCHANGE_TZ = {"KRW": "Asia/Seoul", "USD": "America/New_York"}
DEFAULT_TZ = "America/New_York"

# 통화 표기
CURRENCY = {"USD": {"unit": "달러", "sym": "$", "decimals": 2},
            "KRW": {"unit": "원", "sym": "", "decimals": 0}}


def currency_info(code):
    return CURRENCY.get((code or "USD").upper(),
                        {"unit": (code or "").upper(), "sym": "", "decimals": 2})


def _trade_date(unix, currency="USD"):
    """그 시세가 '어느 거래일' 것인가 — 거래소 시각으로 잘라야 한다.

    ⚠️ 한국 시각으로 자르면 하루 어긋난다.
    금요일 미국 종가(16:00 EDT)는 한국시간 토요일 05:00 이다. KST 로 날짜를
    뽑으면 10-31 이 되지만, 거래일은 10-30 이고 prices 테이블·company_curate.py
    가 쓰는 날짜도 10-30 이다. 같은 장을 두 날짜로 저장하면 화면에 같은 날이
    두 줄로 쌓인다 — 환율에서 하루의 경계를 자정으로 잡았다가 틀린 것과 같다.
    """
    u = _num(unix)
    if not u:
        return None
    tzname = EXCHANGE_TZ.get((currency or "USD").upper(), DEFAULT_TZ)
    try:
        from zoneinfo import ZoneInfo
        local = datetime.datetime.fromtimestamp(u, ZoneInfo(tzname))
        return local.date().isoformat()
    except Exception:
        # 시간대 정보가 없는 환경이면 고정 시차로 근사한다 (여름시간 때 1시간
        # 오차가 생기지만, 날짜가 바뀌는 자정 근처가 아니면 결과는 같다)
        off = 9 if tzname == "Asia/Seoul" else -5
        try:
            return (datetime.datetime.utcfromtimestamp(u)
                    + datetime.timedelta(hours=off)).date().isoformat()
        except (OSError, OverflowError, ValueError):
            return None


def quote(ticker, use_cache=True):
    """한 종목의 현재 수치. 종목이 없거나 받아오지 못하면 None.

    None 과 '값이 0' 은 다르다. 호출하는 쪽에서 None 이면 '못 찾았다',
    값이 있는데 일부가 None 이면 '그 항목만 야후에 없다' 로 다뤄야 한다.
    """
    t = (ticker or "").upper().strip()
    if not t:
        return None

    if use_cache:
        with _LOCK:
            c = _CACHE.get(t)
            if c and time.time() - c[0] < TTL:
                return c[1]

    import yfinance as yf
    try:
        info = yf.Ticker(t).get_info() or {}
    except Exception as e:
        print(f"  시세 조회 실패 {t}: {e.__class__.__name__}")
        return None

    price = _num(info.get("regularMarketPrice"))
    if price is None:
        return None               # 존재하지 않는 티커. 야후는 빈 info 를 준다
    cur = (info.get("currency") or "USD").upper()
    ci = currency_info(cur)
    dp = ci["decimals"]
    # 지수는 통화가 아니다. 야후는 ^KS11 의 currency 를 KRW 로 주지만
    # 코스피 5,731 은 '5,731원' 이 아니라 지수값이다. 단위를 떼야 한다.
    if t.startswith("^"):
        ci = dict(ci, unit="", sym="")

    prev = _num(info.get("regularMarketPreviousClose"))
    raw_state = (info.get("marketState") or "CLOSED").upper()
    state_ko, state_note = STATE_KO.get(raw_state, ("마감", ""))

    # 장외 가격은 장전·장후 중 하나만 있다
    ext_price = _num(info.get("preMarketPrice"))
    ext_pct = _num(info.get("preMarketChangePercent"))
    ext_label = "장 시작 전"
    if ext_price is None:
        ext_price = _num(info.get("postMarketPrice"))
        ext_pct = _num(info.get("postMarketChangePercent"))
        ext_label = "장 마감 후"

    hi = _num(info.get("fiftyTwoWeekHigh"))
    lo = _num(info.get("fiftyTwoWeekLow"))
    # 52주 범위에서 현재가가 어디인가 (0=최저, 1=최고). 막대로 보여준다
    pos = None
    if hi is not None and lo is not None and hi > lo:
        pos = max(0.0, min(1.0, (price - lo) / (hi - lo)))

    q = {
        "ticker": t,
        "short_name": info.get("shortName") or t,
        "long_name": info.get("longName") or info.get("shortName") or t,
        "currency": cur,
        "unit": ci["unit"],
        "symbol": ci["sym"],
        "decimals": dp,
        "exchange": info.get("exchange") or "",
        "market_state": raw_state,
        "state_ko": state_ko,
        "state_note": state_note,
        "price": round(price, dp) if dp else round(price),
        "prev_close": (round(prev, dp) if dp else round(prev)) if prev is not None else None,
        "chg": (round(price - prev, dp) if dp else round(price - prev)) if prev is not None else None,
        "pct": _num(info.get("regularMarketChangePercent")),
        "quote_time": _ts(info.get("regularMarketTime")),
        "trade_date": _trade_date(info.get("regularMarketTime"), cur),
        "volume": info.get("regularMarketVolume"),
        "market_cap": info.get("marketCap"),
        "pe": _num(info.get("trailingPE")),
        "w52_high": (round(hi, dp) if dp else round(hi)) if hi is not None else None,
        "w52_low": (round(lo, dp) if dp else round(lo)) if lo is not None else None,
        "w52_pos": round(pos, 4) if pos is not None else None,
        "ext_price": (round(ext_price, dp) if dp else round(ext_price)) if ext_price is not None else None,
        "ext_pct": ext_pct,
        "ext_label": ext_label if ext_price is not None else None,
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    if q["pct"] is not None:
        q["pct"] = round(q["pct"], 2)
    if q["ext_pct"] is not None:
        q["ext_pct"] = round(q["ext_pct"], 2)

    with _LOCK:
        _CACHE[t] = (time.time(), q)
    return q


def history(ticker, days=30):
    """최근 일별 종가·거래량. 오래된 것부터.

    [{"date": "2026-10-30", "close": 204.64, "volume": 165923799}, ...]
    """
    import yfinance as yf
    t = ticker.upper()
    # 원화 종목은 소수점이 의미가 없다 — 225000.00원 은 읽기만 나쁘다
    dp = 0 if t.endswith((".KS", ".KQ")) else 2
    try:
        h = yf.Ticker(t).history(period=f"{max(days + 10, 40)}d",
                                              interval="1d")
    except Exception as e:
        print(f"  추이 조회 실패 {t}: {e.__class__.__name__}")
        return []
    out = []
    for idx, row in h.iterrows():
        c = _num(row.get("Close"))
        if c is None:
            continue
        v = _num(row.get("Volume"))
        out.append({"date": idx.strftime("%Y-%m-%d"),
                    "close": round(c, dp) if dp else round(c),
                    "volume": int(v) if v else None})
    return out[-days:]


def volume_note(hist, volume, skip_last=True):
    """거래량이 평소와 비교해 어떤지 한 마디로. 비교할 게 없으면 None.

    ⚠️ 이걸 만든 이유 — 프롬프트에 거래량 숫자만 넣었더니 AI 가
    "거래량이 크게 늘어나면서" 라고 썼다. 평균을 알려준 적이 없는데
    지어낸 것이다. 비교 기준을 주지 않으면 모델은 추측하고,
    추측한 문장은 사실처럼 읽힌다.
    """
    if not volume or not hist:
        return None
    past = hist[:-1] if skip_last and len(hist) > 1 else hist
    vols = [h["volume"] for h in past if h.get("volume")]
    if len(vols) < 5:
        return None
    avg = sum(vols) / len(vols)
    if avg <= 0:
        return None
    r = volume / avg
    if r >= 1.5:
        word = "평소보다 많다"
    elif r >= 1.15:
        word = "평소보다 약간 많다"
    elif r <= 0.67:
        word = "평소보다 적다"
    elif r <= 0.87:
        word = "평소보다 약간 적다"
    else:
        word = "평소와 비슷하다"
    return f"최근 {len(vols)}거래일 평균의 {r:.1f}배 — {word}"


def intraday(ticker):
    """그 종목의 '하루' 가 어떻게 움직였는지 — 5분봉.

    period="1d" 는 가장 최근 장 하루를 준다. 주말에 불러도 금요일 장이 나온다.

    시각은 미국 동부 시각으로 그대로 쓴다. 한국 시각으로 바꾸면 23:30 에
    시작해 다음날 06:00 에 끝나서, 한 장이 이틀에 걸쳐 보인다 — 그래프의
    가로축이 자정을 넘어가면 '하루' 로 읽히지 않는다. 그래서 09:30~16:00
    으로 두고, 한국 시각은 화면 설명으로 알려준다.

    ⚠️ 마지막 봉의 종가와 공식 종가는 조금 다르다 (204.81 vs 204.64).
    그래서 이 함수는 '모양' 만 돌려주고 대표 숫자는 quote() 것을 쓴다.
    같은 값을 두 곳에서 가져오면 카드와 그래프가 어긋난다 — 환율에서
    32일 중 13일이 그랬다.
    """
    import yfinance as yf
    t = (ticker or "").upper().strip()
    kr = t.endswith((".KS", ".KQ"))
    dp = 0 if kr else 2
    try:
        h = yf.Ticker(t).history(period="1d", interval="5m")
    except Exception as e:
        print(f"  장중 조회 실패 {t}: {e.__class__.__name__}")
        return None
    if h is None or len(h) < 2:
        return None

    pts, closes = [], []
    for idx, row in h.iterrows():
        c = _num(row.get("Close"))
        if c is None:
            continue
        pts.append({"t": idx.strftime("%H:%M"),
                    "price": round(c, dp) if dp else round(c)})
        closes.append(c)
    if len(pts) < 2:
        return None

    def r(v):
        return round(v, dp) if dp else round(v)

    op, last = closes[0], closes[-1]
    return {
        "session": h.index[0].strftime("%Y-%m-%d"),
        "tz": "한국" if kr else "미국 동부",
        "kr": kr,
        "open_at": pts[0]["t"],
        "close_at": pts[-1]["t"],
        "points": pts,
        "open": r(op),
        "last": r(last),
        "high": r(max(closes)),
        "low": r(min(closes)),
        "chg": r(last - op),
        "pct": round((last - op) / op * 100, 2) if op else None,
    }
