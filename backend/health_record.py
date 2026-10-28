"""헬스체크 결과를 하루 한 줄씩 DB 에 남긴다.

왜 로그가 아니라 DB 인가 —
  로그(journald)는 VM 안에 500MB 까지만 쌓이고 오래된 것부터 버려진다.
  그리고 VM 이 통째로 날아가면 같이 사라진다. 로그를 통째로 백업하기에는
  크고(하루 수십 MB), 정작 나중에 필요한 건 "그날 정상이었나" 한 줄이다.
  econ.db 에 넣으면 하루 수십 바이트이고, 이미 돌고 있는 06:30 백업에
  그대로 실린다. 새로 만들 백업 경로가 없다.

무엇을 재는가 (과장하지 말 것) —
  이 값은 **하루 한 번 아침 점검을 통과한 날의 비율**이다. 초 단위 가동률이
  아니다. 08:00 과 08:00 사이에 잠깐 죽었다 살아난 것은 여기 안 잡힌다.
  그건 OnFailure 알림이 맡는다. 둘은 보는 게 다르다.

호출하는 쪽 —
  healthcheck.sh 가 마지막에 부른다. 여기서 실패해도 헬스체크의 종료 코드는
  바꾸지 않는다. DB 기록이 안 됐다고 "서버에 문제 있음" 알림이 가면 안 된다.
  대신 빠진 날은 uptime_stats.py 가 '기록 없음' 으로 드러낸다.
"""
import datetime
import sqlite3
import sys

DB = "/home/miniserver/School-Project/backend/econ.db"


def kst_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)


def main():
    ok = 0 if (len(sys.argv) > 1 and sys.argv[1] not in ("0", "")) else 1
    problems = sys.argv[2] if len(sys.argv) > 2 else ""

    now = kst_now()
    conn = sqlite3.connect(DB, timeout=20)
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS health_log (
            date       TEXT PRIMARY KEY,   -- KST 달력 날짜
            ok         INTEGER,            -- 1 정상 / 0 문제
            problems   TEXT,               -- 실패 항목, ';' 로 구분
            checked_at TEXT                -- 실제 점검 시각 (KST)
        )""")
        # 같은 날 다시 돌리면 덮어쓴다 — 손으로 재점검한 결과가 최종이 되게.
        conn.execute(
            "INSERT OR REPLACE INTO health_log (date, ok, problems, checked_at) "
            "VALUES (?,?,?,?)",
            (now.strftime("%Y-%m-%d"), ok, problems, now.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally:
        conn.close()

    print(f"  기록: health_log {now.strftime('%Y-%m-%d')} "
          f"{'정상' if ok else '문제'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # 기록 실패가 헬스체크 자체의 실패로 번지면 안 된다.
        print(f"  기록 실패 — {e.__class__.__name__}: {e}", file=sys.stderr)
        sys.exit(0)
