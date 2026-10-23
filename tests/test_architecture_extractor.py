import base64
import json

import httpx
import pytest

from architecture_agent import extractor, schema

WELL_FORMED = {
    "summary": "Lichu는 라이선스 관리 서비스와 격리된 연습 환경으로 구성됩니다.",
    "components": [
        {"name": "Isolated CSI Lab Mode", "role": "격리된 연습 환경", "isolationStatus": "ISOLATED", "state": "OBSERVED"},
    ],
}


def test_validate_accepts_well_formed_list():
    result = schema.validate_result(WELL_FORMED)
    assert result["summary"] == WELL_FORMED["summary"]
    assert result["components"][0]["name"] == "Isolated CSI Lab Mode"


def test_validate_rejects_missing_role():
    broken = json.loads(json.dumps(WELL_FORMED))
    del broken["components"][0]["role"]
    with pytest.raises(ValueError):
        schema.validate_result(broken)


def test_validate_rejects_unknown_isolation_status():
    broken = json.loads(json.dumps(WELL_FORMED))
    broken["components"][0]["isolationStatus"] = "PUBLIC_CLOUD"
    with pytest.raises(ValueError):
        schema.validate_result(broken)


def test_validate_requires_summary_string():
    broken = json.loads(json.dumps(WELL_FORMED))
    broken["summary"] = ""
    with pytest.raises(ValueError):
        schema.validate_result(broken)
    broken["summary"] = None
    with pytest.raises(ValueError):
        schema.validate_result(broken)


def test_extract_calls_ollama_with_image_and_parses_result(monkeypatch):
    captured = {}

    def handler(request):
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": json.dumps(WELL_FORMED)}})

    real_client = httpx.Client
    monkeypatch.setattr(
        extractor.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **{k: v for k, v in kwargs.items() if k != "trust_env"}),
    )
    result = extractor.extract(b"fake-png-bytes", ollama_url="http://127.0.0.1:11434")
    assert result["summary"] == WELL_FORMED["summary"]
    sent = captured["payload"]
    assert sent["model"] == extractor.DEFAULT_MODEL
    assert sent["messages"][0]["images"] == [base64.b64encode(b"fake-png-bytes").decode("ascii")]


def test_prompt_never_asks_for_file_paths():
    assert "파일 경로나 코드 구조는 언급하지 마" in extractor.PROMPT


def test_prompt_requests_summary():
    assert "summary" in extractor.PROMPT
