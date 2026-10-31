"""LLM 호출 한 곳. 외부(Groq) 를 먼저 쓰고, 안 되면 서버 안의 Ollama 로 넘어간다.

왜 둘을 두는가 —
  로컬(qwen2.5:7b, CPU)은 분석 한 건에 100초가 걸린다. 아침 배치는 상관없지만
  사용자가 검색창에서 기다리기엔 너무 길다. Groq 는 같은 일을 몇 초에 끝낸다.
  대신 무료 한도가 있고(하루 1,000회·분당 30회), 제공처가 모델을 없애기도 한다.
  실제로 2026-08 에 Llama 3.3 70B 가 사라져 그걸 쓰던 코드들이 깨졌다.

  그래서 외부는 '빠른 길' 일 뿐이고, 막히면 로컬이 받는다. 수집 쪽에서
  Finnhub 가 막히면 RSS 로 넘어가는 것과 같은 구조다. 외부가 통째로 죽어도
  서비스는 느려질 뿐 멈추지 않는다.

우리 사용량은 하루 50~120회쯤이라 무료 한도 안에 들어간다.
키가 없으면 아무것도 설정할 필요 없이 로컬로만 돈다.
"""
import json
import os
import time
from collections import deque
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()

# ── 외부 (Groq) ──
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# 모델은 .env 에서 바꿀 수 있게 한다. 제공처가 모델을 없애는 일이 있어서,
# 코드를 고치지 않고 갈아탈 수 있어야 한다. check_groq.py 로 목록을 볼 수 있다.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b").strip()

# ── 로컬 (Ollama) ──
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"

# Groq 무료 한도에서 먼저 걸리는 건 '분당 토큰(TPM)' 이다. 하루 1,000회는
# 넉넉한데 분당 8,000 토큰이라, 분석 한 건이 3,000 토큰쯤이니 2~3건을 연달아
# 보내면 바로 429 가 난다. 실제로 재분석 배치가 2건 만에 막혔다.
#
# 그래서 미리 속도를 맞춘다 — 최근 60초에 쓴 토큰을 기억해 두고, 한도에
# 가까워지면 잠깐 쉰다. 429 를 받고 되돌리는 것보다 안 맞는 편이 빠르다.
_TPM_LIMIT = 8000
_TPM_MARGIN = 6500          # 여유를 두고 멈춘다 (응답 토큰을 미리 알 수 없으므로)
_recent = deque()           # (시각, 토큰수)

# 그래도 429 가 나면 Retry-After 만큼만 쉰다. TPM 한도는 몇 초면 풀리므로
# 길게 쉬면 손해다. 아주 긴 값을 주면 일당 한도를 다 쓴 것으로 보고 로컬로.
_groq_blocked_until = 0.0
_LONG_COOLDOWN = 900

last_provider = None          # 마지막으로 성공한 쪽 ("groq" / "local")


