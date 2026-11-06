import os
import sqlite3
import time
import yfinance as yf
from fredapi import Fred
from dotenv import load_dotenv

load_dotenv()
FRED_KEY = os.environ["FRED_API_KEY"]

TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "META"]
# ⚠️ 한국 CPI 는 여기 없다. FRED 의 한국 물가 시리즈는 전부 멈췄는데 ID 는
#    살아 있어서, 받아오면 200 으로 성공하고 몇 년 전 값을 준다.
#    OECD 에서 직접 받는다 → collect_oecd.py
#
# 한국 금리는 콜금리(은행 간 하루 금리)다. 한국은행 기준금리 그 자체는 ECOS
# 뿐인데, 비교 대상인 미국 FEDFUNDS 도 FOMC 목표가 아니라 실제 거래된 금리의
# 월평균이라 **오히려 이 쌍이 더 일관된다.** 화면에는 '콜금리' 라고 쓴다.
INDICATORS = {
    ("US", "CPI"): "CPIAUCSL",
    ("US", "금리"): "FEDFUNDS",
    ("US", "실업률"): "UNRATE",
    ("KR", "금리"): "IRSTCI01KRM156N",
    ("KR", "수출"): "XTEXVA01KRM667N",
    ("KR", "수입"): "XTIMVA01KRM667N",
}

conn = sqlite3.connect("econ.db")
cur = conn.cursor()

# prices 에 volume 컬럼 없으면 추가 (1회 자동 마이그레이션)
try:
    cur.execute("ALTER TABLE prices ADD COLUMN volume INTEGER")
    conn.commit()
except sqlite3.OperationalError:
    pass  # 이미 있음

# indicators 에 release_date(실제 발표일) 컬럼 없으면 추가 (1회 자동 마이그레이션)
try:
    cur.execute("ALTER TABLE indicators ADD COLUMN release_date TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass  # 이미 있음

# 주가 (거래량 포함, 종목별 실패해도 계속). INSERT OR REPLACE 로 기존 행에 volume 채움
for ticker in TICKERS:
    try:
        # 5년치: 지표 발표일(2023-01~) 전체 구간을 덮어야 지표축 분석이 성립한다.
        # 2년치였을 때는 2024-09 이전 발표 21건이 주가 데이터 범위 밖이었다.
        data = yf.Ticker(ticker).history(period="5y")
        for date, row in data.iterrows():
            # 장중 미완성 봉은 Open/Close 가 NaN 으로 온다. SQLite 엔 NaN 이 없어
            # NULL 로 저장돼 뒤에서 계산이 터지므로 아예 넣지 않는다.
            if row["Close"] != row["Close"] or row["Open"] != row["Open"]:
                continue
            cur.execute(
                "INSERT OR REPLACE INTO prices (ticker, date, open, close, volume) VALUES (?, ?, ?, ?, ?)",
                (ticker, str(date.date()), row["Open"], row["Close"], int(row["Volume"])))
    except Exception as e:
        print(f"주가 {ticker} 실패: {e.__class__.__name__} (건너뜀)")

conn.commit()  # 주가 먼저 저장

# 경제지표 (시리즈별 3회 재시도)
fred = Fred(api_key=FRED_KEY)
for (country, name), series_id in INDICATORS.items():
    for attempt in range(3):
        try:
            series = fred.get_series(series_id, observation_start="2023-01-01")

            # 실제 발표일 맵 — FRED 의 date 는 '기준월'이지 발표일이 아니다.
            # (2026-09 CPI 의 발표일은 2026-10-14) 발표 반응을 재려면 이 날짜를 써야 한다.
            released = {}
            try:
                df = fred.get_series_all_releases(series_id, realtime_start="2023-01-01")
                for ref, rel in df.groupby("date")["realtime_start"].min().items():
                    released[str(ref.date())] = str(rel.date())
            except Exception as e:
                print(f"지표 {name} 발표일 조회 실패: {e.__class__.__name__} (기준월만 저장)")

            for date, value in series.items():
                if value != value:
                    continue
                iso = str(date.date())
                rel = released.get(iso)
                cur.execute(
                    "INSERT OR IGNORE INTO indicators"
                    " (country, name, date, value, release_date) VALUES (?, ?, ?, ?, ?)",
                    (country, name, iso, float(value), rel))
                if rel:  # 기존 행(release_date 없이 저장됐던 것)도 채워준다
                    cur.execute(
                        "UPDATE indicators SET release_date=? WHERE country=? AND name=? "
                        "AND date=? AND (release_date IS NULL OR release_date='')",
                        (rel, country, name, iso))
            break
        except Exception as e:
            if attempt < 2:
                print(f"지표 {name} 재시도 {attempt + 1}/3 ({e.__class__.__name__}) ...")
                time.sleep(5)
            else:
                print(f"지표 {name} 실패: {e.__class__.__name__} (건너뜀)")

conn.commit()
conn.close()

# OECD 에서 직접 받는 것(한국 CPI)은 따로 돈다. 여기서 실패해도 위의 FRED
# 수집은 이미 저장됐으므로, 한쪽이 막혀도 나머지는 남는다.
try:
    import collect_oecd
    collect_oecd.main("econ.db")
except Exception as e:
    print(f"OECD 수집 실패: {e.__class__.__name__} (건너뜀)")

print("수집 완료")
