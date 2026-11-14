"""수집한 영어 기사 제목을 한국어로 번역해 news.title_ko 에 채운다.

왜 필요한가 — 기사는 Finnhub·Yahoo 에서 받아오므로 제목이 전부 영어다.
사용자는 한국어로 검색하는데, 영어 제목만 있으면 '금리' 를 쳐도 한 건도 안 걸린다.
search_terms 사전이 그 빈틈을 메우지만, 사전에 없는 단어는 여전히 못 찾는다.

처음에는 title_ko 를 **검색용으로만** 썼다. 로컬 모델(qwen2.5:7b, CPU)의 번역이
들쭉날쭉해도("Stock Market Sell-Off" → "주식 시장 팔리기") 검색어는 걸리니까.

⚠️ 그 전제는 2026-10-25 에 깨졌다 — AI 추천 기사 카드가 title_ko 를 제목으로
   띄우기 시작했다(11-12 에 홈 화면도). 번역 쪽 기준은 그대로였고, 2026-11-13 에
   "Jensen Huang" 이 37건 중 1건만 '젠슨 황' 이었다. 나머지는 제인슨 홀랜드 ·
   진센 홀란 · 제너슨 화이트하우스… 매번 다르게 지어냈다. 회사도 '네비디아'.
   그래서 **사람·회사 이름은 모델에게 맡기지 않는다** (NAMES 아래 설명).

설계 — 중간에 끊겨도 괜찮게:
  · 한 건 번역할 때마다 바로 커밋한다. 죽어도 거기까지는 남는다.
  · 아직 안 된 것(title_ko IS NULL)만 집어오므로, 다시 실행하면 이어서 한다.
  · 최신 기사부터 한다. 끝까지 못 돌려도 검색에 자주 걸리는 쪽이 먼저 채워진다.

사용법:
  .venv/bin/python translate_titles.py            # 남은 것 전부
  .venv/bin/python translate_titles.py 50         # 50건만
"""
import datetime
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

# 이름은 모델에게 맡기지 않는다 — 번역 **전에** 코드가 한글로 바꿔 넣고,
# 번역 **후에** 그 한글이 그대로 남았는지 확인한다. 빠졌으면 저장하지 않는다
# (NULL 로 두면 화면은 영어 원제를 보여준다. 틀린 이름보다 영어가 낫다).
#
# 프롬프트에 "Nvidia→엔비디아" 를 적어뒀는데도 '네비디아' 가 나왔다.
# 프롬프트는 부탁이고 코드가 보장이다 — 채팅(chat.py)과 같은 원칙.
#
# 넣는 기준: 2026-11-13 기사 제목에서 실제로 센 횟수. 성(姓)만 바꾸는 것은
# 다른 단어와 안 겹치는 것만 — "Jobs"(고용지표) · "Su"(319건, Surge 등) ·
# "Cook" · "Wood" · "Lee" · "Son" 은 성만으로는 넣지 않는다.
NAMES = {
    # 사람 — 전체 이름
    "Elon Musk": "일론 머스크", "Jensen Huang": "젠슨 황", "Jim Cramer": "짐 크레이머",
    "Warren Buffett": "워런 버핏", "Cathie Wood": "캐시 우드", "Tim Cook": "팀 쿡",
    "Steve Jobs": "스티브 잡스", "Mark Zuckerberg": "마크 저커버그",
    "Satya Nadella": "사티아 나델라", "Lisa Su": "리사 수", "Sam Altman": "샘 올트먼",
    "Jamie Dimon": "제이미 다이먼", "Tom Lee": "톰 리", "Michael Burry": "마이클 버리",
    "Bill Ackman": "빌 애크먼", "Sundar Pichai": "순다르 피차이", "Andy Jassy": "앤디 재시",
    "Jeff Bezos": "제프 베이조스", "Bill Gates": "빌 게이츠", "Ken Griffin": "켄 그리핀",
    "Dan Ives": "댄 아이브스", "Jerome Powell": "제롬 파월", "Donald Trump": "도널드 트럼프",
    "Scott Bessent": "스콧 베센트", "Kevin Warsh": "케빈 워시", "Kevin Hassett": "케빈 해싯",
    "Masayoshi Son": "손정의", "Larry Fink": "래리 핑크", "Ray Dalio": "레이 달리오",
    # 사람 — 성만 (위 전체 이름이 먼저 바뀐 뒤에 남은 것만 걸린다)
    "Musk": "머스크", "Huang": "황", "Cramer": "크레이머", "Buffett": "버핏",
    "Zuckerberg": "저커버그", "Nadella": "나델라", "Powell": "파월", "Trump": "트럼프",
    "Bessent": "베센트", "Ackman": "애크먼", "Burry": "버리", "Bezos": "베이조스",
    "Pichai": "피차이", "Jassy": "재시", "Altman": "올트먼", "Dimon": "다이먼",
    # 회사·기관 — 원래 프롬프트 5번 규칙에 있던 것
    "Nvidia": "엔비디아", "NVIDIA": "엔비디아", "Tesla": "테슬라", "Apple": "애플",
    "Microsoft": "마이크로소프트", "Amazon": "아마존", "Alphabet": "구글", "Google": "구글",
    "Meta Platforms": "메타", "Meta": "메타", "Federal Reserve": "연준", "Fed": "연준",
    "Broadcom": "브로드컴", "Intel": "인텔", "Samsung": "삼성",
}
# 긴 것부터 — "Elon Musk" 가 "Musk" 보다 먼저 바뀌어야 '일론 머스크' 가 된다.
_NAME_RE = re.compile(r"\b(%s)\b(?:['’]s\b)?" % "|".join(
    re.escape(k) for k in sorted(NAMES, key=len, reverse=True)))


