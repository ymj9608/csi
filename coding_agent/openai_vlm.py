"""OpenAI Responses transport. Credentials and provider responses never enter public logs."""
import os
import httpx
from .repository import Rejected

DEFAULT_MODEL = 'gpt-5.4-mini-2026-03-17'
MODELS = {DEFAULT_MODEL, 'gpt-5.4-mini', 'gpt-6.1-sol', 'gpt-6-astra'}
ENDPOINT = 'https://api.openai.com/v1/responses'


def provider_name():
    provider = os.environ.get('CSI_VLM_PROVIDER', 'openai')
    if provider not in {'openai', 'ollama'}:
        raise Rejected('VLM_PROVIDER_UNSUPPORTED')
    return provider


def model_name():
    provider = provider_name()
    model = os.environ.get('CSI_VLM_MODEL') or (DEFAULT_MODEL if provider == 'openai' else 'qwen3-vl:8b')
    if model not in (MODELS if provider == 'openai' else {'qwen3-vl:8b'}):
        raise Rejected('VLM_MODEL_UNSUPPORTED')
    return model


class ResponsesClient:
    def __init__(self, api_key=None, transport=None):
        self.key = api_key or os.environ.get('OPENAI_API_KEY', '')
        if not self.key.strip():
            raise Rejected('OPENAI_API_KEY_REQUIRED')
        self.transport = transport

    def __call__(self, payload):
        try:
            # No redirects, arbitrary base URLs, proxy environment, or implicit retries.
            with httpx.Client(timeout=60, trust_env=False, transport=self.transport) as api:
                response = api.post(ENDPOINT, headers={'Authorization': 'Bearer ' + self.key}, json=payload)
                if response.status_code in {401, 403}:
                    raise Rejected('VLM_AUTH_FAILED')
                if response.status_code == 429:
                    raise Rejected('VLM_RATE_LIMITED')
                response.raise_for_status()
                value = response.json()
                if not isinstance(value, dict):
                    raise Rejected('VLM_RESPONSE_INVALID')
                return value
        except httpx.TimeoutException:
            raise Rejected('VLM_TIMEOUT') from None
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(exc, Rejected):
                raise
            raise Rejected('VLM_UNAVAILABLE') from None
