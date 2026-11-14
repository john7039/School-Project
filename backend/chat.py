"""채팅 — 우리 DB 에 있는 것만 근거로 답한다.

왜 자유 대화가 아닌가 —
  이 프로젝트는 "근거 없으면 말 안 한다" 로 일관해 왔다. 업종 판단에 AI 를
  안 썼고, 경제지표에 해설을 안 붙였고, 연준 2% 목표선을 안 그었다. 채팅만
  아무거나 답하면 그 원칙이 한 번에 깨진다.
  그리고 발표에서 "그냥 ChatGPT 붙인 거 아니냐" 가 반드시 나온다. 우리가
  모은 자료를 보고 답한다는 게 그 답이다.

구조 — 새로 짜는 건 근거 고르기(`chat_context`) 하나뿐이다.
  질문 → chat_context.build() → 프롬프트 → llm.generate_json()
  안 걸리면 **LLM 을 아예 안 부른다**(공개 사이트라 호출을 아껴야 한다).

⚠️ 숫자를 계산시키지 않는다. 근거에 "+0.71%p" 까지 적어서 넘긴다.
   LLM 이 하는 일은 그걸 문장으로 엮는 것뿐이다.
"""

import re

import chat_context
import llm

# 대화를 몇 턴까지 들고 갈 것인가.
# Groq 무료는 분당 8,000토큰이 먼저 걸린다. 턴이 쌓이면 토큰이 선형으로 늘어서
# 금방 막힌다. 근거는 매번 새로 뽑으므로 맥락은 "무엇을 묻던 중인지" 만 있으면 된다.
HISTORY_TURNS = 3
HISTORY_CHARS = 300          # 한 턴당 자르는 길이
MAX_QUESTION = 300           # 긴 지시문을 밀어 넣지 못하게

PROMPT = """너는 '경제 한 조각' 사이트의 도우미다. 아래 [자료] 에 있는 것만 근거로 답한다.

규칙
- 자료에 없는 것은 "그건 저희가 가진 자료에 없습니다" 라고 말한다. 추측하지 않는다.
- 앞으로 어떻게 될지는 답하지 않는다. 이 사이트는 예측을 하지 않는다.
  물어보면 "예측은 하지 않습니다" 라고 말하고, 대신 지금까지의 흐름을 알려준다.
- 사야 하는지 팔아야 하는지는 답하지 않는다. 투자 조언이 아니다.
- **숫자는 자료에 적힌 것을 그대로 쓴다. 직접 계산하지 않는다.**
- 기사는 **보도된 내용**이지 확인된 사실이 아니다. "~라고 보도됐어요",
  "~라는 의혹이 제기됐어요" 처럼 전한다. 단정하지 않는다.
  언제·어느 매체인지 같이 적는다.
- 2~3문장으로 짧게. 숫자를 쓸 때는 언제 기준인지 같이 적는다.
- 경제를 처음 보는 사람에게 말하듯 쉬운 말로.

[자료]
{context}
{history}
[질문] {question}

아래 JSON 으로만 답한다.
{{"answer": "2~3문장", "used": ["근거로 쓴 자료 이름", ...]}}"""


# ⚠️ 프롬프트에 "예측하지 않는다" 를 적어도 작은 모델은 흘린다.
#   2026-11-11 실측 — 같은 프롬프트로 "내년에 금리 오를까?" 를 물었더니
#     Groq  "예측은 하지 않습니다. 현재 ..."                      ✓
#     로컬  "...내년에도 금리가 오를 가능성이 있습니다"             ✗
#   규칙이 여럿이면 7B 는 흘린다. **그래서 코드가 먼저 잡는다** — 이 프로젝트가
#   늘 하던 방식이다(업종 판단도 AI 가 아니라 계산이 한다).
_FUTURE = ["내년", "앞으로", "전망", "향후", "오를까", "내릴까", "될까",
           "오를까요", "예상", "예측", "어떻게 될", "괜찮을까", "계속될"]
_ADVICE = ["사야", "팔아야", "살까", "팔까", "투자해", "추천해", "담을까", "매수", "매도"]

