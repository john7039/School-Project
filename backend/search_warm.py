"""자주 쓸 검색어의 AI 분석을 미리 계산해 둔다.

검색어 하나를 분석하는 데 1분쯤 걸린다 — 고르기 11초, 설명 32초,
기업별 영향 20초. 로컬 모델을 CPU 로 돌리는 값이라 줄일 수가 없다.
그래서 화면에서 바로 누를 수 있는 단어들은 미리 돌려서 캐시에 넣어 둔다.
사용자가 그 단어를 누르면 기다림 없이 결과가 뜬다.

캐시에 없는 단어를 검색하면 화면이 "분석하기(1분쯤)" 버튼을 보여주고,
사용자가 누를 때만 그 자리에서 분석한다.

사용법:
  .venv/bin/python search_warm.py              # 기본 목록 전부
  .venv/bin/python search_warm.py 금리 환율      # 지정한 단어만
  .venv/bin/python search_warm.py --redo 금리    # 이미 있어도 다시
"""
import sqlite3
import sys
import time

import main

# 화면의 추천 칩과 같은 순서로 둔다 — 시연에서 제일 먼저 눌릴 단어들
DEFAULT = [
    "금리", "물가", "테슬라", "반도체", "환율", "실적",
    "연준", "주가", "고용", "유가", "인공지능", "관세",
    "애플", "엔비디아", "달러", "경기침체",
]


def main_():
    args = [a for a in sys.argv[1:] if a != "--redo"]
    redo = "--redo" in sys.argv
    words = args or DEFAULT

    conn = sqlite3.connect("econ.db")
    conn.row_factory = sqlite3.Row
    main._ensure_tables(conn)
    day0 = main._latest_day(conn)
    have = {r[0] for r in conn.execute(
        "SELECT keyword FROM search_keyword WHERE day=?", (day0,))}
    conn.close()

    todo = words if redo else [w for w in words if w not in have]
    print(f"대상 {len(todo)}건 (이미 있는 것 {len(words) - len(todo)}건 건너뜀)")
    if not todo:
        return

    ok = skipped = failed = 0
    started = time.time()
    for i, w in enumerate(todo, 1):
        t0 = time.time()
        try:
            r = main.pick_article(q=w, force=True, redo=redo)
            # 서버가 백그라운드로 돌리므로 화면과 똑같이 상태를 물어보며 기다린다
            while r["status"] == "working":
                time.sleep(3)
                r = main.pick_article(q=w)
        except Exception as e:
            print(f"  [{i}/{len(todo)}] {w} — 실패 ({e.__class__.__name__}: {e})")
            failed += 1
            continue

        took = time.time() - t0
        if r["status"] != "ready":
            print(f"  [{i}/{len(todo)}] {w} — {r['status']} "
                  f"{r.get('message', '')}")
            skipped += 1
            continue

        ok += 1
        imp = r.get("impacts") or []
        names = " · ".join(f"{x['company']}{'(추정)' if x['kind'] == '간접' else ''}"
                           f" {x['sentiment']}" for x in imp) or "없음"
        print(f"  [{i}/{len(todo)}] {w} — {took:.0f}초 · {r.get('range')} "
              f"{r.get('candidates')}건 · 전체 {r['sentiment']}", flush=True)
        print(f"        {(r['title'] or '')[:76]}", flush=True)
        print(f"        🏢 {names}", flush=True)

    print(f"끝 — 저장 {ok} · 기사없음 {skipped} · 실패 {failed} "
          f"(총 {(time.time() - started) / 60:.1f}분)")


if __name__ == "__main__":
    main_()
