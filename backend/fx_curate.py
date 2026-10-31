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
  python fx_curate.py --dry 2026-10-30  그날 프롬프트만 찍어 본다 (호출·저장 없음)
  python fx_curate.py --redo 2026-10-30 그 하루만 조건 없이 다시 쓴다
"""
import re
import sqlite3
import sys

from fxmarket import session_bounds
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
  ai_summary TEXT,
  summary_final INTEGER DEFAULT 0   -- 1 이면 장이 닫힌 뒤 쓴 것
)""")
# 이미 있는 DB 에 칸을 더한다
for col, decl in (("summary_final", "INTEGER DEFAULT 0"),):
    try:
        cur.execute(f"ALTER TABLE fx_daily ADD COLUMN {col} {decl}")
    except sqlite3.OperationalError:
        pass            # 이미 있다
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


def intraday_stats(pair, d):
    """d 세션(09:00~다음날 02:00) 5분봉에서 시작·고·저를 뽑는다. 봉이 없으면 None.

    화면 그래프(/api/fx)와 **같은 창**을 봐야 한다. 창이 다르면 해설의 고·저가
    그래프의 고·저와 다른 숫자가 된다 — 숫자가 두 곳에 생기는 그 문제다.
    그래서 세션 계산은 fxmarket 한 곳에만 둔다.
    """
    lo, hi = session_bounds(d)
    rows = cur.execute("SELECT rate FROM fx_intraday WHERE pair=? AND ts>=? AND ts<? ORDER BY ts",
                       (pair, lo, hi)).fetchall()
    if len(rows) < 3:
        return None
    v = [r["rate"] for r in rows]
    return {"open": v[0], "high": max(v), "low": min(v), "last": v[-1], "n": len(v)}


def day_shape(op, hi, lo, close):
    """하루 모양을 코드가 판정한다.

    모델에게 맡기지 않는 이유 — 7주차에 겪은 그대로다. 숫자 판단을 모델에
    넘기면 자기가 쓴 틀린 글도 통과시킨다. 모양은 코드가 정하고, 모델은
    그 문장을 쉽게 풀어 쓰는 일만 한다.
    """
    rng = hi - lo
    if rng < 0.05:
        return "하루 내내 거의 움직이지 않았다"
    net = (close - op) / rng      # 시작 대비 순이동이 변동폭의 몇 할인가
    pos = (close - lo) / rng      # 끝값이 저가(0)와 고가(1) 사이 어디인가
    if abs(net) < 0.25:
        return "오르내리며 출렁인 끝에 시작과 비슷한 자리로 돌아왔다"
    if net > 0 and pos > 0.7:
        return "장중 대체로 오르며 높은 쪽에서 끝났다"
    if net < 0 and pos < 0.3:
        return "장중 대체로 내리며 낮은 쪽에서 끝났다"
    if net > 0:
        return "올랐지만 고점에서는 밀린 채 끝났다"
    return "내렸지만 저점에서는 되돌린 채 끝났다"


def direction(chg):
    if chg is None:
        return "데이터 없음"
    if chg > 0.5:
        return "원화 약세(환율 상승)"
    if chg < -0.5:
        return "원화 강세(환율 하락)"
    return "보합"