def _post_json(url, body, headers, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          # Cloudflare 가 urllib 기본 UA 를
                                          # 막는다(403, code 1010).
                                          "User-Agent": "econ-piece/1.0 (+https://macmini.tail1ca8bf.ts.net)",
                                          **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _throttle(est=3000):
    """최근 60초 토큰 사용량을 보고, 한도에 닿기 전에 잠깐 쉰다."""
    now = time.time()
    while _recent and now - _recent[0][0] > 60:
        _recent.popleft()
    used = sum(t for _, t in _recent)
    if used + est > _TPM_MARGIN and _recent:
        wait = 60 - (now - _recent[0][0]) + 0.5
        if wait > 0:
            print(f"  Groq 분당 토큰 한도 근접({used}) — {wait:.0f}초 대기")
            time.sleep(wait)
            return _throttle(est)


def _note_usage(data):
    u = (data or {}).get("usage") or {}
    _recent.append((time.time(), u.get("total_tokens") or 1500))


def _groq(prompt, timeout):
    _throttle()
    data = _post_json(
        GROQ_URL,
        {"model": GROQ_MODEL,
         "messages": [{"role": "user", "content": prompt}],
         "response_format": {"type": "json_object"},
         "temperature": 0.3},
        {"Authorization": f"Bearer {GROQ_KEY}"},
        timeout)
    _note_usage(data)
    return json.loads(data["choices"][0]["message"]["content"])


def _local(prompt, timeout):
    data = _post_json(
        OLLAMA_URL,
        {"model": MODEL, "prompt": prompt, "format": "json",
         "stream": False, "options": {"temperature": 0.3}},
        {}, timeout)
    return json.loads(data["response"])


def generate_json(prompt, tries=3, timeout=300, prefer_local=False):
    """JSON 응답을 받아 dict 로 돌려준다.

    기본은 Groq -> (실패하면) Ollama 순. 둘 다 실패하면 마지막 예외를 올린다.

    prefer_local=True — 사용자가 기다리지 않는 배치용. 로컬을 먼저 쓰고,
      로컬이 죽어 있으면 Groq 로 넘어간다.

      Groq 무료 한도(분당 8,000 토큰)에서 먼저 막히는 쪽은 언제나 배치다.
      그런데 배치는 빠를 필요가 없다 — 아침·오후에 혼자 돌고 아무도 안 기다린다.
      정작 빨라야 하는 것은 사용자가 검색창에서 기다리는 /api/news/pick 하나다.
      그래서 배치를 로컬로 내려 Groq 한도를 그쪽에 남겨둔다.

      2026-10-31 실측(qwen2.5:7b, CPU): 환율 해설 30초 · 제목 번역 3초.
      기사 분석 100초와 달리 프롬프트가 짧아서 로컬로도 감당이 된다.
    """
    global last_provider, _groq_blocked_until

    if prefer_local:
        try:
            out = _local(prompt, timeout)
            last_provider = "local"
            return out
        except Exception as e:
            print(f"  로컬 실패({e.__class__.__name__}) — Groq 로 넘어간다")

    if GROQ_KEY and time.time() >= _groq_blocked_until:
        for attempt in range(tries):
            try:
                out = _groq(prompt, min(timeout, 60))
                last_provider = "groq"
                return out
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    # Retry-After 를 그대로 따른다. 분당 한도면 몇 초,
                    # 일당 한도를 다 썼으면 아주 긴 값이 온다.
                    ra = e.headers.get("retry-after") if e.headers else None
                    try:
                        wait = float(ra)
                    except (TypeError, ValueError):
                        wait = 20.0
                    if wait > 120:
                        _groq_blocked_until = time.time() + _LONG_COOLDOWN
                        print(f"  Groq 일당 한도 소진(재시도 {wait:.0f}초) — 로컬로 전환")
                        break
                    print(f"  Groq 분당 한도 — {wait:.0f}초 쉬고 재시도")
                    _recent.clear()
                    time.sleep(wait + 1)
                    continue
                if 400 <= e.code < 500:
                    # 모델명이 틀렸거나 키가 잘못된 것. 재시도해도 같다.
                    print(f"  Groq 설정 오류 {e.code} ({GROQ_MODEL}) — 로컬로 전환")
                    # 설정이 틀린 것이라 다시 보내도 같다. 길게 쉬고 로컬로 간다.
                    # (2026-10-31 전까지 여기에 정의되지 않은 _COOLDOWN_SEC 이 있어서,
                    #  정작 로컬로 넘어가야 할 때 NameError 로 그냥 실패했다.
                    #  2026-08 에 Llama 3.3 이 사라졌을 때가 바로 이 경로다.)
                    _groq_blocked_until = time.time() + _LONG_COOLDOWN
                    break
                if attempt == tries - 1:
                    print(f"  Groq 오류 {e.code} — 로컬로 전환")
                time.sleep(2)
            except Exception as e:
                if attempt == tries - 1:
                    print(f"  Groq 실패({e.__class__.__name__}) — 로컬로 전환")
                time.sleep(2)

    last_err = None
    for attempt in range(tries):
        try:
            out = _local(prompt, timeout)
            last_provider = "local"
            return out
        except Exception as e:
            last_err = e
            if attempt < tries - 1:
                print(f"  재시도 {attempt + 1}/{tries} ({e.__class__.__name__}) ...")
                time.sleep(3)
    raise last_err
