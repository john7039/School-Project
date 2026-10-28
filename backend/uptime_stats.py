"""운영 기록을 숫자로 — 점검 통과율과 문제가 있었던 날.

사용법:
  .venv/bin/python uptime_stats.py          전체 기간
  .venv/bin/python uptime_stats.py 30       최근 30일

무엇을 재는가 —
  health_log 는 하루 한 줄이다. 그래서 이 값은 **아침 점검을 통과한 날의
  비율**이지 초 단위 가동률이 아니다. 발표에서 말할 때도 그렇게 말해야 한다.
  "가동률 99%" 라고 하면 과장이고, "점검 통과 29/30일" 이 정확하다.

기록이 빠진 날도 센다 —
  헬스체크가 아예 안 돈 날은 health_log 에 줄이 없다. 통과도 실패도 아닌
  '모름' 이다. 이걸 통과로 쳐 버리면 숫자가 거짓말을 한다.
"""
import datetime
import sqlite3
import sys

DB = "/home/miniserver/School-Project/backend/econ.db"


def kst_today():
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=9)).date()


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        conn.execute("SELECT 1 FROM health_log LIMIT 1")
    except sqlite3.OperationalError:
        print("health_log 가 아직 없다. 헬스체크가 한 번은 돌아야 한다.")
        return 1

    rows = conn.execute(
        "SELECT date, ok, problems FROM health_log ORDER BY date").fetchall()
    conn.close()
    if not rows:
        print("기록이 없다.")
        return 1

    first = datetime.date.fromisoformat(rows[0][0])
    today = kst_today()
    if days:
        start = max(first, today - datetime.timedelta(days=days - 1))
    else:
        start = first

    kept = {datetime.date.fromisoformat(d): (ok, p) for d, ok, p in rows
            if datetime.date.fromisoformat(d) >= start}

    span = (today - start).days + 1
    passed = sum(1 for ok, _ in kept.values() if ok)
    failed = sum(1 for ok, _ in kept.values() if not ok)
    missing = span - len(kept)

    print(f"점검 기록 — {start} ~ {today} ({span}일)")
    print()
    print(f"  통과      {passed}일")
    print(f"  문제      {failed}일")
    if missing:
        print(f"  기록 없음  {missing}일   ← 헬스체크가 안 돈 날")
    print(f"  ──────────────────")
    print(f"  통과율    {passed}/{span}일  ({passed * 100 / span:.1f}%)")

    bad = [(d, p) for d, (ok, p) in sorted(kept.items()) if not ok]
    if bad:
        print()
        print("문제가 있었던 날")
        for d, p in bad:
            print(f"  {d}  {p or '(내용 없음)'}")

    gaps = [start + datetime.timedelta(days=i) for i in range(span)
            if (start + datetime.timedelta(days=i)) not in kept]
    if gaps:
        print()
        print("기록이 없는 날")
        for d in gaps:
            print(f"  {d}")

    print()
    print("※ 하루 한 번 아침 점검 기준이다. 초 단위 가동률이 아니다.")
    print("   08시와 08시 사이에 잠깐 죽었다 살아난 것은 여기 안 잡힌다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
