"""기사 한 건을 고르고 분석하는 일을 모아둔 곳.

매일 자동으로 도는 큐레이션과, 사용자가 단어로 검색했을 때 도는 분석이
같은 일을 한다. 같은 프롬프트를 두 벌 두면 한쪽만 고치는 사고가 나므로
여기로 모은다. 입구가 둘이어도 결과는 한 모양이다.

단계는 셋이고, 한 번에 다 시키지 않는 이유가 각각 있다:
  pick    — 후보 중 1건 고르기. 번호만 받으면 모델이 기사를 지어낼 수 없다.
  explain — 고른 그 기사 하나만 주고 설명 생성. 제목과 설명이 어긋나지 않는다.
  impacts — 어느 기업이 왜 긍정/부정인지. 설명과 섞으면 감정이 뭉개진다.
"""
import json
import re

from llm import generate_json

# 우리가 주가를 가지고 있는 종목 — 간접 영향은 이 안에서만 고른다
TRACKED = {
    "AAPL": "애플", "MSFT": "마이크로소프트", "NVDA": "엔비디아",
    "AMZN": "아마존", "GOOGL": "구글", "TSLA": "테슬라", "META": "메타",
}

VALID_SENT = ("긍정", "부정", "중립")

# 간접 영향에서 걸러낼 말버릇.
# 실제로 이런 항목이 나왔다 —
#   "기사 내용은 애플과 직접적인 관련이 없으나, 전반적으로 ..."  (중립)
# 관련이 없다고 말하면서 항목을 채우고 있다. 억지로 짜낸 판단이고,
# 이런 게 섞이면 제대로 된 판단까지 같이 못 믿게 된다.
FILLER = ("관련이 없", "관련은 없", "직접적인 영향은 없", "언급되지 않", "명시되지 않")


# 기업이 아닌 것들. "기업별 영향" 인데 실제로 이런 게 들어왔다 —
#   [직접] 석유 시장  부정
# 시장·업계 이름은 기업이 아니므로 뺀다. 그 내용은 전체 방향(overall)이
# 이미 말하고 있다.
# 계속 새로운 게 나와서 넓게 잡았다. "석유 시장", "경기" 가 실제로 들어왔다.
NOT_COMPANY = (
    # 덩어리를 가리키는 말
    "시장", "업계", "산업", "섹터", "부문", "분야", "전반", "전체",
    # 경제 개념
    "경제", "경기", "금융", "증시", "주가", "물가", "환율", "금리", "유가",
    "인플레이션", "실적", "무역", "수출", "수입",
    # 사람·기관
    "기업", "기업들", "회사", "회사들", "투자자", "투자자들", "소비자",
    "소비자들", "정부", "중앙은행", "연준", "당국",
    # 언론사. 기사를 쓴 쪽이지 영향을 받는 기업이 아닌데 들어왔다
    # ("Usa Today 중립").
    "USA Today", "Usa Today", "로이터", "Reuters", "블룸버그", "Bloomberg",
    "CNBC", "월스트리트저널", "WSJ", "파이낸셜타임스", "연합뉴스", "뉴시스",
    "조선일보", "중앙일보", "한국경제", "매일경제", "이데일리", "전자신문",
    "Yahoo", "Yahoo Finance", "Benzinga", "Zacks", "Motley Fool",
    # 모델이 "해당 기업 없음" 을 회사 이름 칸에 써 넣은 경우.
    # 실제로 '환율' 분석에서 "없음 · 중립" 이라는 항목이 만들어졌다.
    "없음", "해당 없음", "해당없음", "없다", "N/A", "n/a", "미상", "알 수 없음",
)

# "애플(AAPL)" 처럼 이름에 티커를 덧붙여 오는 경우. 티커는 별도 필드라
# 그대로 두면 화면에 "애플(AAPL) AAPL" 로 두 번 나온다.
TICKER_IN_NAME = re.compile(r"\s*\(\s*([A-Z]{1,5})\s*\)\s*$")