def build_prompt(iso, usd, usd_chg, eur, eur_chg, day=None):
    usd_pct = (usd_chg / (usd - usd_chg) * 100) if usd_chg is not None and (usd - usd_chg) else 0
    eur_txt = (f"원/유로 {eur:.2f}원 (전일 대비 {eur_chg:+.2f}원) — {direction(eur_chg)}"
               if eur is not None and eur_chg is not None else "원/유로 데이터 없음")

    # 하루 안의 움직임. 5분봉이 있는 날만 들어간다 (2026-10-31 부터 모으기 시작).
    # 모양 판정은 코드가 끝낸 뒤 문장으로 넘긴다 — 모델은 다시 판단하지 않는다.
    inside = ""
    if day:
        # ⚠️ '끝값'은 일봉 종가(usd) 하나만 쓴다.
        #    5분봉 마지막 값(day["last"])은 다른 계열이라 일봉 종가와 미세하게
        #    다르다(실측 1334.03 vs 1334.20). 둘을 같이 보내면 해설에 화면과
        #    다른 숫자가 박힌다 — 오늘 아침에 고친 그 문제와 같은 종류다.
        #    5분봉에서는 시작·고·저만 가져온다.
        hi = max(day["high"], usd)   # 종가가 봉 범위를 벗어날 수 있어 맞춰 넓힌다
        lo = min(day["low"], usd)
        span = hi - lo
        span_pct = (span / day["open"] * 100) if day["open"] else 0
        inside = (f"""
- 하루 안의 움직임 (5분봉 {day['n']}개)
  09:00 개장 {day['open']:.2f}원 → 끝 {usd:.2f}원
  가장 높았을 때 {hi:.2f}원 / 가장 낮았을 때 {lo:.2f}원
  변동폭 {span:.2f}원 ({span_pct:.2f}%)
  하루 모양: {day_shape(day['open'], hi, lo, usd)}""")

    return f"""{iso}의 환율이다.
- 원/달러 {usd:.2f}원 (전일 대비 {usd_chg:+.2f}원, {usd_pct:+.2f}%) — {direction(usd_chg)}
- {eur_txt}{inside}

경제 초보자에게 "이날 환율이 어떻게 움직였고, 그것이 우리(한국) 경제에 어떤 영향을 주는지" 설명하라.

반드시 지킬 것:
1) 환율은 한쪽만 좋은 게 아니라 **양면적**이다. 유리한 쪽과 불리한 쪽을 **둘 다** 짚어라.
   - 환율 상승(원화 약세) → 수출기업에 유리 / 수입물가·기름값·해외여행·유학 비용엔 부담
   - 환율 하락(원화 강세) → 수입 부담 완화·물가 안정에 도움 / 수출기업엔 불리
2) **달러를 중심으로** 설명하고, 유로는 보조로 짧게만 언급하라(한국 경제엔 달러 영향이 더 크다).
3) 위에 주어진 숫자만 사용하라. **왜 움직였는지 원인은 추측하지 마라**(뉴스 정보가 없음).
4) '하루 모양'이 주어졌으면 그 판정을 **그대로 따르라.** 네가 다시 판단하거나
   뒤집지 마라. 거기에 숫자를 곁들여 쉬운 말로 풀어 쓰는 것이 네 일이다.
   변동폭이 0.3% 미만이면 "크게 움직이지 않았다"고 말해도 된다.
5) **움직인 것은 '환율'이다. '원화'가 아니다.**
   환율이 오르면 원화 약세, 환율이 내리면 원화 강세다 — 방향이 반대다.
   "원화가 내려갔다 / 올라갔다" 처럼 쓰지 마라. 헷갈리고, 실제로 한 글 안에서
   "원화가 내려갔다"와 "원화는 강세였다"를 같이 쓴 적이 있다.
   오른 것도 내린 것도 **환율**이라고 쓰고, 원화는 **강세/약세**로만 말하라.

아래 JSON 형식으로만 한국어로 답하라:
{{"ai_summary": "<초보자용 4~6문장. 순서대로 (1) 하루 안에서 어떻게 움직였는지(시작·고·저·끝과 모양) (2) 누구에게 유리하고 누구에게 불리한지(양면) (3) 내 생활에 당장 뭐가 달라지는지. 중학생도 이해할 쉬운 말로.>"}}"""


def wrong_direction(text, chg):
    """환율 방향과 어긋나는 표현을 찾는다. 문제가 있으면 이유를, 없으면 None.

    실제로 나온 사고 (2026-10-31) — 환율이 6.14원 내린(원화 강세) 날에
    모델이 "원화는 하루 내내 내려갔습니다" 라고 썼다. 환율이 내린 것과
    원화가 약해진 것을 뒤섞은 것이고, 같은 글 뒤쪽에는 "원화는 강세를
    보였습니다" 라고 써서 앞뒤가 맞지 않았다.

    모델에게 다시 판단하게 하지 않고 코드가 글자를 본다 — 7주차 원칙 그대로.
    """
    if chg is None:
        return None
    # '원화' 뒤 10자 안에 방향 동사가 오는 경우만 본다. 그 사이에 강세/약세가
    # 끼어 있으면 ("원화가 강세를 보이면 물가가 내려...") 다른 문장이므로 넘긴다.
    for m in re.finditer(r"원화[가는이은]?(.{0,10}?)(하락|내려|떨어|상승|올라|올랐)", text):
        gap, verb = m.group(1), m.group(2)
        if "강세" in gap or "약세" in gap:
            continue
        down = verb in ("하락", "내려", "떨어")
        if chg < -0.5 and down:
            return f"환율이 내렸는데(원화 강세) '원화…{verb}'라고 썼다"
        if chg > 0.5 and not down:
            return f"환율이 올랐는데(원화 약세) '원화…{verb}'라고 썼다"
    return None


