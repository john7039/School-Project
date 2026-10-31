"""현재 환율이 조용히 멈추지 않았는지 본다.

왜 필요한가 —
  econ-fx-live.service 는 일부러 `ExecStart=-` 로 돌린다. 5분마다 도는 유닛이라
  일시적 네트워크 실패마다 알리면 하루 수백 통이 되기 때문이다.
  그런데 그러면 **정말로 멈췄을 때도 아무도 모른다.**

  2026-10-29 장애 복구 훈련에서 찾은 구멍과 같은 모양이다 — 유닛은 전부 정상인데
  화면의 숫자만 낡아 있는 상태. 유닛 상태로는 절대 안 보인다.

무엇을 보는가 — 시각을 따로 본다

  fetched_at   우리가 받아온 시각     → 수집이 돌고 있나 (타이머가 죽었나)
  market_time  시세 자체의 시각       → 받아온 값이 신선한가
  최신 5분봉    그래프에 그려지는 것   → 그래프가 멈췄나

  방금 받아온 낡은 데이터는 여전히 낡았다. 셋은 서로 다른 질문이다.

알림은 상태가 바뀔 때만 보낸다 — sitecheck.sh 와 같은 방식.
15분마다 울리면 사람이 알림을 무시하기 시작한다. 멈췄을 때 한 번,
돌아왔을 때 한 번.

휴장 중에는 아무것도 하지 않는다. 숫자가 안 바뀌는 것이 정상이고,
상태 파일도 건드리지 않는다 — 그래야 금요일에 멈춘 채 주말을 보내도
월요일에 '복구됨' 이 제대로 나간다.
"""
import datetime
import os
import sqlite3
import sys
import urllib.request

from fxmarket import market_closed

DB = "/home/miniserver/School-Project/backend/econ.db"
ENV_FILE = "/home/miniserver/School-Project/backend/.env"
STATE = "/var/tmp/econ-fxfresh.state"

# 수집은 5분마다 돈다. 20분이면 네 번 연속 실패한 것 — 일시적 장애가 아니다.
STALE_FETCH_MIN = 20
# 시세·봉은 5분 간격이라 30분이면 확실히 멈춘 것. 한두 번 실패에는 안 울린다.
STALE_MARKET_MIN = 30
STALE_BAR_MIN = 30

PAIRS = ("USDKRW", "EURKRW")


def age_min(now, iso):
    """iso 시각이 몇 분 전인지. 못 읽으면 None."""
    if not iso:
        return None
    try:
        return (now - datetime.datetime.fromisoformat(iso)).total_seconds() / 60
    except ValueError:
        return None


def notify(title, body, prio, tags):
    if DRY:
        print("--- [--dry] 보내지 않음 ---")
        print(f"제목: {title}")
        print(body)
        print("---------------------------")
        return True
    topic = ""
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                if line.startswith("NTFY_TOPIC="):
                    topic = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except OSError:
        pass
    if not topic:
        print("NTFY_TOPIC 이 없다 — 알림 못 보냄", file=sys.stderr)
        return False
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}", data=body.encode(),
        headers={"Title": title, "Priority": prio, "Tags": tags})
    try:
        urllib.request.urlopen(req, timeout=15).read()
        return True
    except Exception as e:
        print(f"ntfy 전송 실패: {e.__class__.__name__}", file=sys.stderr)
        return False


DRY = "--dry" in sys.argv       # 전송·상태기록 없이 판정만 본다
now = datetime.datetime.now()
host = os.uname().nodename.split(".")[0]

if market_closed(now) and "--force" not in sys.argv:
    print(f"{now:%Y-%m-%d %H:%M} KST — 외환시장 휴장. 숫자가 안 바뀌는 것이 정상 (상태 유지)")
    raise SystemExit

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

problems = []
try:
    rows = {r["pair"]: r for r in cur.execute("SELECT * FROM fx_live").fetchall()}
except sqlite3.OperationalError:
    rows = {}

if not rows:
    problems.append("fx_live 가 비어 있다 (수집이 한 번도 성공하지 않았다)")

for pair in PAIRS:
    r = rows.get(pair)
    if not r:
        problems.append(f"{pair}: fx_live 에 줄이 없다")
        continue

    a_fetch = age_min(now, r["fetched_at"])
    a_market = age_min(now, r["market_time"])
    bar = cur.execute("SELECT max(ts) FROM fx_intraday WHERE pair=?", (pair,)).fetchone()[0]
    a_bar = age_min(now, bar)

    def fmt(v):
        return "읽을 수 없음" if v is None else f"{v:.0f}분 전"

    print(f"  {pair}  받아온 시각 {fmt(a_fetch)} · 시세 시각 {fmt(a_market)} · 최신 봉 {fmt(a_bar)}")

    if a_fetch is None or a_fetch > STALE_FETCH_MIN:
        problems.append(f"{pair}: 수집이 {fmt(a_fetch)} — 타이머가 멈췄을 수 있다")
    if a_market is None or a_market > STALE_MARKET_MIN:
        problems.append(f"{pair}: 시세가 {fmt(a_market)} — 받아오긴 했는데 값이 낡았다")
    if a_bar is None or a_bar > STALE_BAR_MIN:
        problems.append(f"{pair}: 최신 5분봉이 {fmt(a_bar)} — 그래프가 멈췄다")

conn.close()

prev = "unknown"
try:
    with open(STATE, encoding="utf-8") as f:
        prev = f.read().strip() or "unknown"
except OSError:
    pass
curr = "stale" if problems else "fresh"
if not DRY:
    try:
        with open(STATE, "w", encoding="utf-8") as f:
            f.write(curr)
    except OSError as e:
        print(f"상태 파일을 쓸 수 없다: {e}", file=sys.stderr)

if prev == curr:
    print(f"상태 그대로({curr}) — 알림 없음")
    raise SystemExit

# 첫 실행(또는 상태 파일이 지워진 뒤)에 멀쩡한 것은 알릴 일이 아니다.
# 이걸 막지 않으면 설치하자마자 '복구됨' 이 한 통 온다.
if prev == "unknown" and curr == "fresh":
    print("첫 실행 · 정상 — 상태만 기록하고 알리지 않는다")
    raise SystemExit

stamp = now.strftime("%Y-%m-%d %H:%M:%S")
if curr == "stale":
    ok = notify(
        f"환율 시세가 멈췄다 on {host}",
        stamp + "\n\n" + "\n".join(problems) + f"""

유닛은 정상으로 보일 수 있다 (ExecStart=- 라 실패해도 성공으로 뜬다).

확인: systemctl list-timers econ-fx-live.timer
      journalctl -u econ-fx-live -n 20
      cd ~/School-Project/backend && .venv/bin/python collect_fx_live.py --force""",
        "high", "warning")
else:
    ok = notify(f"환율 시세 복구됨 on {host}",
                stamp + "\n\n받아온 시각·시세 시각·5분봉이 전부 정상 범위로 돌아왔다.",
                "default", "white_check_mark")

print(f"알림 전송{'' if ok else ' 실패'}: {prev} → {curr}")
if problems:
    for p in problems:
        print(f"   {p}")
raise SystemExit(0)
