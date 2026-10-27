"""오래된 뉴스 원문을 지운다. 수집한 지 한 달이 지난 것.

왜 지우는가 —
  news 가 DB 의 74% 를 차지하고 하루 약 1,100건(750KB)씩 늘어난다.
  디스크 자체는 여유가 있지만 **백업이 곱해진다**. VM 에 7벌, 호스트에
  30벌이므로 DB 가 270MB 가 되면 백업만 합쳐서 10GB 다.
  한 달로 묶어 두면 3만 건 남짓, 약 28MB 에서 멈춘다.

무엇을 지우지 않는가 —
  · prices · indicators · fx · fx_daily — 시계열이다. prices 에는 2021년부터
    5년치가 있고 그래프가 그 과거를 쓴다. 건드리면 안 된다.
  · article_analysis · daily — 서비스의 산출물이지 원재료가 아니다.
  · 분석에 쓰인 news 행 — 지워도 화면은 안 깨지지만(analysis 가 제목·출처·
    본문을 자기가 들고 있다) 원문과의 연결을 남겨 두는 편이 낫다.

안전장치 —
  백업은 06:30, 이 스크립트는 07시대에 돈다. 그래서 오늘 지운 것은 아침
  백업에 그대로 들어 있고, VM 에서 7일 · 호스트에서 30일 더 남는다.
  잘못 지웠다는 걸 한 달 안에 알아차리면 되돌릴 수 있다.

VACUUM 은 하지 않는다 —
  지워도 파일이 바로 줄지는 않지만, 빈 자리는 다음 INSERT 가 다시 쓴다.
  매일 지우므로 파일 크기는 3주치에서 멈춘다. VACUUM 은 배타 잠금이 필요해
  백엔드가 DB 를 열고 있는 동안에는 실패하기 쉽고, 얻는 것에 비해 번거롭다.
"""
import datetime
import os
import sqlite3
import sys

DB = "/home/miniserver/School-Project/backend/econ.db"
# 검색의 날짜 사다리 마지막 칸(main.py LADDER)과 짝이다. 여기서 지운 것은
# 사다리로도 닿지 않으므로, 한쪽만 바꾸면 "전체 기간" 이 거짓말이 된다.
#
# 21일로 재 봤더니 '경기침체' 가 후보 8건(MIN_CANDIDATES 와 같음)으로 간신히
# 걸렸다. 하나만 적었어도 마지막 칸으로 내려갔을 것이다. 30일이면 여유가 있고
# 값은 안정 상태 20MB → 28MB, 백업 37벌 합쳐 740MB → 1GB 로 미미하다.
KEEP_DAYS = 30


def main():
    cut = (datetime.datetime.now(datetime.timezone.utc)
           - datetime.timedelta(days=KEEP_DAYS)).strftime("%Y%m%dT%H%M%S")

    conn = sqlite3.connect(DB, timeout=30)
    try:
        q = lambda s, *a: conn.execute(s, a).fetchone()[0]
        before = q("SELECT COUNT(*) FROM news")

        # 분석에 쓰인 기사는 남긴다
        cur = conn.execute(
            """DELETE FROM news
               WHERE published < ?
                 AND url NOT IN (SELECT url FROM article_analysis)
                 AND url NOT IN (SELECT url FROM daily)""", (cut,))
        removed = cur.rowcount
        conn.commit()

        after = q("SELECT COUNT(*) FROM news")
        kept_old = q("SELECT COUNT(*) FROM news WHERE published < ?", cut)
    finally:
        conn.close()

    size = os.path.getsize(DB) / 1024 / 1024
    print(f"오래된 기사 정리 — {KEEP_DAYS}일 이전 {removed:,}건 삭제 "
          f"(분석에 쓰여 남긴 것 {kept_old}건)")
    print(f"  news {before:,} → {after:,}행 · DB {size:.1f}MB")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"정리 실패 — {e.__class__.__name__}: {e}", file=sys.stderr)
        sys.exit(1)
