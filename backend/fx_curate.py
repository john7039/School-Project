"""오늘 환율 변동이 한국 경제에 주는 영향을 로컬 AI가 초보자용으로 설명.
환율은 한쪽만 좋은 게 아니라 양면적이므로(수출 유리 ↔ 수입물가 부담) 양쪽을 다 짚게 한다."""
import sqlite3
import datetime
from llm import generate_json

conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS fx_daily (
  date TEXT PRIMARY KEY,
  usdkrw REAL, usdkrw_chg REAL,
  eurkrw REAL, eurkrw_chg REAL,
  ai_summary TEXT
)""")
conn.commit()

# 기록 날짜 = 환율 데이터의 최신 거래일 (주가처럼 '그날의 환율'로 기록)
row = cur.execute("SELECT max(date) d FROM fx WHERE pair='USDKRW'").fetchone()
iso = row["d"] if row else None
if not iso:
    print("환율 데이터 없음 — 먼저 collect_fx 실행 필요")
    conn.close()
    raise SystemExit

if cur.execute("SELECT 1 FROM fx_daily WHERE date=?", (iso,)).fetchone():
    print(f"{iso}: 환율 분석 이미 있음 — 생략")
    conn.close()
    raise SystemExit


def at(pair, d):
    """d일 종가와 직전 거래일 대비 증감"""
    rows = cur.execute("SELECT rate FROM fx WHERE pair=? AND date<=? ORDER BY date DESC LIMIT 2",
                       (pair, d)).fetchall()
    if len(rows) < 2:
        return None, None
    return rows[0]["rate"], rows[0]["rate"] - rows[1]["rate"]


usd, usd_chg = at("USDKRW", iso)
eur, eur_chg = at("EURKRW", iso)
if usd is None:
    print("환율 데이터 부족 — 다음 실행에서 재시도")
    conn.close()
    raise SystemExit


def direction(chg):
    if chg is None:
        return "데이터 없음"
    if chg > 0.5:
        return "원화 약세(환율 상승)"
    if chg < -0.5:
        return "원화 강세(환율 하락)"
    return "보합"


usd_pct = (usd_chg / (usd - usd_chg) * 100) if usd_chg is not None and (usd - usd_chg) else 0
eur_txt = (f"원/유로 {eur:.2f}원 (전일 대비 {eur_chg:+.2f}원) — {direction(eur_chg)}"
           if eur is not None else "원/유로 데이터 없음")

prompt = f"""오늘({iso}) 환율이다.
- 원/달러 {usd:.2f}원 (전일 대비 {usd_chg:+.2f}원, {usd_pct:+.2f}%) — {direction(usd_chg)}
- {eur_txt}

경제 초보자에게 "오늘 환율 변동이 우리(한국) 경제에 어떤 영향을 주는지" 설명하라.

반드시 지킬 것:
1) 환율은 한쪽만 좋은 게 아니라 **양면적**이다. 유리한 쪽과 불리한 쪽을 **둘 다** 짚어라.
   - 환율 상승(원화 약세) → 수출기업에 유리 / 수입물가·기름값·해외여행·유학 비용엔 부담
   - 환율 하락(원화 강세) → 수입 부담 완화·물가 안정에 도움 / 수출기업엔 불리
2) **달러를 중심으로** 설명하고, 유로는 보조로 짧게만 언급하라(한국 경제엔 달러 영향이 더 크다).
3) 위에 주어진 숫자만 사용하라. **왜 움직였는지 원인은 추측하지 마라**(뉴스 정보가 없음).

아래 JSON 형식으로만 한국어로 답하라:
{{"ai_summary": "<초보자용 4~6문장. 순서대로 (1) 오늘 어느 방향으로 얼마나 움직였는지 (2) 누구에게 유리하고 누구에게 불리한지(양면) (3) 내 생활에 당장 뭐가 달라지는지. 중학생도 이해할 쉬운 말로.>"}}"""

try:
    data = generate_json(prompt)
    summary = data["ai_summary"]
except Exception as e:
    print(f"{iso}: 실패 ({e.__class__.__name__}) — 다음 실행에서 재시도")
    conn.close()
    raise SystemExit

cur.execute(
    "INSERT INTO fx_daily (date, usdkrw, usdkrw_chg, eurkrw, eurkrw_chg, ai_summary) VALUES (?, ?, ?, ?, ?, ?)",
    (iso, usd, usd_chg, eur, eur_chg, summary))
conn.commit()
conn.close()
print(f"{iso}: 원/달러 {usd:.2f}({usd_chg:+.2f}) · 원/유로 {eur:.2f}({eur_chg:+.2f}) — 환율 분석 완료")
