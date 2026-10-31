"""환율 날짜별 AI 해설 — 생성 · 정정 · 백필을 한 엔진에서.

환율은 한쪽만 좋은 게 아니라 양면적이므로(수출 유리 ↔ 수입물가 부담) 양쪽을 다 짚게 한다.

왜 '정정'이 필요한가 —
  환율은 24시간 거래라 수집 시각(15:40)에는 그날 종가가 아직 확정되지 않는다.
  yfinance 가 주는 것은 진행 중인 값이다. 그 값으로 해설을 쓰면, 다음 날
  collect_fx 가 6개월치를 다시 받아 fx 를 정정해도 해설 본문의 숫자는 틀린 채 남는다.
  2026-10-31 점검에서 32일 중 13일이 그랬다 (최대 11.36원 차이).

  그래서 해설을 쓸 때 본 숫자를 summary_usdkrw 에 함께 남기고,
  나중에 fx 와 어긋나면 그 하루만 다시 생성한다.

  ⚠️ summary_usdkrw 는 '그날의 종가'가 아니다. '해설이 본 숫자'다.
     종가는 fx 한 곳에만 있고, 화면에 나가는 값은 /api/fx 가 거기서 계산한다.
     같은 숫자를 두 곳에 두면 반드시 어긋난다 — 그게 이 구조의 이유다.

사용법
  python fx_curate.py                최신 거래일 해설 생성 + 드리프트 보정 (최대 3건)
  python fx_curate.py --fix          전체 기간 드리프트 보정 (건수 제한 없음)
  python fx_curate.py --backfill 14  최근 14거래일 중 해설이 없는 날 채우기
"""
import sqlite3
import sys

from llm import generate_json

# 해설이 본 숫자와 fx 의 종가가 이만큼 넘게 벌어지면 다시 쓴다.
# 화면·본문이 소수점 둘째 자리까지 보여주므로 그보다 작은 차이는 눈에 안 보인다.
DRIFT = 0.01
# 기본 실행에서 한 번에 다시 쓸 최대 건수. LLM 호출이 줄줄이 늘어나는 것을 막는다.
MAX_FIX_PER_RUN = 3

conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS fx_daily (
  date TEXT PRIMARY KEY,
  summary_usdkrw REAL,      -- 해설이 본 숫자. 종가가 아니다 (위 설명 참고)
  summary_eurkrw REAL,
  ai_summary TEXT
)""")
conn.commit()


def at(pair, d):
    """d일(없으면 그 이전 가장 가까운 거래일) 종가와 직전 거래일 대비 증감.

    /api/fx 의 at() 과 같은 계산이다. 화면과 해설이 같은 숫자를 보게 하려면 같아야 한다.
    """
    rows = cur.execute("SELECT rate FROM fx WHERE pair=? AND date<=? ORDER BY date DESC LIMIT 2",
                       (pair, d)).fetchall()
    if not rows:
        return None, None
    if len(rows) < 2:
        return rows[0]["rate"], None
    return rows[0]["rate"], rows[0]["rate"] - rows[1]["rate"]


def direction(chg):
    if chg is None:
        return "데이터 없음"
    if chg > 0.5:
        return "원화 약세(환율 상승)"
    if chg < -0.5:
        return "원화 강세(환율 하락)"
    return "보합"


def build_prompt(iso, usd, usd_chg, eur, eur_chg):
    usd_pct = (usd_chg / (usd - usd_chg) * 100) if usd_chg is not None and (usd - usd_chg) else 0
    eur_txt = (f"원/유로 {eur:.2f}원 (전일 대비 {eur_chg:+.2f}원) — {direction(eur_chg)}"
               if eur is not None and eur_chg is not None else "원/유로 데이터 없음")
    return f"""{iso}의 환율이다.
- 원/달러 {usd:.2f}원 (전일 대비 {usd_chg:+.2f}원, {usd_pct:+.2f}%) — {direction(usd_chg)}
- {eur_txt}

경제 초보자에게 "이날 환율 변동이 우리(한국) 경제에 어떤 영향을 주는지" 설명하라.

반드시 지킬 것:
1) 환율은 한쪽만 좋은 게 아니라 **양면적**이다. 유리한 쪽과 불리한 쪽을 **둘 다** 짚어라.
   - 환율 상승(원화 약세) → 수출기업에 유리 / 수입물가·기름값·해외여행·유학 비용엔 부담
   - 환율 하락(원화 강세) → 수입 부담 완화·물가 안정에 도움 / 수출기업엔 불리
2) **달러를 중심으로** 설명하고, 유로는 보조로 짧게만 언급하라(한국 경제엔 달러 영향이 더 크다).
3) 위에 주어진 숫자만 사용하라. **왜 움직였는지 원인은 추측하지 마라**(뉴스 정보가 없음).

