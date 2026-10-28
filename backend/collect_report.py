"""아침 수집 배치가 끝난 뒤, 오늘 무엇이 들어왔는지 휴대폰으로 보낸다.

왜 정상일 때도 보내는가 —
  실패 알림(OnFailure)만 있으면 "알림이 안 왔다" 가 두 가지를 뜻한다.
  정상이거나, 알림 자체가 고장났거나. 둘을 구분할 수 없다.
  정상일 때도 보내면 **안 오는 것 자체가 신호**가 된다.

왜 항목마다 기준이 다른가 —
  prices 와 company_daily 는 미국장 데이터라 오늘자가 아직 없는 게 정상이다
  (07:25 시점에 최신이 어제). 여기에 "오늘자 없음" 으로 경보를 울리면 매일
  거짓 경보가 울린다. 그래서 '오늘 있어야 하는 것' 과 '며칠 안에 있으면
  되는 것' 을 나눈다. 거짓 경보를 울리는 감시 장치는 안 울리는 것보다 나쁘다.

보내지 못하면 0 이 아닌 값으로 끝난다. 그러면 econ-collect.service 가
실패하고, 거기 걸린 OnFailure 가 알림 유닛을 부른다.
"""
import datetime
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

DB = "/home/miniserver/School-Project/backend/econ.db"
ENV = "/home/miniserver/School-Project/backend/.env"
STALE_DAYS = 4            # 미국장·환율은 주말·공휴일이 있어 넉넉히 본다
TRACKED = 7               # 추적 종목 수
DB_LIMIT_MB = 70          # 한 달 보관이면 28MB 안팎에서 멈춘다. 넉넉히 잡은 값.
NEWS_FLOOR = 50           # 최근 24시간 기사 수 하한 (평소 수백 건).
                          # 0 만 잡으면 "절반만 깨진" 경우를 놓친다.


def kst_today():
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=9)).date()