def _title_case(name):
    """영문 회사명을 보기 좋게. "CAPITAL ONE" -> "Capital One".

    모델이 전부 대문자로 뱉는 일이 잦다. 다만 원래 대문자인 약어
    (TSMC, IBM, AMD)와 대소문자가 섞인 고유 표기(SpaceX, iPhone)는
    건드리지 않는다. 그래서 '두 글자를 넘는 전부 대문자 단어' 만 손본다.
    """
    if not re.search(r"[A-Za-z]", name):
        return name                      # 한글 이름은 그대로

    words = name.split()
    # 약어 판정은 '한 단어짜리 짧은 전부 대문자' 일 때만. 여러 단어로 된
    # 이름에 적용하면 "CAPITAL ONE" 의 ONE 이 약어로 오인돼 그대로 남는다.
    if len(words) == 1 and len(words[0]) <= 4 and words[0].isupper():
        return name                      # IBM, AMD, TSMC
    return " ".join(w.capitalize() if w.isupper() else w for w in words)


def _clean_company(name):
    """기업 이름을 다듬고, 이름에 섞인 티커를 떼어낸다.

    돌려주는 값은 (이름, 이름에서 떼어낸 티커 또는 ""). 기업이 아니면
    이름 자리에 None 을 준다.
    """
    name = (name or "").strip()
    if not name:
        return None, ""
    m = TICKER_IN_NAME.search(name)
    found = ""
    if m:
        found = m.group(1)
        name = TICKER_IN_NAME.sub("", name).strip()
    if not name:
        return None, ""
    if name in NOT_COMPANY or any(name.endswith(w) for w in NOT_COMPANY):
        return None, ""
    return _title_case(name), found


# 영어로 들어온 추적 종목을 한국어 이름으로 맞춘다.
ALIAS = {
    "apple": "애플", "microsoft": "마이크로소프트", "nvidia": "엔비디아",
    "amazon": "아마존", "google": "구글", "alphabet": "구글",
    "tesla": "테슬라", "meta": "메타", "facebook": "메타",
}


def _canon(name, ticker):
    """같은 회사가 'Apple' 과 '애플' 로 갈리지 않게 한국어 이름으로 모은다."""
    if ticker in TRACKED:
        return TRACKED[ticker]
    return ALIAS.get((name or "").strip().lower(), name)


# qwen2.5 는 중국 모델이라 한국어로 답하라고 해도 중국어·한자로 새는 일이 있다.
# 실제로 겪었다 — "Tesla가 2026年第3季度的财报显示..." 처럼 요약 한가운데가
# 통째로 중국어로 나왔다. 프롬프트로 금지하는 것만으로는 안 막히므로,
# 결과를 받아 보고 한자가 보이면 다시 시킨다.
CJK = re.compile(r"[一-鿿぀-ヿ]")

# 지시는 프롬프트 맨 앞에 둔다. 뒤에 붙였더니 모델이 덜 따랐고, 재시도가
# 걸려서 분석 한 건이 63초에서 112초로 늘었다.
NO_CJK = ("[가장 중요한 규칙] 반드시 한국어로만 답하라. "
          "한자나 중국어를 단 한 글자도 쓰지 마라. "
          "숫자와 티커(TSLA 등)는 그대로 써도 된다.\n\n")


