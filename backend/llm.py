import json
import time
import urllib.request

# 로컬 Ollama (맥미니에서 직접 실행 — 외부 의존 0, 할당량 없음)
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"


def generate_json(prompt, tries=3, timeout=300):
    """Ollama 로 JSON 응답 생성. dict 반환."""
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "format": "json",        # 유효한 JSON 강제
        "stream": False,
        "options": {"temperature": 0.3},
    }).encode()
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            return json.loads(data["response"])
        except Exception as e:
            if attempt < tries - 1:
                print(f"  재시도 {attempt + 1}/{tries} ({e.__class__.__name__}) ...")
                time.sleep(3)
            else:
                raise