def topic():
    if not os.path.exists(ENV):
        return ""
    for line in open(ENV, encoding="utf-8"):
        if line.startswith("NTFY_TOPIC="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def josa(word, with_batchim="이", without="가"):
    """받침 여부로 조사를 고른다. '환율가' 같은 말이 나오지 않게."""
    last = word.strip()[-1]
    if "가" <= last <= "힣":
        return with_batchim if (ord(last) - 0xAC00) % 28 else without
    return without


def days_old(datestr, today):
    """'2026-10-26' 가 며칠 전인지. 못 읽으면 None."""
    try:
        return (today - datetime.date.fromisoformat(datestr)).days
    except (TypeError, ValueError):
        return None


def collect(conn, today):
    """(줄 목록, 문제 목록) 을 만든다."""
    q = lambda sql, *a: conn.execute(sql, a).fetchone()
    lines, bad = [], []

    # ── 오늘 있어야 하는 것 ──
    ymd = today.strftime("%Y%m%d")

    # news.published 는 UTC 이고 수집 시각 열은 따로 없다. KST 날짜와 그대로
    # 대조하면 오전에는 거의 0 으로 나온다(07시 배치 시점에 UTC 로는 전날).
    # 알고 싶은 것은 "신선한 기사가 들어왔는가" 이므로 최근 24시간으로 센다.
    cut = (datetime.datetime.now(datetime.timezone.utc)
           - datetime.timedelta(hours=24)).strftime("%Y%m%dT%H%M%S")
    n_news = q("SELECT COUNT(*) FROM news WHERE published >= ?", cut)[0]
    total_news = q("SELECT COUNT(*) FROM news")[0]
    lines.append(f"기사 · 최근 24시간 {n_news:,}건 (누적 {total_news:,})")
    if n_news == 0:
        bad.append("최근 24시간 기사가 하나도 없다")
    elif n_news < NEWS_FLOOR:
        bad.append(f"기사가 {n_news}건뿐이다 (보통 수백 건, 기준 {NEWS_FLOOR})")

    iso = today.isoformat()
    pick = q("SELECT title, sentiment FROM daily WHERE date=?", iso)
    if pick:
        title = pick[0][:38] + ("…" if len(pick[0]) > 38 else "")
        lines.append(f"오늘 추천 · {title}")
        lines.append(f"  전체 판단 {pick[1] or '-'}")
    else:
        lines.append("오늘 추천 · 없음")
        bad.append("오늘의 추천 기사가 선정되지 않았다")

    n_warm = q("SELECT COUNT(*) FROM search_keyword WHERE day=?", ymd)[0]
    lines.append(f"검색어 예열 · {n_warm}개")

    # DB 크기를 같이 보낸다. 오래된 기사 정리(prune_news.py)가 조용히 멈추면
    # 이 숫자가 계속 커지는 것으로 드러난다. 3주 보관이면 20MB 안팎에서 멈춘다.
    mb = os.path.getsize(DB) / 1024 / 1024
    lines.append(f"DB · {mb:.1f}MB · news {total_news:,}행")
    if mb > DB_LIMIT_MB:
        bad.append(f"DB가 {mb:.0f}MB다 (기준 {DB_LIMIT_MB}MB) — 오래된 기사 정리가 "
                   f"멈췄는지 확인할 것")

    # 점검 통과율 — 숫자를 매일 보지 않으면 쌓여도 모른다.
    # 없으면 조용히 건너뛴다(헬스체크가 아직 한 번도 안 돌았을 수 있다).
    try:
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(ok),0) FROM health_log").fetchone()
        if row and row[0]:
            lines.append(f"점검 통과 · {row[1]}/{row[0]}일")
    except Exception:
        pass

    # ── 며칠 안에 있으면 되는 것 (미국장·환율) ──
    for label, table, want in (("주가", "prices", None),
                               ("종목 분석", "company_daily", TRACKED),
                               ("환율", "fx", None)):
        row = q(f"SELECT MAX(date) FROM {table}")
        latest = row[0] if row else None
        age = days_old(latest, today)
        if age is None:
            lines.append(f"{label} · 기록 없음")
            bad.append(f"{label} 데이터가 아예 없다")
            continue
        cnt = q(f"SELECT COUNT(*) FROM {table} WHERE date=?", latest)[0]
        when = "오늘" if age == 0 else f"{age}일 전"
        lines.append(f"{label} · {latest} ({when}) {cnt}건")
        if age > STALE_DAYS:
            bad.append(f"{label}{josa(label)} {age}일째 갱신되지 않았다 "
                       f"(허용 {STALE_DAYS}일)")
        if want is not None and cnt < want:
            bad.append(f"{label}{josa(label)} {cnt}/{want}개뿐이다")

    return lines, bad


def send(topic_name, title, body, priority, tags):
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic_name}",
        data=body.encode("utf-8"),
        headers={"Title": title.encode("utf-8").decode("latin-1"),
                 "Priority": priority,
                 "Tags": tags})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def main():
    today = kst_today()
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        lines, bad = collect(conn, today)
    finally:
        conn.close()

    head = f"{today.strftime('%Y-%m-%d')} 수집 결과"
    body = head + "\n\n" + "\n".join(lines)
    if bad:
        body += "\n\n문제\n" + "\n".join(f"· {b}" for b in bad)
        title, priority, tags = "수집 이상", "high", "warning"
    else:
        body += "\n\n모두 정상"
        title, priority, tags = "수집 정상", "default", "white_check_mark"

    print(body)                      # journal 에도 남긴다

    t = topic()
    if not t:
        print("NTFY_TOPIC 이 .env 에 없다 — 알림을 보내지 못했다", file=sys.stderr)
        return 1
    try:
        send(t, f"경제 한 조각 · {title}", body, priority, tags)
    except (urllib.error.URLError, OSError) as e:
        print(f"ntfy 전송 실패 — {e.__class__.__name__}: {e}", file=sys.stderr)
        return 1
    print("ntfy 전송 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