def _has_cjk(obj):
    """dict/list/str 어디에든 한자·가나가 섞여 있으면 True."""
    if isinstance(obj, str):
        return bool(CJK.search(obj))
    if isinstance(obj, dict):
        return any(_has_cjk(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_cjk(v) for v in obj)
    return False


def _gen_korean(prompt, tries=3):
    """한자가 섞이지 않은 응답이 나올 때까지 다시 시킨다."""
    last = None
    for _ in range(tries):
        last = generate_json(prompt)
        if not _has_cjk(last):
            return last
    return last


# ──────────────────────────────────────────────────────────────
# 1단계 — 고르기
# ──────────────────────────────────────────────────────────────

def pick(rows, topic=None):
    """후보 기사 중 1건의 인덱스를 고른다.

    고르는 기준이 세 가지인 이유 —
      ① 키워드와 관련: 당연한 조건.
      ② 초보자가 학습하기 좋을 것: 이 서비스의 목적.
      ③ **기업 영향을 말할 수 있을 것**: 이게 없어서 사고가 났다.
         '환율' 로 남아공 물가 기사를, '금리' 로 가족 기금 부동산 기사를
         골랐고, 그 결과 기업별 영향이 빈 채로 나왔다. 이 탭의 목적이
         "기사가 기업에 미치는 영향" 이라면 고르는 단계에서 그 조건을
         봐야 한다. 나중에 억지로 기업을 짜내면 근거 없는 판단이 붙어
         오히려 나빠진다.
    """
    cand = "\n".join(
        f"[{i}] {r['title']}  (관련 종목 태그: {r['tickers'] or '없음'})"
        for i, r in enumerate(rows))

    if topic:
        goal = (f'사용자가 "{topic}" 에 대해 알고 싶어 한다. '
                f'아래 후보 중 "{topic}" 와 실제로 관련이 깊은 기사 중에서 고른다.')
    else:
        goal = '지금 경제가 어떻게 돌아가고 있는지를 보여주는 기사 중에서 고른다.'

    prompt = f"""아래는 오늘 수집한 경제 뉴스 후보들이다(번호순).
{goal}

**고르는 기준 세 가지를 모두 만족하는 기사 1건**을 골라라:

① 주제가 맞을 것
② 경제 초보자가 공부하기 좋을 것
   - 지금 실제로 벌어지고 있는 일을 다룰 것
   - 배경지식 없이도 따라갈 수 있을 것
③ **어느 기업이 어떤 영향을 받는지 말할 수 있을 것** ← 가장 중요
   - 기사에 기업이 등장하거나
   - 다음 종목과 연결 지어 설명할 수 있는 내용일 것:
     애플, 마이크로소프트, 엔비디아, 아마존, 구글, 테슬라, 메타

아래는 **절대 고르지 마라**:
- 스포츠·연예·생활·취미·가십
- 시점과 무관한 조언성 기사 ("~하는 법", "~해야 하는 이유", "초보자가 흔히 하는 실수")
- 어느 기업과도 연결할 수 없는 기사 (③ 위반)

아래 JSON 형식으로만 답하라:
{{"chosen_index": <번호(정수)>, "why": "<세 기준을 어떻게 만족하는지 한 문장>"}}

후보:
{cand}"""

    sel = generate_json(prompt)
    idx = int(sel.get("chosen_index", 0))
    if idx < 0 or idx >= len(rows):
        idx = 0
    return idx


# ──────────────────────────────────────────────────────────────
# 2단계 — 쉬운 설명
# ──────────────────────────────────────────────────────────────

def explain(title, summary):
    """고른 기사 하나를 초보자용으로 풀어 설명한다."""
    prompt = f"""아래 기사를 경제 초보자용으로 설명하라. 핵심은 "지금 무슨 일이 벌어지고 있고, 그게 경제에 어떤 영향을 주는지".
제목: {title}
요약: {(summary or title)[:400]}

중요: **위 제목·요약에 실제로 있는 내용만으로 설명하라.** 본문에 없는 원인·배경·숨은 의미를 추측하거나 지어내지 말 것. 정보가 부족하면 제목이 말하는 사실만 담백하게 설명하라.

아래 JSON 형식으로만 한국어로 답하라:
{{
  "pick_reason": "<이 기사가 공부하기 좋은 이유 1-2문장. 반드시 이 기사 내용에 대해서만>",
  "brief": "<무슨 일이 있었는지 1~2문장으로. 중학생이 읽어도 알아들을 말로>",
  "summary_easy": "<경제를 전혀 모르는 사람도 이해하도록 쉽고 자세하게. 반드시 이 순서로: (1) 무슨 일이 일어났는지, (2) 그 일이 경제·시장에 어떤 영향을 주는지, (3) 그래서 왜 중요한지. 어려운 용어는 일상 비유로 바로 풀어서. 5~7문장. 반드시 위 '제목'의 사건에 대해서만 쓸 것.>",
  "glossary": [{{"term": "<용어>", "desc": "<초보자용 설명>"}}]
}}
glossary 는 기사에 나오는 어려운 경제 용어 2-4개."""
    return _gen_korean(NO_CJK + prompt)


# ──────────────────────────────────────────────────────────────
# 3단계 — 기업별 영향
# ──────────────────────────────────────────────────────────────

def impacts(title, summary, hint_tickers=""):
    """어느 기업이 이 기사로 어떤 영향을 받는지, 이유와 함께 뽑는다.

    예전에는 기사 하나에 감정 하나만 붙이고, 기업은 뉴스 제공처가 달아준
    태그를 그대로 복사했다. 그래서 '비트코인 기사에 NVDA, 긍정' 같은 짝이
    나왔다 — 그 긍정이 어느 기업 얘긴지 아무 데도 없었다.

    둘로 나누는 이유:
      직접 — 기사에 실제로 나오는 기업. 근거가 기사 안에 있다.
      간접 — 우리가 추적하는 종목에 미칠 영향. 기사에는 없고 우리가
             추론한 것이므로, 화면에도 "AI 추정" 이라고 밝혀서 보여준다.
    섞어 놓으면 사용자가 둘을 구분할 수 없고, 추론을 사실로 읽게 된다.
    """
    tracked = ", ".join(f"{n}({t})" for t, n in TRACKED.items())
    hint = f"\n이 기사에 달린 종목 태그: {hint_tickers} (참고만 할 것. 기사 내용과 상관없으면 무시하라)" if hint_tickers else ""

    prompt = f"""아래 경제 뉴스가 **개별 기업**에 어떤 영향을 주는지 판단하라.

제목: {title}
요약: {(summary or title)[:400]}{hint}

우리가 주가를 추적하는 종목: {tracked}

**두 가지로 나눠서 답하라.**

[직접] 기사에 실제로 등장하거나 명백히 다뤄지는 기업
  - 기사 내용에 근거해서 판단한다. 최소 1개, 최대 3개.
  - **반드시 개별 회사 이름을 쓸 것.** "석유 시장", "반도체 업계" 처럼
    시장·업계·산업 이름은 기업이 아니므로 쓰지 마라.
  - company 에는 회사 이름만 쓰고, 티커는 ticker 에만 쓴다.
    "애플(AAPL)" 처럼 이름 안에 티커를 넣지 마라.

[간접] 위 추적 종목 중, 이 기사가 영향을 줄 만한 기업
  - 기사에 직접 안 나와도 된다. 대신 **왜 연결되는지 고리를 설명**해야 한다.
    예: "반도체 수요 둔화 → 데이터센터 투자 축소 → 엔비디아 매출 감소"
  - 설명할 고리가 없으면 넣지 마라. 0개여도 된다. 최대 2개.
  - 직접에 이미 쓴 기업은 넣지 마라.
  - **"직접적인 관련이 없으나" 같은 말로 시작하지 마라.** 관련이 없으면 그냥 빼라.
  - **간접은 중립을 쓰지 마라.** 방향이 분명한 것만 넣는다.

**방향 판단 규칙** (중립을 남발하지 말 것):
  부정 — 주가·실적 하락, 수요 감소, 비용·금리 상승, 규제·소송, 경쟁 심화
  긍정 — 주가·실적 상승, 수요 증가, 비용·금리 하락, 규제 완화, 점유율 확대
  중립 — **호재와 악재가 비슷하게 섞였을 때만.** 판단이 어렵다는 이유로
         중립을 쓰지 마라. 조금이라도 기울면 그쪽으로 판단하라.

**근거 규칙**: 각 기업마다 **왜 그 방향인지** 1~2문장으로 써라.
"긍정입니다" 처럼 방향만 있고 이유가 없는 답은 쓰지 마라.

아래 JSON 형식으로만 한국어로 답하라:
{{
  "direct": [
    {{"company": "<기업 이름(한국어)>", "ticker": "<추적 종목이면 티커, 아니면 빈 문자열>",
      "sentiment": "<긍정|부정|중립>", "reason": "<기사 내용에 근거해 왜 그런지 1~2문장>"}}
  ],
  "indirect": [
    {{"company": "<추적 종목 이름(한국어)>", "ticker": "<티커>",
      "sentiment": "<긍정|부정|중립>", "reason": "<어떤 고리로 연결되는지 1~2문장>"}}
  ],
  "overall": "<긍정|부정|중립>",
  "overall_reason": "<위 판단들과 어긋나지 않게, 시장 전체로는 어느 쪽인지 1문장>"
}}"""

    data = _gen_korean(NO_CJK + prompt)
    return _clean_impacts(data)


def _clean_impacts(data):
    """모델 응답에서 쓸 수 있는 것만 남긴다.

    근거 없는 판정은 버린다 — 비어 있는 편이 틀린 것보다 낫다.
    간접은 추적 종목에 한정한다. 모델이 지어낸 티커도 버린다.
    """
    out = []
    seen = set()

    for kind, key, only_tracked in (("직접", "direct", False),
                                    ("간접", "indirect", True)):
        # 개수 제한은 **거르고 난 뒤**에 센다. 먼저 잘라 버리면
        # 쓸모없는 항목이 자리를 차지하고 멀쩡한 항목이 밀려난다.
        limit = 3 if kind == "직접" else 2
        kept = 0
        for it in (data.get(key) or []):
            if kept >= limit:
                break
            company, from_name = _clean_company(it.get("company"))
            sent = (it.get("sentiment") or "").strip()
            reason = (it.get("reason") or "").strip()
            if not company or sent not in VALID_SENT or len(reason) < 10:
                continue

            ticker = (it.get("ticker") or "").strip().upper() or from_name
            if ticker and ticker not in TRACKED:
                ticker = ""
            if only_tracked and not ticker:
                continue          # 간접은 추적 종목만

            if kind == "간접":
                # 간접은 "이 기사가 저 회사에 영향을 준다"는 주장이다.
                # 중립이면 할 말이 없다는 뜻이므로 넣지 않는다.
                if sent == "중립":
                    continue
                if any(f in reason for f in FILLER):
                    continue

            company = _canon(company, ticker)
            dedup = ticker or company
            if dedup in seen:
                continue          # 직접에 이미 나온 기업을 간접에 또 쓰지 않게
            seen.add(dedup)

            out.append({"kind": kind, "company": company, "ticker": ticker,
                        "sentiment": sent, "reason": reason})
            kept += 1

    # 전체 방향은 기업별 판정과 어긋나면 안 된다.
    # 실제로 '금리' 분석에서 기업별은 엔비디아 부정 하나뿐인데 전체가 중립으로
    # 나왔다. 이유 문장은 "부정적" 이라고 쓰면서. 중립이 형식상 유효한 값이라
    # 그냥 통과했던 것 — 기업별이 한쪽으로만 기울면 전체도 그쪽으로 맞춘다.
    # 기사의 주인공은 '직접' 쪽이다. 직접이 하나라도 있으면 그쪽으로 전체를
    # 정한다. 실제로 "삼성, 인도 1위 탈환" 기사에서 직접은 삼성 긍정 하나인데
    # 간접(애플 부정)과 동점이 되어 전체가 '부정' 으로 나왔다. 1위를 되찾은
    # 기사가 부정으로 표시되면 읽는 사람이 먼저 이상하게 느낀다.
    direct = [x["sentiment"] for x in out if x["kind"] == "직접"]
    votes = direct or [x["sentiment"] for x in out]
    pos, neg = votes.count("긍정"), votes.count("부정")
    inferred = "긍정" if pos > neg else "부정" if neg > pos else "중립"

    # 카드에는 앞의 3개만 보인다. "애플 중립" 처럼 방향이 없는 항목이
    # 자리를 차지하면 정작 볼 만한 긍정·부정이 밀린다. 방향이 분명한 것을
    # 앞에 세우되, 직접이 간접보다 먼저인 순서는 지킨다.
    # 방향이 먼저, 그 다음이 직접/간접. 카드 3칸에 "애플 중립" 이 들어가면
    # 아무것도 못 알려주지만, 간접이라도 "구글 긍정" 은 알려주는 게 있다.
    # 모달에서는 어차피 직접·간접을 나눠서 보여주므로 순서가 섞여도 된다.
    out.sort(key=lambda x: (x["sentiment"] == "중립", x["kind"] == "간접"))

    overall = (data.get("overall") or "").strip()
    if overall not in VALID_SENT:
        overall = inferred
    elif out and overall != inferred and inferred != "중립":
        overall = inferred

    return {
        "impacts": out,
        "overall": overall,
        "overall_reason": (data.get("overall_reason") or "").strip(),
    }


# ──────────────────────────────────────────────────────────────
# 묶어서 쓰기
# ──────────────────────────────────────────────────────────────

def full(title, summary, hint_tickers=""):
    """설명 + 기업별 영향을 한 번에. 실패한 쪽은 비워서 돌려준다."""
    try:
        exp = explain(title, summary)
    except Exception:
        exp = {}
    try:
        imp = impacts(title, summary, hint_tickers)
    except Exception:
        imp = {"impacts": [], "overall": "중립", "overall_reason": ""}

    return {
        "pick_reason": exp.get("pick_reason", ""),
        "brief": exp.get("brief", ""),
        "summary_easy": exp.get("summary_easy", ""),
        "glossary": exp.get("glossary", []) or [],
        "impacts": imp["impacts"],
        "sentiment": imp["overall"],
        "sentiment_reason": imp["overall_reason"],
    }