_WARN_FUTURE = (
    "\n⚠️ 이 질문은 **앞으로 어떻게 될지**를 묻고 있다.\n"
    "   답은 반드시 \"예측은 하지 않습니다\" 로 시작한다.\n"
    "   그 뒤에는 자료에 있는 **지금까지의 흐름만** 쓴다.\n"
    "   '가능성이 있다' · '~할 것으로 보인다' 같은 말을 한 글자도 쓰지 마라.\n")
_WARN_ADVICE = (
    "\n⚠️ 이 질문은 **사라/팔라**를 묻고 있다.\n"
    "   답은 반드시 \"투자 판단은 도와드리지 않습니다\" 로 시작한다.\n"
    "   그 뒤에는 자료에 있는 수치만 알려준다.\n")


# ⚠️ 경고문을 넣어도 작은 모델은 **끝에서** 샌다.
#   2026-11-11 실측 — 로컬이 "예측은 하지 않습니다" 로 시작해놓고
#   마지막 문장에 "앞으로도 계속될 가능성이 높습니다" 를 붙였다.
#   프롬프트로 부탁했으면 코드로 보장한다.
_LEAK = ["가능성이 높", "가능성이 있", "것으로 보", "것으로 예상", "전망",
         "예상됩니다", "예상돼", "오를 것", "내릴 것", "계속될", "될 것",
         "이어질 것", "상승할", "하락할", "예측하"]


def _drop_forecast(answer):
    """예측을 묻는 질문의 답에서 **미래를 말하는 문장만** 버린다.

    통째로 버리지 않는 이유 — 앞부분("예측은 하지 않습니다 + 지금까지의 흐름")은
    맞는 답이다. 문장 단위로 걸러야 쓸 수 있는 답이 남는다.
    """
    sents = [t for t in re.split(r"(?<=[.!?다])\s+", answer) if t.strip()]
    kept = [t for t in sents if not any(k in t for k in _LEAK)]
    if not kept:
        return ""
    return " ".join(kept)


# 근거에는 "+0.71%p" 로 넣었는데 LLM 이 "0.71 percentage point" 로 풀어 쓴다.
# 2026-11-13 시연 질문 "한·미 금리 차이는?" 에서 실제로 나왔다.
# 단위는 근거에 적힌 그대로 돌려놓는다.
_PP = re.compile(r"\s*(?:percentage|percent)\s*points?|\s*퍼센트\s*포인트",
                 re.IGNORECASE)


def _fix_units(answer):
    return _PP.sub("%p", answer)


def _guard(q):
    w = ""
    if any(k in q for k in _ADVICE):
        w += _WARN_ADVICE
    if any(k in q for k in _FUTURE):
        w += _WARN_FUTURE
    return w


def _clean(t):
    return re.sub(r"\s+", " ", (t or "")).strip()


def _history_block(history):
    """최근 몇 턴만. 길면 자른다."""
    if not history:
        return ""
    turns = [h for h in history if h.get("q") or h.get("a")][-HISTORY_TURNS:]
    if not turns:
        return ""
    lines = ["", "[앞서 나눈 이야기]"]
    for h in turns:
        if h.get("q"):
            lines.append("  사용자: " + _clean(h["q"])[:HISTORY_CHARS])
        if h.get("a"):
            lines.append("  도우미: " + _clean(h["a"])[:HISTORY_CHARS])
    return "\n".join(lines) + "\n"


# 사전에 안 걸렸을 때 보여줄 것. ⚠️ 여기서 끝낸다 — LLM 을 부르지 않는다.
EXAMPLES = ["요즘 물가 어때?", "한·미 금리 차이는?", "지금 환율 얼마야?",
            "오늘 기사 뭐 있어?", "엔비디아 어때?"]

MISS_ANSWER = (
    "그건 제가 가진 자료에서 못 찾았어요. 저는 이 사이트가 모아둔 것만 보거든요 "
    "— 물가·금리·실업률·수출입, 환율, 기사 2만여 건, 저장된 종목입니다.\n\n"
    # ⚠️ "없다" 로 끝내지 않는다. **받아오는 자리는 따로 있다.**
    #    기사 검색 탭은 처음 보는 단어도 그 자리에서 구글 뉴스에서 받아와
    #    분석한다. 채팅이 그걸 하면 느려지고(최대 15초) 남용 통로가 된다.
    "찾으시는 게 새 소식이라면 **지난 기사 탭**에서 그 단어로 검색해 보세요. "
    "거기서는 없는 단어도 그 자리에서 받아와 분석합니다.")


