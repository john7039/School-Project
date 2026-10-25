"""수집한 영어 기사 제목을 한국어로 번역해 news.title_ko 에 채운다.

왜 필요한가 — 기사는 Finnhub·Yahoo 에서 받아오므로 제목이 전부 영어다.
사용자는 한국어로 검색하는데, 영어 제목만 있으면 '금리' 를 쳐도 한 건도 안 걸린다.
search_terms 사전이 그 빈틈을 메우지만, 사전에 없는 단어는 여전히 못 찾는다.

중요 — title_ko 는 **검색용이고 화면에 보여주지 않는다.**
로컬 모델(qwen2.5:7b, CPU)의 번역 품질이 들쭉날쭉하다. 실제로 시험해 보니
"Stock Market Sell-Off" 가 "주식 시장 팔리기" 로 나오는 식이다.
그래도 '주식 시장' 이라는 검색어는 걸리므로 검색 재현율은 분명히 올라간다.
화면에는 영어 원제목을 그대로 보여주므로 어색한 번역이 사용자 눈에 띄지 않는다.
이 전제가 깨지면(=화면에 title_ko 를 쓰기 시작하면) 품질 기준을 다시 잡아야 한다.

설계 — 중간에 끊겨도 괜찮게:
  · 한 건 번역할 때마다 바로 커밋한다. 죽어도 거기까지는 남는다.
  · 아직 안 된 것(title_ko IS NULL)만 집어오므로, 다시 실행하면 이어서 한다.
  · 최신 기사부터 한다. 끝까지 못 돌려도 검색에 자주 걸리는 쪽이 먼저 채워진다.

사용법:
  .venv/bin/python translate_titles.py            # 남은 것 전부
  .venv/bin/python translate_titles.py 50         # 50건만
"""
import re
import sqlite3
import sys
import time

from llm import generate_json

DB = "econ.db"

# qwen2.5 는 중국 모델이라 한국어를 시키면 중국어·한자로 새는 일이 있다.
# 수집한 기사에는 한자가 한 글자도 없으므로(3,802건 확인), 번역 결과에
# 한자가 보이면 그건 모델이 샌 것이다. 저장하지 않고 버린다.
CJK = re.compile(r"[一-鿿぀-ヿ]")
# 글자가 깨져 들어오는 경우(예: "이㎞미") 를 걸러내기 위한 허용 문자 집합
ALLOWED = re.compile(r"^[가-힣ㄱ-ㆎ A-Za-z0-9\s"
                     r"&·,./:;%\-–—'\"“”‘’()\[\]+…?!$€£¥\\]*$")

PROMPT = """영어 경제 뉴스 제목을 한국어로 번역하는 일이다.

규칙:
1. 반드시 한국어로만 쓴다. 한자나 중국어를 단 한 글자도 쓰지 마라.
2. 제목 전체를 끝까지 번역한다. 중간에 끊지 마라.
3. 제목에 있는 내용만 옮긴다. 없는 말을 지어내지 마라.
4. 맨 뒤의 출처 표기(- Reuters 등)는 영어 그대로 둔다.
5. 회사·기관 이름은 한국에서 쓰는 이름으로: Tesla→테슬라, Nvidia→엔비디아,
   Apple→애플, Microsoft→마이크로소프트, Amazon→아마존, Google/Alphabet→구글,
   Meta→메타, Fed/Federal Reserve→연준. 티커(AAPL, TSLA)는 그대로 둔다.

예시 1
입력: Tesla Stock Jumps After Q3 Deliveries Beat Estimates
출력: {{"ko": "테슬라 주가, 3분기 인도량이 예상치를 웃돌며 급등"}}

예시 2
입력: Oil Prices Climb as OPEC+ Signals Output Cut - Reuters
출력: {{"ko": "유가 상승, OPEC+ 감산 시사 - Reuters"}}

이제 아래 제목을 번역하라.
입력: {title}
출력:"""


def clean(ko):
    """저장해도 되는 번역이면 그대로, 아니면 None.

    돌려보내는 이유를 같이 알 수 있게 (값, 사유) 로 준다.
    """
    ko = (ko or "").strip()
    if not ko:
        return None, "빈 응답"
    if CJK.search(ko):
        return None, "중국어·한자 섞임"
    if not re.search(r"[가-힣]", ko):
        return None, "한국어가 없음"
    if not ALLOWED.match(ko):
        return None, "깨진 문자 섞임"
    return ko, None


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    sql = ("SELECT id, title FROM news "
           "WHERE title_ko IS NULL AND title IS NOT NULL AND title <> '' "
           "ORDER BY published DESC")
    if limit:
        sql += f" LIMIT {limit}"
    rows = conn.execute(sql).fetchall()

    total = len(rows)
    left = conn.execute(
        "SELECT COUNT(*) FROM news WHERE title_ko IS NULL").fetchone()[0]
    print(f"번역 대상 {total}건 (전체 미번역 {left}건)")
    if not total:
        conn.close()
        return

    done = 0
    rejected = {}
    started = time.time()
    for i, r in enumerate(rows, 1):
        try:
            data = generate_json(PROMPT.format(title=r["title"]), tries=2, timeout=120)
            ko, why = clean(data.get("ko"))
        except Exception as e:
            ko, why = None, e.__class__.__name__

        if ko is None:
            # 저장하지 않고 NULL 로 둔다 → 다음 실행에서 다시 시도한다
            rejected[why] = rejected.get(why, 0) + 1
        else:
            # 한 건마다 바로 저장 — 중간에 끊겨도 여기까지는 남는다
            conn.execute("UPDATE news SET title_ko=? WHERE id=?", (ko, r["id"]))
            conn.commit()
            done += 1

        if i % 25 == 0 or i == total:
            per = (time.time() - started) / i
            eta = per * (total - i) / 60
            print(f"  [{i}/{total}] 저장 {done} · 버림 {sum(rejected.values())} "
                  f"· 건당 {per:.1f}초 · 남은 시간 약 {eta:.0f}분", flush=True)

    conn.close()
    print(f"끝 — {done}건 저장 ({done / total * 100:.0f}%), "
          f"{sum(rejected.values())}건 버림, 총 {(time.time() - started) / 60:.1f}분")
    for why, n in sorted(rejected.items(), key=lambda kv: -kv[1]):
        print(f"   버린 이유 · {why}: {n}건")


if __name__ == "__main__":
    main()