def pin_names(title):
    """제목 속 이름을 한글로 바꾼 제목과, 결과에 남아 있어야 할 한글 이름들.

    "Nvidia's" 의 's 는 같이 떼어 '엔비디아의' 로 바꾼다. 그냥 두면 모델이
    '엔비디아's' 를 그대로 옮기거나, 거기서 이름을 다시 쓰려 든다.
    """
    must = []

    def sub(m):
        ko = NAMES[m.group(1)]
        must.append(ko)
        return ko + ("의" if m.group(0) != m.group(1) else "")
    return _NAME_RE.sub(sub, title), sorted(set(must))


PROMPT = """영어 경제 뉴스 제목을 한국어로 번역하는 일이다.

규칙:
1. 반드시 한국어로만 쓴다. 한자나 중국어를 단 한 글자도 쓰지 마라.
2. 제목 전체를 끝까지 번역한다. 중간에 끊지 마라.
3. 제목에 있는 내용만 옮긴다. 없는 말을 지어내지 마라.
4. 맨 뒤의 출처 표기(- Reuters 등)는 영어 그대로 둔다.
5. **제목에 이미 한글로 적힌 이름은 한 글자도 바꾸지 말고 그대로 쓴다.**
   (예: '젠슨 황' 은 '젠슨 황' 그대로.) 티커(AAPL, TSLA)도 그대로 둔다.
6. 한글로 안 바뀌어 있는 사람 이름은 영어 그대로 둔다. 한글로 옮기지 마라.

예시 1
입력: 테슬라 Stock Jumps as 일론 머스크 Unveils Robotaxi
출력: {{"ko": "일론 머스크가 로보택시 공개하자 테슬라 주가 급등"}}

예시 2
입력: Oil Prices Climb as OPEC+ Signals Output Cut - Reuters
출력: {{"ko": "유가 상승, OPEC+ 감산 시사 - Reuters"}}

이제 아래 제목을 번역하라. 위 예시처럼 JSON 으로만 답한다.
입력: {title}
출력:"""

# ⚠️ 위 "JSON" 이라는 단어를 지우지 마라. Groq 는 JSON 모드로 부를 때 프롬프트에
#    'json' 이 한 번도 없으면 400 을 돌려준다. 2026-11-13 까지 이 프롬프트에 그 단어가
#    없어서 **번역은 단 한 건도 Groq 를 거치지 못했다** — 매번 400 → llm.py 가 설정
#    오류로 보고 Groq 를 15분 끔 → 전부 로컬 qwen 7B 가 번역했다.
#    지금은 일부러 로컬을 먼저 쓴다(아래 main). 이 단어는 로컬이 죽었을 때
#    Groq 로 넘어가는 길을 위해 남긴다.


