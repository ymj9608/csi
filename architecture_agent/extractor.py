"""Local Qwen3-VL call: read an architecture diagram image, extract high-level
structure only. Never asks for or accepts file paths / code structure."""
import base64
import json
import httpx
from . import schema
from coding_agent.runtime_settings import integer

DEFAULT_MODEL = "qwen3-vl:8b-instruct"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

PROMPT = (
    "이 아키텍처 다이어그램 이미지를 분석해줘. 그림에 실제로 보이는 것만 읽고, "
    "그림에 없는 내용은 추측해서 지어내지 마.\n"
    "모든 작은 박스를 나열하지 말고 최상위 서비스와 데이터 저장소 3~6개만 골라. "
    "summary는 한 문장, 각 role은 20자 이내의 짧은 구절로 작성해. "
    "격리나 운영 환경이라는 표시가 없으면 isolationStatus는 UNKNOWN으로 작성해.\n"
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

# Constrain generation as well as the prompt: unconstrained JSON can enumerate
# every nested box and exhaust the local model's time/output budget.
OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "components"],
    "properties": {
        "summary": {"type": "string", "maxLength": 180},
        "components": {"type": "array", "minItems": 1, "maxItems": 6, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "role", "isolationStatus", "state"],
            "properties": {
                "name": {"type": "string", "maxLength": 60},
                "role": {"type": "string", "maxLength": 40},
                "isolationStatus": {"type": "string", "enum": sorted(schema.ISOLATION_STATUSES)},
                "state": {"type": "string", "enum": sorted(schema.STATES)},
            },
        }},
    },
}


def extract(image_bytes, model=DEFAULT_MODEL, ollama_url=DEFAULT_OLLAMA_URL):
    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "stream": False,
        "keep_alive": 0,  # Release GPU memory before the coding worker runs.
        "think": False,
        "format": OUTPUT_SCHEMA,
        # Bound this high-level overview for local machines. The coding VLM
        # still receives the original image, not only this compact extraction.
        "options": {"temperature": 0, "seed": 42,
                    "num_predict": integer('CSI_ARCHITECTURE_NUM_PREDICT', 1536, 512, 4096), "num_ctx": 4096},
        "messages": [{"role": "user", "content": PROMPT, "images": [encoded]}],
    }
    with httpx.Client(timeout=integer('CSI_ARCHITECTURE_TIMEOUT_SECONDS', 900, 60, 1800), trust_env=False) as client:
        response = client.post(ollama_url.rstrip("/") + "/api/chat", json=payload)
        response.raise_for_status()
        body = response.json()
    if body.get("done_reason") != "stop":
        raise ValueError("Architecture extraction did not complete")
    text = body["message"]["content"]
    raw = json.loads(text)
    return schema.validate_result(raw)