def probe(conn, question):
    """근거만 먼저 뽑는다. SQLite 만 읽으니 밀리초다.

    엔드포인트가 이걸 먼저 불러 **안 걸리는 질문을 즉시 돌려보낸다** —
    작업을 띄우고 폴링하게 만들 이유가 없다.
    """
    return chat_context.build(conn, _clean(question)[:MAX_QUESTION])


def ask(conn, question, history=None, prefer_local=False, ctx=None):
    """질문 하나에 답한다.

    돌려주는 것
      status   ok | miss | error
      answer   답 문장
      sources  무엇을 봤는지 (화면에 작게 붙인다 — 검증이 되게)
      tokens   근거 토큰 수 (튜닝용)
    """
    q = _clean(question)[:MAX_QUESTION]
    if not q:
        return {"status": "miss", "answer": MISS_ANSWER, "sources": [],
                "examples": EXAMPLES, "tokens": 0}

    # ⚠️ probe 가 만든 ctx 를 재사용하지 않는다. 그건 POST 가 즉시 답하려고
    #    DB 만 본 것이고, 여기(백그라운드)서는 **시세를 받아와야** 한다.
    ctx = chat_context.build(conn, q, live=True)
    if not ctx["matched"]:
        # 규칙이 못 잡은 질문을 남긴다. 사전을 뭘로 늘릴지가 데이터로 나온다.
        try:
            chat_context.log_miss(conn, q)
        except Exception:
            pass
        return {"status": "miss", "answer": MISS_ANSWER, "sources": [],
                "examples": EXAMPLES, "tokens": 0}

    prompt = PROMPT.format(context=ctx["context"],
                           history=_history_block(history),
                           question=q) + _guard(q)
    try:
        # wait_ok=False — 사람이 기다리는 호출이다. 분당 한도에 닿으면
        # 쉬지 말고 바로 로컬로 내려간다.
        out = llm.generate_json(prompt, timeout=120,
                                prefer_local=prefer_local, wait_ok=False)
    except Exception as e:
        return {"status": "error", "answer": "", "sources": ctx["sources"],
                "message": "답을 만들지 못했습니다 (%s)" % e.__class__.__name__,
                "tokens": ctx["tokens"]}

    answer = _clean(out.get("answer") if isinstance(out, dict) else "")
    if not answer:
        return {"status": "error", "answer": "", "sources": ctx["sources"],
                "message": "답이 비어 있습니다", "tokens": ctx["tokens"]}
    answer = _fix_units(answer)

    if any(k in q for k in _FUTURE):
        cut = _drop_forecast(answer)
        if cut:
            answer = cut
        else:
            # 전부 미래 얘기였다. 그러면 LLM 답을 버리고 코드가 답한다.
            answer = ("예측은 하지 않습니다. 이 사이트는 지나간 자료만 보여드려요. "
                      "'지금 어떤지' 로 물어보시면 수치를 알려드릴 수 있습니다.")

    # ⚠️ 꼭 전해야 하는 말은 코드가 붙인다. 프롬프트에 적어도 LLM 이 흘린다 —
    #    "지금 값이 아닙니다" 가 빠지고 "보유한 최신 자료입니다" 로 바뀌었다.
    for n in ctx.get("notes") or []:
        if n not in answer:
            answer += "\n\n" + n

    # ⚠️ used 는 LLM 이 쓴 것이라 믿지 않는다. 화면에 보여주는 '근거' 는
    #    우리가 실제로 넣은 것(ctx["sources"])이다. 지어낸 출처를 띄우면
    #    검증 장치가 아니라 또 하나의 거짓말이 된다.
    return {"status": "ok", "answer": answer, "sources": ctx["sources"],
            "provider": llm.last_provider, "tokens": ctx["tokens"]}
