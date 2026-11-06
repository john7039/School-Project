"""한국 수출·수입을 처음 한 번 적재한다.

`collect.py` 의 INDICATORS 에 두 시리즈를 넣었으니 내일 07:00 부터는 자동으로
들어온다. 다만 그때까지 화면의 한국 칸이 비어 있게 되므로 한 번만 손으로 채운다.

`collect.py` 를 그냥 돌려도 되지만 그러면 주가·뉴스까지 다 다시 받는다.
지표 두 개만 필요해서 그 부분만 떼어 왔다.

**INSERT OR IGNORE 라서 이미 있는 행은 건드리지 않는다.** 여러 번 돌려도 같다.

왜 수출·수입만 FRED 인가 —
  한국은행 기준금리와 한국 소비자물가지수는 FRED 에서 끊겼다. OECD 가 2023년에
  데이터 플랫폼을 바꾸면서 MEI 계열을 대거 중단했는데, **series_id 는 남아 있어서
  받아오면 200 으로 성공하고 2025-04 값을 준다.** 그래서 그 둘은 넣지 않았다.
  (KORCPICORMINMEI 2025-04 / 기준금리는 살아 있는 시리즈가 아예 없다.)
  → 한국은행 ECOS API 로 받아야 한다.

금액 크기를 한 번 의심했다가 확인한 기록 —
  2026-08 수출이 982.8억 달러로 나와서 "연 1.18조 달러는 너무 크다" 고 의심했다.
  세 시리즈가 서로 맞았다. XTEXVA01KRM667N(달러) 과 KORXTEXVA01NCMLM(원) 으로
  환율을 역산하면 1,403.7원이고, 우리 fx 테이블의 그 무렵 값이 1,428~1,436원이다.
  월평균 환산 기준으로 들어맞는다. **데이터가 맞았고 내 기억이 낡았다.**
"""

import os
import sqlite3
import sys

from fredapi import Fred

COUNTRY = "KR"
SERIES = {"수출": "XTEXVA01KRM667N", "수입": "XTIMVA01KRM667N"}
START = "2023-01-01"            # 미국 지표와 같은 시작점


def fred_key():
    """systemd 로 돌 때는 환경변수, 손으로 돌 때는 .env 에서 읽는다."""
    key = os.environ.get("FRED_API_KEY")
    if key:
        return key
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, ".env"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("FRED_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("FRED_API_KEY 를 찾지 못했다")


def main(db="econ.db"):
    fred = Fred(api_key=fred_key())
    conn = sqlite3.connect(db)
    cur = conn.cursor()

    for name, series_id in SERIES.items():
        series = fred.get_series(series_id, observation_start=START)

        # FRED 의 date 는 '기준월' 이지 발표일이 아니다. 발표일을 따로 받는다.
        released = {}
        try:
            df = fred.get_series_all_releases(series_id, realtime_start=START)
            for ref, rel in df.groupby("date")["realtime_start"].min().items():
                released[str(ref.date())] = str(rel.date())
        except Exception as e:
            print(f"  {name} 발표일 조회 실패: {e.__class__.__name__} (기준월만 저장)")

        added = 0
        for date, value in series.items():
            if value != value:          # NaN
                continue
            iso = str(date.date())
            cur.execute(
                "INSERT OR IGNORE INTO indicators"
                " (country, name, date, value, release_date) VALUES (?, ?, ?, ?, ?)",
                (COUNTRY, name, iso, float(value), released.get(iso)))
            added += cur.rowcount
        conn.commit()

        n, lo, hi = cur.execute(
            "SELECT COUNT(*), MIN(date), MAX(date) FROM indicators"
            " WHERE country=? AND name=?", (COUNTRY, name)).fetchone()
        last = cur.execute(
            "SELECT value, release_date FROM indicators WHERE country=? AND name=?"
            " ORDER BY date DESC LIMIT 1", (COUNTRY, name)).fetchone()
        print(f"{name}: 새로 {added}행 · 보유 {n}행 {lo}~{hi} · "
              f"마지막 {last[0] / 1e8:,.1f}억 달러 ({last[1] or '발표일 없음'})")

    conn.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "econ.db")
