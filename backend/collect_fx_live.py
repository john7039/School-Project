"""현재 환율 시세 — 수 분 간격으로 갱신 (원/달러·원/유로).

collect_fx.py 와 역할이 다르다. 이 둘을 한 테이블에 섞었다가 숫자가 어긋났다.

    fx        확정된 일별 종가.  변하지 않는다.  그래프와 AI 해설의 근거
    fx_live   지금 시세.         계속 덮어쓴다.  화면 맨 위의 '현재'

시각을 둘 기록하는 이유 —
    fetched_at    우리가 언제 받아왔나   → 수집이 살아 있나
    market_time   시세가 언제 것인가     → 데이터가 신선한가
  방금 받아온 낡은 데이터는 여전히 낡았다. 둘은 서로 다른 질문이고,
  하나만 보면 "조용히 멈춘" 상태를 놓친다.

정직하게 — yfinance 는 야후 지연 시세다. 진짜 실시간이 아니다.
그래서 화면에 값만 띄우지 않고 market_time 을 함께 내보낸다.
"""
import datetime
import sqlite3
import sys

import yfinance as yf

PAIRS = {"USDKRW": "USDKRW=X", "EURKRW": "EURKRW=X"}


def market_closed(now):
    """외환시장 휴장 여부 (KST 기준).

    FX 는 뉴욕 금요일 17:00 에 닫고 일요일 17:00 에 연다.
    KST 로는 토요일 06:00 ~ 월요일 06:00 이 휴장이다.
    닫혀 있을 때는 외부 호출을 아예 하지 않는다 — yfinance 는 비공식 API라
    의미 없는 호출을 쌓으면 차단당할 수 있다.
    """
    wd, hm = now.weekday(), now.hour  # 월=0 … 토=5, 일=6
    if wd == 5 and hm >= 6:
        return True
    if wd == 6:
        return True
    if wd == 0 and hm < 6:
        return True
    return False


now = datetime.datetime.now()
if market_closed(now) and "--force" not in sys.argv:
    print(f"{now:%Y-%m-%d %H:%M} KST — 외환시장 휴장. 호출하지 않음 (강제: --force)")
    raise SystemExit

conn = sqlite3.connect("econ.db")
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS fx_live (
  pair TEXT PRIMARY KEY,
  rate REAL,
  bid REAL, ask REAL,
  prev_close REAL,
  market_time TEXT,     -- 시세 자체의 시각 (KST). 신선도의 근거
  market_state TEXT,    -- REGULAR / CLOSED 등 야후가 주는 값 그대로
  fetched_at TEXT       -- 우리가 받아온 시각 (KST)
)""")
conn.commit()

ok = 0
for pair, symbol in PAIRS.items():
    try:
        info = yf.Ticker(symbol).info
        rate = info.get("regularMarketPrice")
        if rate is None:
            print(f"{pair}: 시세 없음 — 건너뜀")
            continue
        mt = info.get("regularMarketTime")
        mt_iso = (datetime.datetime.fromtimestamp(mt).isoformat(timespec="seconds")
                  if mt else None)
        cur.execute(
            "INSERT OR REPLACE INTO fx_live "
            "(pair, rate, bid, ask, prev_close, market_time, market_state, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (pair, float(rate), info.get("bid"), info.get("ask"),
             info.get("regularMarketPreviousClose"), mt_iso,
             info.get("marketState"), now.isoformat(timespec="seconds")))
        conn.commit()  # 쌍별로 바로 저장 — 뒤에서 실패해도 앞의 것은 남는다
        ok += 1
        age = ""
        if mt:
            mins = (now - datetime.datetime.fromtimestamp(mt)).total_seconds() / 60
            age = f" · 시세는 {mins:.0f}분 전"
        print(f"{pair}: {rate:.2f}원 ({info.get('marketState')}){age}")
    except Exception as e:
        print(f"{pair} 실패: {e.__class__.__name__} — 건너뜀", file=sys.stderr)

conn.close()
if ok == 0:
    print("현재 시세를 한 건도 받지 못했다", file=sys.stderr)
    raise SystemExit(1)   # 전부 실패하면 유닛도 실패로 — OnFailure 가 알려준다
print(f"현재 환율 갱신 완료 ({ok}/{len(PAIRS)}쌍)")