def clean(ko, must=()):
    """저장해도 되는 번역이면 그대로, 아니면 None.

    돌려보내는 이유를 같이 알 수 있게 (값, 사유) 로 준다.
    must — pin_names 가 넣은 한글 이름. 하나라도 빠졌으면 모델이 이름을
    다시 쓴 것이다.
    """
    ko = (ko or "").strip()
    if not ko:
        return None, "빈 응답"
    if any(n not in ko for n in must):
        return None, "이름이 바뀜"
    if CJK.search(ko):
        return None, "중국어·한자 섞임"
    if not re.search(r"[가-힣]", ko):
        return None, "한국어가 없음"
    if not ALLOWED.match(ko):
        return None, "깨진 문자 섞임"
    return ko, None


def recheck(conn):
    """이미 저장된 번역에 이름 검사를 다시 댄다. 걸리면 NULL 로 되돌린다.

    **오늘 것만** 본다 — 오늘 수집한 기사와 오늘의 추천 카드. 2026-11-13 처음엔
    전체에 댔다가(19,266건 중 320건) 지난 기사까지 다시 번역할 필요는 없다고 봐서
    좁혔다. 화면에 나가는 건 오늘 카드이고, 지난 기사 번역은 검색용이다.

    article_analysis(추천 기사 카드)는 뽑힐 때 news.title_ko 를 복사해 간다.
    그래서 여기도 같이 비운다. 비어 있으면 화면은 영어 원제를 보여주고,
    news 쪽이 다시 번역되면 sync_cards 가 채운다.
    """
    kst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()
    where = {
        "news": ("published >= ?", kst.strftime("%Y%m%d")),
        "article_analysis": ("url IN (SELECT url FROM daily WHERE date = ?)", kst.isoformat()),
    }
    n = {}
    for table, (cond, arg) in where.items():
        bad = [(rid,) for rid, t, k in conn.execute(
                   f"SELECT rowid, title, title_ko FROM {table} "
                   f"WHERE title_ko IS NOT NULL AND {cond}", (arg,))
               if not clean(k, pin_names(t or "")[1])[0]]
        conn.executemany(f"UPDATE {table} SET title_ko=NULL WHERE rowid=?", bad)
        n[table] = len(bad)
    conn.commit()
    return n


def sync_cards(conn):
    """추천 기사 카드의 빈 제목을 news 의 (검사를 통과한) 번역으로 채운다."""
    cur = conn.execute(
        "UPDATE article_analysis SET title_ko = (SELECT n.title_ko FROM news n "
        "  WHERE n.url = article_analysis.url AND n.title_ko IS NOT NULL) "
        "WHERE title_ko IS NULL AND EXISTS (SELECT 1 FROM news n "
        "  WHERE n.url = article_analysis.url AND n.title_ko IS NOT NULL)")
    conn.commit()
    return cur.rowcount


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    undone = recheck(conn)
    if any(undone.values()):
        print(f"이름 검사로 되돌림 — 기사 {undone['news']}건 · 추천 카드 "
              f"{undone['article_analysis']}건 (다시 번역한다)")
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
        sync_cards(conn)
        conn.close()
        return

    done = 0
    rejected = {}
    started = time.time()
    for i, r in enumerate(rows, 1):
        try:
            pinned, must = pin_names(r["title"])
            # 로컬 먼저. Groq 하루 한도는 화면에 나가는 기사 분석 몫이다.
            # 2026-11-14: Groq 로 번역 200건을 보냈더니 47분이 걸렸고(분당 한도
            # 대기), 하루 토큰을 다 써서 기사 분석 16건 중 7건이 로컬로 밀렸다.
            # 이름은 pin_names 가 미리 한글로 박아두므로 로컬도 이름을 못 바꾼다.
            data = generate_json(PROMPT.format(title=pinned), tries=2, timeout=120,
                                 prefer_local=True)
            ko, why = clean(data.get("ko"), must)
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

    synced = sync_cards(conn)
    if synced:
        print(f"추천 카드 제목 {synced}건 채움")
    conn.close()
    print(f"끝 — {done}건 저장 ({done / total * 100:.0f}%), "
          f"{sum(rejected.values())}건 버림, 총 {(time.time() - started) / 60:.1f}분")
    for why, n in sorted(rejected.items(), key=lambda kv: -kv[1]):
        print(f"   버린 이유 · {why}: {n}건")


if __name__ == "__main__":
    main()