def write_day(iso, label, final=0):
    """iso 하루치 해설을 (다시) 생성해 저장. 성공하면 True.

    final=1 은 '장이 닫힌 뒤에 쓴 것'이라는 표시다. 15:40 에 쓰는 해설은
    그날이 아직 진행 중이라(환율은 다음날 06:00 마감) 고·저가 미완성이고,
    다음 날 완성된 봉으로 다시 쓴다.
    """
    usd, usd_chg = at("USDKRW", iso)
    eur, eur_chg = at("EURKRW", iso)
    if usd is None or usd_chg is None:
        print(f"{iso}: 환율 데이터 부족 — 건너뜀")
        return False
    day = intraday_stats("USDKRW", iso)
    prompt = build_prompt(iso, usd, usd_chg, eur, eur_chg, day)

    # 한 번 더 기회를 주되 무한정은 아니다. 두 번째도 어긋나면 그냥 저장한다 —
    # 문장이 조금 어색한 것보다 해설이 아예 없는 것이 나쁘다.
    summary = None
    for attempt in (1, 2):
        try:
            # prefer_local — 이 스크립트는 15:40 배치라 아무도 기다리지 않는다.
            # 로컬(qwen2.5:7b)로 30초 걸리는데, 그만큼 Groq 분당 한도를 사용자
            # 검색(/api/news/pick)에 남겨둘 수 있다. 로컬이 죽어 있으면 Groq 로 간다.
            cand = generate_json(prompt, prefer_local=True)["ai_summary"]
        except Exception as e:
            print(f"{iso}: 실패 ({e.__class__.__name__}) — 다음 실행에서 재시도")
            return False
        why = wrong_direction(cand, usd_chg)
        summary = cand
        if not why:
            break
        print(f"   방향 표현 어긋남 — {why}")
        if attempt == 1:
            print("   다시 생성한다")
            prompt += ("\n\n※ 직전 답이 틀렸다: " + why +
                       ". 움직인 것은 환율이고, 원화는 강세/약세로만 말하라.")
        else:
            print("   두 번째도 어긋남 — 그대로 저장한다")
    # 해설과 '해설이 본 숫자'를 한 번에 쓴다. 둘이 떨어지면 정정 판단을 못 한다.
    cur.execute("INSERT OR REPLACE INTO fx_daily "
                "(date, summary_usdkrw, summary_eurkrw, ai_summary, summary_final) "
                "VALUES (?, ?, ?, ?, ?)", (iso, usd, eur, summary, final))
    conn.commit()
    shape = (f" · {day_shape(day['open'], max(day['high'], usd), min(day['low'], usd), usd)}"
             if day else " · 5분봉 없음")
    print(f"{iso}: {label} — 원/달러 {usd:.2f}({usd_chg:+.2f}){shape}")
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

if "--dry" in args:
    # 모델에 뭘 보내는지 눈으로 확인한다. 호출도 저장도 하지 않는다.
    i = args.index("--dry")
    iso = args[i + 1] if len(args) > i + 1 else None
    if not iso:
        row = cur.execute("SELECT max(date) d FROM fx WHERE pair='USDKRW'").fetchone()
        iso = row["d"]
    usd, usd_chg = at("USDKRW", iso)
    eur, eur_chg = at("EURKRW", iso)
    if usd is None:
        print(f"{iso}: 환율 데이터 없음")
        raise SystemExit
    day = intraday_stats("USDKRW", iso)
    print(f"--- {iso} 프롬프트 (5분봉 {day['n'] if day else 0}개) ---")
    print(build_prompt(iso, usd, usd_chg, eur, eur_chg, day))
    conn.close()
    raise SystemExit

if "--redo" in args:
    i = args.index("--redo")
    if len(args) <= i + 1:
        print("날짜를 주어야 한다 — 예: --redo 2026-10-30")
        raise SystemExit(1)
    write_day(args[i + 1], "다시 씀", final=1)
    conn.close()
    raise SystemExit

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
        if write_day(iso, "백필", final=1):
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
        fixed = sum(write_day(iso, "정정", final=1) for iso, _, _ in bad)
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

# ⓐ 장이 닫힌 지난 날 중 아직 '진행 중'으로 쓰인 해설을 완성한다.
#    newest 보다 앞선 날짜는 이미 마감된 날이므로 5분봉이 다 모여 있다.
pending = [r["date"] for r in cur.execute(
    "SELECT date FROM fx_daily WHERE COALESCE(summary_final,0)=0 AND date<? "
    "ORDER BY date DESC LIMIT ?", (newest, MAX_FIX_PER_RUN)).fetchall()]
for iso in pending:
    write_day(iso, "하루 마감 후 다시 씀", final=1)
if not pending:
    print("완성할 지난 해설 없음")

# ⓑ 최신 거래일 해설 (아직 진행 중이므로 final=0)
if cur.execute("SELECT 1 FROM fx_daily WHERE date=?", (newest,)).fetchone():
    print(f"{newest}: 환율 해설 이미 있음 — 생성 생략")
else:
    write_day(newest, "신규(진행 중)", final=0)

# 오늘 쓴 해설은 아직 장중 값일 수 있으니 정정 대상에서 뺀다 (다음 날 보정된다)
bad = [x for x in drifted() if x[0] != newest][:MAX_FIX_PER_RUN]
if not bad:
    print("정정할 지난 날짜 없음")
else:
    for iso, had, truth in bad:
        print(f"정정: {iso}  해설이 본 값 {had:.2f} → 실제 종가 {truth:.2f} ({truth - had:+.2f})")
        write_day(iso, "정정")

conn.close()
