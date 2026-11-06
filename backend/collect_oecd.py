"""OECD 에서 직접 받는 지표. 지금은 한국 소비자물가지수 하나다.

왜 FRED 가 아니라 OECD 인가 —
  FRED 의 한국 CPI 시리즈는 전부 멈췄다. KORCPIALLMINMEI 는 2023-11,
  CPALTT01KRM657N 은 2024-03, KORCPICORMINMEI 는 2025-04 이 마지막이다.
  OECD 가 2023년에 데이터 플랫폼을 바꾸며 MEI 계열을 FRED 로 보내는 것을
  끊었기 때문이다. **그런데 series_id 는 FRED 에 그대로 남아 있어서, 받아오면
  200 으로 성공하고 2023~2025년 값을 준다.** 그냥 FRED 에서 받았으면 한국
  물가가 몇 년 전 값으로 조용히 떠 있었을 것이다.

  OECD 자체 API 는 멀쩡하다. 보내주던 것만 끊은 것이다.

⚠️ User-Agent 를 안 보내면 403 이다.
  curl 은 200 인데 파이썬 urllib 기본 요청은 거절당한다. 처음에 이것 때문에
  "OECD 도 안 된다" 고 잘못 판단할 뻔했다.

⚠️ 지수를 받아서 상승률은 우리가 계산한다 (indicators.py).
  OECD 는 전년 대비 상승률(PA/GY)도 주는데, 그걸 받으면 미국 CPI(지수를
  받아 우리가 계산)와 다른 길을 타게 된다. 지수(IX/_Z)를 받으면 두 나라
  CPI 가 같은 코드를 지난다. 기준연도가 달라도(미국 1982~84=100,
  한국 2020=100) 상승률로 바꾸면 비교가 된다.

⚠️ 발표일을 주지 않는다.
  release_date 가 NULL 로 들어간다. 신선도 감시(indicator_fresh.py)가
  발표일이 없으면 기준월 120일로 떨어뜨리는 이유가 이것이다.
"""

import json
import sqlite3
import sys
import urllib.request

BASE = "https://sdmx.oecd.org/public/rest/data/"
UA = {"User-Agent": "econ-slice/1.0 (graduation project)"}
START = "2023-01"                      # 미국 지표와 같은 시작점

# (나라, 이름) → SDMX 경로
SERIES = {
    ("KR", "CPI"): "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/KOR.M.N.CPI.IX._T.N._Z",
}


def fetch(path):
    """SDMX-JSON 을 [(기준월, 값)] 로. 기간이 값 안에 없고 인덱스로 따로 온다."""
    url = "%s%s?startPeriod=%s&format=jsondata" % (BASE, path, START)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        d = json.load(r)
    periods = [v["id"] for v in d["data"]["structure"]["dimensions"]["observation"][0]["values"]]
    rows = []
    for s in d["data"]["dataSets"][0]["series"].values():
        rows = sorted((periods[int(i)], v[0]) for i, v in s["observations"].items())
    return rows


def main(db="econ.db"):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    for (country, name), path in SERIES.items():
        try:
            rows = fetch(path)
        except Exception as e:
            print(f"OECD {country} {name} 실패: {e.__class__.__name__} (건너뜀)")
            continue

        added = 0
        for period, value in rows:
            if value is None:
                continue
            # 미국 지표와 날짜 꼴을 맞춘다. '2026-09' → '2026-09-01'
            iso = period + "-01"
            cur.execute(
                "INSERT OR IGNORE INTO indicators"
                " (country, name, date, value, release_date) VALUES (?, ?, ?, ?, NULL)",
                (country, name, iso, float(value)))
            added += cur.rowcount
        conn.commit()

        n, lo, hi = cur.execute(
            "SELECT COUNT(*), MIN(date), MAX(date) FROM indicators"
            " WHERE country=? AND name=?", (country, name)).fetchone()
        print(f"OECD {country} {name}: 새로 {added}행 · 보유 {n}행 {lo[:7]}~{hi[:7]}")

    conn.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "econ.db")
