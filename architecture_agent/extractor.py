"""Local Qwen3-VL call: read an architecture diagram image, extract high-level
structure only. Never asks for or accepts file paths / code structure."""
import base64
import json
import httpx
from . import schema

DEFAULT_MODEL = "qwen3-vl:8b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

PROMPT = (
    "이 아키텍처 다이어그램 이미지를 분석해줘. 그림에 실제로 보이는 것만 읽고, "
    "그림에 없는 내용은 추측해서 지어내지 마.\n"
    "다음 JSON 형식으로만 답해:\n"
    '{"summary": "전체 아키텍처를 1~3문장으로 설명 (한국어)", '
    '"components": [{"name": "박스/컴포넌트 이름", "role": "역할 설명 (한국어)", '
    '"isolationStatus": "ISOLATED 또는 PRODUCTION 또는 UNKNOWN", '
    '"state": "OBSERVED(그림에 직접 쓰여있음) 또는 INFERRED(추론) 또는 UNKNOWN(판단 불가)"}]}\n'
    "절대 파일 경로나 코드 구조는 언급하지 마 — 이 그림에는 그런 정보가 없으니까.\n"
    "component의 name은 그림에 적힌 텍스트를 최대한 그대로 사용해(원문이 영어면 영어 그대로). "
    "하지만 role과 summary는 원문이 영어여도 반드시 한국어로 번역해서 설명해. "
    "isolationStatus와 state는 번역하지 말고 ISOLATED/PRODUCTION/UNKNOWN, "
    "OBSERVED/INFERRED/UNKNOWN 중 하나를 영어 그대로 써."
)


def extract(image_bytes, model=DEFAULT_MODEL, ollama_url=DEFAULT_OLLAMA_URL):
    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "stream": False,
        "keep_alive": 0,  # Release GPU memory before the coding worker runs.
        "think": False,
        "format": "json",
        # Detailed diagrams make the model "think" at length before answering;
        # num_predict/num_ctx must cover thinking + the final JSON, or Ollama
        # truncates mid-thought and the response has no usable content at all.
        # Discovered via live testing against a real ~1.5MB diagram (took ~8min).
        "options": {"temperature": 0, "seed": 42, "num_predict": 10000, "num_ctx": 16384},
        "messages": [{"role": "user", "content": PROMPT, "images": [encoded]}],
    }
    with httpx.Client(timeout=600, trust_env=False) as client:
        response = client.post(ollama_url.rstrip("/") + "/api/chat", json=payload)
        response.raise_for_status()
        body = response.json()
    text = body["message"]["content"]
    raw = json.loads(text)
    return schema.validate_result(raw)
