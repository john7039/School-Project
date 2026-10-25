"""이미 저장된 기업별 영향에 최신 정리 규칙을 다시 적용한다 (LLM 없이).

분석을 돌린 뒤에 규칙을 고치는 일이 생긴다 — 대소문자(CAPITAL ONE),
언론사 제외(Usa Today), 이름 통일(Apple→애플) 같은 것들이다. 이런 건
글자 처리라 다시 생성할 필요가 없다. 저장된 JSON 만 다듬으면 된다.

사용법:  .venv/bin/python clean_impacts.py [--apply]
         --apply 없으면 무엇이 바뀌는지 보여주기만 한다.
"""
import json
import sqlite3
import sys

import analyze

apply = "--apply" in sys.argv
conn = sqlite3.connect("econ.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

rows = cur.execute(
    "SELECT url, impacts, sentiment, sentiment_reason FROM article_analysis "
    "WHERE impacts IS NOT NULL AND impacts <> '[]'").fetchall()
print(f"대상 {len(rows)}건" + ("" if apply else "  (미리보기 — 적용하려면 --apply)"))

changed = 0
for r in rows:
    try:
        imp = json.loads(r["impacts"])
    except (ValueError, TypeError):
        continue

    # 저장된 형태를 모델 응답 형태로 되돌려 같은 검증기를 태운다
    data = {
        "direct": [x for x in imp if x.get("kind") != "간접"],
        "indirect": [x for x in imp if x.get("kind") == "간접"],
        "overall": r["sentiment"],
        "overall_reason": r["sentiment_reason"] or "",
    }
    res = analyze._clean_impacts(data)

    before = [(x["company"], x["sentiment"]) for x in imp]
    after = [(x["company"], x["sentiment"]) for x in res["impacts"]]
    if before == after and r["sentiment"] == res["overall"]:
        continue

    changed += 1
    print(f"  {r['url'][:42]}…")
    print(f"     전: {before} · 전체 {r['sentiment']}")
    print(f"     후: {after} · 전체 {res['overall']}")
    if apply:
        cur.execute(
            "UPDATE article_analysis SET impacts=?, sentiment=? WHERE url=?",
            (json.dumps(res["impacts"], ensure_ascii=False), res["overall"],
             r["url"]))

if apply:
    conn.commit()
conn.close()
print(f"{'바꾼' if apply else '바뀔'} 건수: {changed}")
