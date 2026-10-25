"""지난 추천 기사들을 새 규칙으로 다시 분석한다.

왜 — daily 46건은 기업별 영향을 만든 적이 없다. 옛 구조에서는 기사 하나에
감정 하나만 붙이고 기업은 뉴스 제공처 태그를 그대로 복사했다. 그래서 지금
화면에서 "검색한 기사에는 기업 뱃지가 뜨는데 지난 기록에는 안 뜨는" 상태다.

고르는 건 다시 하지 않는다. 그날 고른 기사는 그대로 두고 분석만 새로 한다.

중간에 끊겨도 괜찮게 —
  · 한 건마다 바로 저장한다.
  · 이미 기업별 영향이 들어 있는 기사는 건너뛴다. 다시 실행하면 이어서 한다.
  · 최신 날짜부터 한다. 끝까지 못 돌려도 화면 위쪽부터 채워진다.

사용법:
  .venv/bin/python redo_daily.py          # 남은 것 전부
  .venv/bin/python redo_daily.py 5        # 5건만
"""
import json
import sqlite3
import sys
import time

import analyze

conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

rows = cur.execute("""
    SELECT d.date, d.url, d.tickers,
           COALESCE(n.title, d.title)   AS title,
           n.summary,
           COALESCE(n.source, d.source) AS source,
           n.published, n.title_ko,
           a.impacts
    FROM daily d
    LEFT JOIN news n             ON n.url = d.url
    LEFT JOIN article_analysis a ON a.url = d.url
    WHERE d.url IS NOT NULL AND d.url <> ''
    ORDER BY d.date DESC""").fetchall()

todo = [r for r in rows if not (r["impacts"] or "").strip("[] \n")]
remaining = len(todo)
if limit:
    todo = todo[:limit]

print(f"daily {len(rows)}건 · 기업영향 없는 것 {remaining}건 "
      f"· 이번에 처리 {len(todo)}건")
if not todo:
    print("더 할 일 없음")
    conn.close()
    raise SystemExit

ok = failed = 0
started = time.time()
for i, r in enumerate(todo, 1):
    t0 = time.time()
    try:
        res = analyze.full(r["title"], r["summary"], r["tickers"] or "")
    except Exception as e:
        print(f"  [{i}/{len(todo)}] {r['date']} 실패 ({e.__class__.__name__})", flush=True)
        failed += 1
        continue

    if not res["summary_easy"]:
        print(f"  [{i}/{len(todo)}] {r['date']} 설명 생성 실패 — 다음 실행에서 재시도",
              flush=True)
        failed += 1
        continue

    cur.execute(
        "INSERT OR REPLACE INTO article_analysis "
        "(url, title, title_ko, source, published, pick_reason, brief, "
        " summary_easy, glossary, impacts, sentiment, sentiment_reason, created) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
        (r["url"], r["title"], r["title_ko"], r["source"], r["published"],
         res["pick_reason"], res["brief"], res["summary_easy"],
         json.dumps(res["glossary"], ensure_ascii=False),
         json.dumps(res["impacts"], ensure_ascii=False),
         res["sentiment"], res["sentiment_reason"]))
    conn.commit()          # 한 건마다 저장 — 끊겨도 여기까지는 남는다
    ok += 1

    names = " · ".join(
        f"{x['company']}{'(추정)' if x['kind'] == '간접' else ''} {x['sentiment']}"
        for x in res["impacts"]) or "없음"
    done = time.time() - started
    eta = (done / i) * (len(todo) - i) / 60
    print(f"  [{i}/{len(todo)}] {r['date']} — {time.time() - t0:.0f}초 "
          f"· 전체 {res['sentiment']} · 남은 시간 약 {eta:.0f}분", flush=True)
    print(f"        🏢 {names}", flush=True)

conn.close()
print(f"끝 — {ok}건 완료, {failed}건 실패 (총 {(time.time() - started) / 60:.1f}분)")
