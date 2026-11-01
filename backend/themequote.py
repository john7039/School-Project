"""테마 하나의 종목 시세를 한 번에 받고, 업종 수준으로 읽어낸다.

종목 하나씩 get_info() 로 받으면 8종목에 5초가 걸린다. yf.download() 는
한 번에 1.2초다. 그래서 목록은 download 로만 만든다.

⚠️ 거래량은 돌려주지 않는다.
download 와 get_info 의 거래량이 다르다 (168.0M vs 165.9M). 목록에 넣으면
오른쪽 목록과 왼쪽 상세가 어긋난다 — 환율에서 같은 숫자를 두 곳에 저장했다가
32일 중 13일이 틀렸던 것과 같다. 가격과 등락률은 두 소스가 정확히 일치해서
그것만 쓴다.

그리고 업종 수준 판단은 AI 가 아니라 코드가 한다.
"반도체가 왜 같이 내렸나" 에 답하려면 거시 인과가 필요한데 우리 데이터에는
주가와 기업별 뉴스뿐이다. 근거 없이 물어보면 모델은 "금리 우려로" 같은 것을
지어낸다 — 거래량을 지어냈던 것과 같은 구조다. 그래서 아래 judge() 가 내리는
판단은 전부 계산이고, 틀릴 수가 없다.
"""
import datetime
import threading
import time

import themes as TH
import tickers as TK
from korean import with_josa

TTL = 60
_CACHE = {}
_LOCK = threading.Lock()


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _rows(symbols):
    """[{symbol, price, prev, chg, pct}] — 받아오지 못한 심볼은 빠진다."""
    import yfinance as yf
    try:
        h = yf.download(" ".join(symbols), period="7d", interval="1d",
                        progress=False, auto_adjust=True, group_by="ticker",
                        threads=True)
    except Exception as e:
        print(f"  테마 시세 실패: {e.__class__.__name__}")
        return [], None
    if h is None or len(h) == 0:
        return [], None

    out, last_day = [], None
    for sym in symbols:
        try:
            closes = h[sym]["Close"].dropna()
        except Exception:
            continue
        if len(closes) < 2:
            continue
        price, prev = _num(closes.iloc[-1]), _num(closes.iloc[-2])
        if price is None or prev is None or prev == 0:
            continue
        day = closes.index[-1].strftime("%Y-%m-%d")
        last_day = last_day or day
        out.append({
            "symbol": sym,
            "price": round(price, 2),
            "prev": round(prev, 2),
            "chg": round(price - prev, 2),
            "pct": round((price - prev) / prev * 100, 2),
            "date": day,
        })
    return out, last_day


def judge(items):
    """업종을 한 줄로 읽는다. 전부 계산이라 틀릴 수 없다.

    두 가지를 본다 —
      ① 방향이 모였나 갈렸나
      ② 한 곳만 유독 튀나  ← 종목 하나만 봐서는 알 수 없는 것
    """
    if not items:
        return None
    pcts = [x["pct"] for x in items]
    up = sum(1 for p in pcts if p > 0.1)
    down = sum(1 for p in pcts if p < -0.1)
    flat = len(pcts) - up - down
    avg = sum(pcts) / len(pcts)

    best = max(items, key=lambda x: x["pct"])
    worst = min(items, key=lambda x: x["pct"])

    n = len(items)
    if up >= n * 0.75:
        shape = "업종이 대체로 올랐습니다"
    elif down >= n * 0.75:
        shape = "업종이 대체로 내렸습니다"
    else:
        shape = "방향이 갈렸습니다"

    # 올랐다·내렸다·보합을 한 줄로. 보합을 빼면 합이 종목 수와 안 맞는다 —
    # 빅테크에서 "0곳 상승 5곳 하락" 이라고 쓰고 종목은 6개였다.
    parts = []
    if up:
        parts.append(f"{up}곳 상승")
    if down:
        parts.append(f"{down}곳 하락")
    if flat:
        parts.append(f"{flat}곳 보합")
    tally = " · ".join(parts) or f"{n}곳 보합"

    # 유독 튀는 곳 — 평균에서 가장 멀고, 그 거리가 충분히 클 때만
    odd, odd_note = None, None
    far = max(items, key=lambda x: abs(x["pct"] - avg))
    gap = abs(far["pct"] - avg)
    spread = max(pcts) - min(pcts)
    if gap >= 3.0 and gap >= spread * 0.45:
        odd = far["symbol"]
        side = "더 내렸습니다" if far["pct"] < avg else "더 올랐습니다"
        who = with_josa(TK.name_of(far["symbol"]), "는")
        odd_note = (f"{who} 업종 평균보다 {gap:.1f}%p 유독 {side}. "
                    f"업종 사정만은 아닐 수 있습니다")

    return {
        "up": up, "down": down, "flat": flat, "n": n,
        "tally": tally,
        "avg_pct": round(avg, 2),
        "spread": round(spread, 2),
        "shape": shape,
        "best": {"symbol": best["symbol"], "pct": best["pct"]},
        "worst": {"symbol": worst["symbol"], "pct": worst["pct"]},
        "odd": odd, "odd_note": odd_note,
    }


def load(key, use_cache=True):
    """테마 하나. 없는 테마면 None."""
    t = TH.get(key)
    if not t:
        return None

    if use_cache:
        with _LOCK:
            c = _CACHE.get(key)
            if c and time.time() - c[0] < TTL:
                return c[1]

    syms = TH.all_symbols(key)
    rows, last_day = _rows(syms)
    if not rows:
        return None

    idx_sym = t["index"][0] if t.get("index") else None
    index, items = None, []
    for r in rows:
        if idx_sym and r["symbol"] == idx_sym:
            index = dict(r, name=t["index"][1])
        else:
            items.append(dict(r, name=TK.name_of(r["symbol"])))

    # 많이 오른 것부터 — 위가 오른 쪽, 아래가 내린 쪽
    items.sort(key=lambda x: x["pct"], reverse=True)

    out = {
        "key": key,
        "name": t["name"],
        "short": t["short"],
        "date": last_day,
        "index": index,
        "items": items,
        "stats": judge(items),
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with _LOCK:
        _CACHE[key] = (time.time(), out)
    return out
