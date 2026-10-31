"""환율 날짜별 기록 백필 — fx 시계열에서 최근 N거래일의 AI 해설을 생성.
이미 fx_daily에 있는 날짜는 건너뜀(기존 보존).

⚠️ 2026-10-31 — 이 기능은 `python fx_curate.py --backfill 14` 로 흡수됐다.
   같은 프롬프트·같은 at() 을 두 파일에 두면 한쪽만 고쳐져서 어긋난다
   (환율 숫자 불일치 버그가 정확히 그렇게 생겼다). 이 파일은 지워도 된다."""
import sqlite3
from llm import generate_json

DAYS = 14  # 최근 며칠치 채울지

conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS fx_daily (
  date TEXT PRIMARY KEY,
  summary_usdkrw REAL,      -- 해설이 본 숫자. 종가가 아니다 (fx_curate.py 설명 참고)
  summary_eurkrw REAL,
  ai_summary TEXT
)""")
conn.commit()

dates = [r["date"] for r in cur.execute(
    "SELECT DISTINCT date FROM fx WHERE pair='USDKRW' ORDER BY date DESC LIMIT ?", (DAYS,))]
dates.reverse()  # 오래된 날짜부터


def at(pair, d):
    rows = cur.execute("SELECT rate FROM fx WHERE pair=? AND date<=? ORDER BY date DESC LIMIT 2",
                       (pair, d)).fetchall()
    if len(rows) < 2:
        return None, None
    return rows[0]["rate"], rows[0]["rate"] - rows[1]["rate"]


def direction(chg):
    if chg is None:
        return "데이터 없음"
    if chg > 0.5:
        return "원화 약세(환율 상승)"
    if chg < -0.5:
        return "원화 강세(환율 하락)"
    return "보합"


made = 0
for iso in dates:
    if cur.execute("SELECT 1 FROM fx_daily WHERE date=?", (iso,)).fetchone():
        continue
    usd, usd_chg = at("USDKRW", iso)
    eur, eur_chg = at("EURKRW", iso)
    if usd is None:
        continue
    usd_pct = (usd_chg / (usd - usd_chg) * 100) if (usd - usd_chg) else 0
    eur_txt = (f"원/유로 {eur:.2f}원 (전일 대비 {eur_chg:+.2f}원) — {direction(eur_chg)}"
               if eur is not None else "원/유로 데이터 없음")
    prompt = f"""{iso}의 환율이다.
- 원/달러 {usd:.2f}원 (전일 대비 {usd_chg:+.2f}원, {usd_pct:+.2f}%) — {direction(usd_chg)}
- {eur_txt}

경제 초보자에게 "이날 환율 변동이 우리(한국) 경제에 어떤 영향을 주는지" 설명하라.

반드시 지킬 것:
1) 환율은 한쪽만 좋은 게 아니라 **양면적**이다. 유리한 쪽과 불리한 쪽을 **둘 다** 짚어라.
   - 환율 상승(원화 약세) → 수출기업에 유리 / 수입물가·기름값·해외여행·유학 비용엔 부담
   - 환율 하락(원화 강세) → 수입 부담 완화·물가 안정에 도움 / 수출기업엔 불리
2) **달러를 중심으로** 설명하고, 유로는 보조로 짧게만 언급하라.
3) 위에 주어진 숫자만 사용하라. **왜 움직였는지 원인은 추측하지 마라**(뉴스 정보가 없음).

아래 JSON 형식으로만 한국어로 답하라:
{{"ai_summary": "<초보자용 4~6문장. (1) 어느 방향으로 얼마나 움직였는지 (2) 누구에게 유리/불리한지(양면) (3) 생활에 뭐가 달라지는지.>"}}"""
    try:
        summary = generate_json(prompt)["ai_summary"]
    except Exception as e:
        print(f"{iso}: 실패 ({e.__class__.__name__}) — 건너뜀")
        continue
    cur.execute(
        "INSERT INTO fx_daily (date, summary_usdkrw, summary_eurkrw, ai_summary) VALUES (?, ?, ?, ?)",
        (iso, usd, eur, summary))
    conn.commit()
    made += 1
    print(f"{iso}: 원/달러 {usd:.2f}({usd_chg:+.2f}) · 원/유로 {eur:.2f}({eur_chg:+.2f})")

conn.close()
print(f"환율 날짜별 기록 백필 완료 (신규 {made}건)")