아래 JSON 형식으로만 한국어로 답하라:
{{"ai_summary": "<초보자용 4~6문장. 순서대로 (1) 어느 방향으로 얼마나 움직였는지 (2) 누구에게 유리하고 누구에게 불리한지(양면) (3) 내 생활에 당장 뭐가 달라지는지. 중학생도 이해할 쉬운 말로.>"}}"""


def write_day(iso, label):
    """iso 하루치 해설을 (다시) 생성해 저장. 성공하면 True."""
    usd, usd_chg = at("USDKRW", iso)
    eur, eur_chg = at("EURKRW", iso)
    if usd is None or usd_chg is None:
        print(f"{iso}: 환율 데이터 부족 — 건너뜀")
        return False
    try:
        summary = generate_json(build_prompt(iso, usd, usd_chg, eur, eur_chg))["ai_summary"]
    except Exception as e:
        print(f"{iso}: 실패 ({e.__class__.__name__}) — 다음 실행에서 재시도")
        return False
    # 해설과 '해설이 본 숫자'를 한 번에 쓴다. 둘이 떨어지면 정정 판단을 못 한다.
    cur.execute("INSERT OR REPLACE INTO fx_daily (date, summary_usdkrw, summary_eurkrw, ai_summary) "
                "VALUES (?, ?, ?, ?)", (iso, usd, eur, summary))
    conn.commit()
    print(f"{iso}: {label} — 원/달러 {usd:.2f}({usd_chg:+.2f})")
    return True


def drifted():
    """해설이 본 숫자가 fx 의 현재 종가와 어긋난 날짜들 (최신순).

    ⚠️ fetchall() 로 먼저 받아두는 것이 중요하다. 커서를 순회하는 중에 at() 이
       같은 커서로 execute 하면 바깥 결과 집합이 날아가서 첫 행만 보고 끝난다.
    """
    out = []
    for r in cur.execute("SELECT date, summary_usdkrw FROM fx_daily ORDER BY date DESC").fetchall():
        if r["summary_usdkrw"] is None:
            continue
        truth, _ = at("USDKRW", r["date"])
        if truth is not None and abs(r["summary_usdkrw"] - truth) > DRIFT:
            out.append((r["date"], r["summary_usdkrw"], truth))
    return out


# ───────── 입구 ─────────

args = sys.argv[1:]

if "--backfill" in args:
    i = args.index("--backfill")
    days = int(args[i + 1]) if len(args) > i + 1 else 14
    dates = [r["date"] for r in cur.execute(
        "SELECT DISTINCT date FROM fx WHERE pair='USDKRW' ORDER BY date DESC LIMIT ?", (days,))]
    dates.reverse()  # 오래된 날짜부터
    made = 0
    for iso in dates:
        if cur.execute("SELECT 1 FROM fx_daily WHERE date=?", (iso,)).fetchone():
            continue
        if write_day(iso, "백필"):
            made += 1
    conn.close()
    print(f"환율 해설 백필 완료 (신규 {made}건)")
    raise SystemExit

if "--fix" in args:
    bad = drifted()
    if not bad:
        print("정정할 날짜 없음 — 해설이 본 숫자가 전부 fx 와 일치한다")
    else:
        print(f"정정 대상 {len(bad)}건")
        for iso, had, truth in bad:
            print(f"  {iso}  해설이 본 값 {had:.2f} → 실제 종가 {truth:.2f} ({truth - had:+.2f})")
        fixed = sum(write_day(iso, "정정") for iso, _, _ in bad)
        print(f"환율 해설 정정 완료 ({fixed}/{len(bad)}건)")
    conn.close()
    raise SystemExit

# 기본 실행 — ① 최신 거래일 해설 생성  ② 드리프트 보정 (최대 MAX_FIX_PER_RUN 건)
row = cur.execute("SELECT max(date) d FROM fx WHERE pair='USDKRW'").fetchone()
newest = row["d"] if row else None
if not newest:
    print("환율 데이터 없음 — 먼저 collect_fx 실행 필요")
    conn.close()
    raise SystemExit

if cur.execute("SELECT 1 FROM fx_daily WHERE date=?", (newest,)).fetchone():
    print(f"{newest}: 환율 해설 이미 있음 — 생성 생략")
else:
    write_day(newest, "신규")

# 오늘 쓴 해설은 아직 장중 값일 수 있으니 정정 대상에서 뺀다 (다음 날 보정된다)
bad = [x for x in drifted() if x[0] != newest][:MAX_FIX_PER_RUN]
if not bad:
    print("정정할 지난 날짜 없음")
else:
    for iso, had, truth in bad:
        print(f"정정: {iso}  해설이 본 값 {had:.2f} → 실제 종가 {truth:.2f} ({truth - had:+.2f})")
        write_day(iso, "정정")

conn.close()
