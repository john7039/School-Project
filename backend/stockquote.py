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


def _trade_date(unix):
    """그 시세가 '어느 거래일' 것인가 — 미국 동부 시각으로 잘라야 한다.

    ⚠️ 한국 시각으로 자르면 하루 어긋난다.
    금요일 미국 종가(16:00 EDT)는 한국시간 토요일 05:00 이다. KST 로 날짜를
    뽑으면 10-31 이 되지만, 거래일은 10-30 이고 prices 테이블·company_curate.py
    가 쓰는 날짜도 10-30 이다. 같은 장을 두 날짜로 저장하면 화면에 같은 날이
    두 줄로 쌓인다 — 환율에서 하루의 경계를 자정으로 잡았다가 틀린 것과 같다.
    """
    u = _num(unix)
    if not u:
        return None
    try:
        from zoneinfo import ZoneInfo
        et = datetime.datetime.fromtimestamp(u, ZoneInfo("America/New_York"))
        return et.date().isoformat()
    except Exception:
        # 시간대 정보가 없는 환경이면 UTC-5 로 근사한다 (여름시간 때 1시간 오차가
        # 생기지만, 날짜가 바뀌는 자정 근처가 아니면 결과는 같다)
        try:
            return (datetime.datetime.utcfromtimestamp(u)
                    - datetime.timedelta(hours=5)).date().isoformat()
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
        "currency": info.get("currency") or "USD",
        "exchange": info.get("exchange") or "",
        "market_state": raw_state,
        "state_ko": state_ko,
        "state_note": state_note,
        "price": round(price, 2),
        "prev_close": round(prev, 2) if prev is not None else None,
        "chg": round(price - prev, 2) if prev is not None else None,
        "pct": _num(info.get("regularMarketChangePercent")),
        "quote_time": _ts(info.get("regularMarketTime")),
        "trade_date": _trade_date(info.get("regularMarketTime")),
        "volume": info.get("regularMarketVolume"),
        "market_cap": info.get("marketCap"),
        "pe": _num(info.get("trailingPE")),
        "w52_high": round(hi, 2) if hi is not None else None,
        "w52_low": round(lo, 2) if lo is not None else None,
        "w52_pos": round(pos, 4) if pos is not None else None,
        "ext_price": round(ext_price, 2) if ext_price is not None else None,
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
    try:
        h = yf.Ticker(ticker.upper()).history(period=f"{max(days + 10, 40)}d",
                                              interval="1d")
    except Exception as e:
        print(f"  추이 조회 실패 {ticker}: {e.__class__.__name__}")
        return []
    out = []
    for idx, row in h.iterrows():
        c = _num(row.get("Close"))
        if c is None:
            continue
        v = _num(row.get("Volume"))
        out.append({"date": idx.strftime("%Y-%m-%d"), "close": round(c, 2),
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
