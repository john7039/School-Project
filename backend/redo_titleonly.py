"""본문 없이 제목만으로 분석됐던 기사를 새 규칙으로 다시 분석한다.

'아우디가 한국에 투자' 처럼 제목에 없는 사실이 섞여 있을 수 있는 행들이다.
중단해도 이미 끝난 것은 남는다 — 한 건씩 바로 저장한다.
"""
import json, sqlite3, time
import analyze, llm

conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
try:
    conn.execute("ALTER TABLE article_analysis ADD COLUMN title_only INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
conn.commit()

rows = conn.execute("""SELECT a.url, a.title, n.summary, n.tickers
                       FROM article_analysis a JOIN news n ON n.url = a.url
                       WHERE (n.summary = '' OR n.summary IS NULL)""").fetchall()
print(f"다시 분석할 기사 {len(rows)}건\n")

for i, r in enumerate(rows, 1):
    print(f"[{i}/{len(rows)}] {r['title'][:60]}")
    t0 = time.time()
    try:
        res = analyze.full(r["title"], r["summary"], r["tickers"] or "")
    except Exception as e:
        print(f"    실패: {e.__class__.__name__}: {e}\n")
        continue
    conn.execute(
        "UPDATE article_analysis SET pick_reason=?, brief=?, summary_easy=?, "
        "glossary=?, impacts=?, sentiment=?, sentiment_reason=?, title_only=1, "
        "created=datetime('now') WHERE url=?",
        (res["pick_reason"], res["brief"], res["summary_easy"],
         json.dumps(res["glossary"], ensure_ascii=False),
         json.dumps(res["impacts"], ensure_ascii=False),
         res["sentiment"], res["sentiment_reason"], r["url"]))
    # daily 쪽 옛 컬럼도 같이 (화면이 COALESCE 로 받치고 있으므로)
    conn.execute("UPDATE daily SET brief=?, summary_easy=?, glossary=?, "
                 "pick_reason=?, sentiment=? WHERE url=?",
                 (res["brief"], res["summary_easy"],
                  json.dumps(res["glossary"], ensure_ascii=False),
                  res["pick_reason"], res["sentiment"], r["url"]))
    conn.commit()
    print(f"    {time.time()-t0:.0f}초 · {llm.last_provider} · {res['summary_easy'][:70]}…\n")

conn.close()
print("끝")
