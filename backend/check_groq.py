"""Groq 키가 제대로 붙었는지, 어떤 모델을 쓸 수 있는지 확인한다.

무료 제공처는 모델을 예고 없이 없앤다(2026-08 에 Llama 3.3 70B 가 사라졌다).
그래서 모델 이름을 코드에 박지 않고 .env 의 GROQ_MODEL 로 둔다.
이 스크립트로 목록을 보고 골라 넣으면 된다.

사용법:
  .venv/bin/python check_groq.py
"""
import json
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()
KEY = os.environ.get("GROQ_API_KEY", "").strip()
WANT = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b").strip()

if not KEY:
    print("GROQ_API_KEY 가 .env 에 없습니다.")
    print("  ~/School-Project/backend/.env 에 아래 한 줄을 넣어 주세요:")
    print("  GROQ_API_KEY=여기에_키")
    raise SystemExit(1)

print(f"키 확인 — {KEY[:6]}…{KEY[-4:]} (길이 {len(KEY)})")
print()


def get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}", "User-Agent": "econ-piece/1.0 (+https://macmini.tail1ca8bf.ts.net)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


try:
    models = get("https://api.groq.com/openai/v1/models")
except urllib.error.HTTPError as e:
    print(f"모델 목록 실패 HTTP {e.code} — 키가 잘못됐을 수 있습니다.")
    print(e.read()[:300].decode("utf-8", "replace"))
    raise SystemExit(1)

ids = sorted(m["id"] for m in models.get("data", []))
print(f"쓸 수 있는 모델 {len(ids)}개")
for i in ids:
    mark = "  ← GROQ_MODEL 설정값" if i == WANT else ""
    print("   ", i, mark)
print()

if WANT not in ids:
    print(f"⚠️  설정된 GROQ_MODEL '{WANT}' 이 목록에 없습니다.")
    print("    위 목록에서 하나 골라 .env 의 GROQ_MODEL 에 넣어 주세요.")
    raise SystemExit(1)

print(f"'{WANT}' 로 실제 호출 시험 중…")
body = {
    "model": WANT,
    "messages": [{"role": "user", "content":
                  '다음 JSON 형식으로만 답하라: {"greeting": "<한국어 인사 한 마디>"}'}],
    "response_format": {"type": "json_object"},
    "temperature": 0.3,
}
req = urllib.request.Request(
    "https://api.groq.com/openai/v1/chat/completions",
    data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json",
             "Authorization": f"Bearer {KEY}", "User-Agent": "econ-piece/1.0 (+https://macmini.tail1ca8bf.ts.net)"})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
except urllib.error.HTTPError as e:
    print(f"호출 실패 HTTP {e.code}")
    print(e.read()[:400].decode("utf-8", "replace"))
    raise SystemExit(1)

took = time.time() - t0
msg = out["choices"][0]["message"]["content"]
usage = out.get("usage", {})
print(f"성공 — {took:.2f}초")
print("  응답:", msg.strip()[:120])
print("  토큰:", usage.get("prompt_tokens"), "+", usage.get("completion_tokens"))
print()
print(f"로컬 모델은 같은 일에 100초쯤 걸립니다. 약 {100 / max(took, 0.01):.0f}배 빠릅니다.")
