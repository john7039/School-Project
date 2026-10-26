"""econ.db 를 하루 한 벌 떠 두고, 오래된 것은 지운다.

왜 cp 를 쓰지 않는가 —
  SQLite 는 쓰기를 여러 번에 나눠서 한다. 그 중간에 cp 가 지나가면 반만
  고쳐진 파일이 복사되고, 열 때 'database disk image is malformed' 가 난다.
  파이썬 sqlite3 의 backup() 은 잠금을 제대로 걸고 한 번에 뜬다.
  서버에 sqlite3 명령어가 없기도 하다.

왜 날짜를 파일 이름에 박는가 —
  덮어쓰면 "어제 망가진 DB 를 오늘도 덮어쓰는" 일이 생긴다. 망가진 걸
  알아차리는 데 하루 넘게 걸릴 수 있으므로, 며칠치를 남겨 둬야 돌아갈 곳이 있다.

떠 놓고 끝이 아니라 바로 열어서 확인한다. 뜨는 데 실패하는 것보다
'떴는데 깨진 파일' 이 더 위험하다 — 있다고 믿고 있다가 필요할 때 안 열린다.
"""
import datetime
import os
import sqlite3
import sys

SRC = "/home/miniserver/School-Project/backend/econ.db"
DEST_DIR = "/home/miniserver/backups"
KEEP_DAYS = 7

# 확인용 — 이 테이블들이 비어 있으면 백업이 잘못된 것이다
CHECK_TABLES = ("news", "prices", "article_analysis")


def human(n):
    return f"{n / 1024 / 1024:.1f}MB"


def make_backup(src, dest):
    """SQLite 전용 방식으로 뜬다."""
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(dest)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def verify(path):
    """뜬 파일을 실제로 열어 본다. (깨짐 여부 + 행 수)"""
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise RuntimeError(f"integrity_check 실패: {ok}")
        counts = {}
        for t in CHECK_TABLES:
            n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            if n == 0:
                raise RuntimeError(f"{t} 가 0행 — 백업이 비었다")
            counts[t] = n
        return counts
    finally:
        c.close()


def prune(dest_dir, keep_days):
    """오래된 백업을 지운다. 안 지우면 디스크가 찬다."""
    cutoff = datetime.date.today() - datetime.timedelta(days=keep_days)
    removed = []
    for name in sorted(os.listdir(dest_dir)):
        if not (name.startswith("econ-") and name.endswith(".db")):
            continue
        stamp = name[len("econ-"):-len(".db")]
        try:
            day = datetime.datetime.strptime(stamp, "%Y%m%d").date()
        except ValueError:
            continue            # 이름 형식이 다르면 건드리지 않는다
        if day < cutoff:
            os.remove(os.path.join(dest_dir, name))
            removed.append(name)
    return removed


def main():
    if not os.path.exists(SRC):
        print(f"원본이 없다: {SRC}", file=sys.stderr)
        return 1

    os.makedirs(DEST_DIR, exist_ok=True)
    today = datetime.date.today().strftime("%Y%m%d")
    dest = os.path.join(DEST_DIR, f"econ-{today}.db")

    make_backup(SRC, dest)
    counts = verify(dest)

    size = os.path.getsize(dest)
    rows = " · ".join(f"{t} {n:,}" for t, n in counts.items())
    print(f"백업 완료 {os.path.basename(dest)} — {human(size)} · {rows}")

    removed = prune(DEST_DIR, KEEP_DAYS)
    if removed:
        print(f"  {KEEP_DAYS}일 지난 것 삭제: {', '.join(removed)}")

    kept = [f for f in os.listdir(DEST_DIR)
            if f.startswith("econ-") and f.endswith(".db")]
    total = sum(os.path.getsize(os.path.join(DEST_DIR, f)) for f in kept)
    print(f"  보관 중 {len(kept)}개 · {human(total)}")
    return 0


if __name__ == "__main__":
    # 실패하면 0 이 아닌 값으로 끝낸다. systemd 가 그걸로 성공/실패를 판단한다.
    try:
        sys.exit(main())
    except Exception as e:
        print(f"백업 실패 — {e.__class__.__name__}: {e}", file=sys.stderr)
        sys.exit(1)
