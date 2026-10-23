"""Local Qwen action adapter; same host tool/evidence/verification gates as OpenAI."""
import json
import uuid
import httpx
from architecture_agent.vision import local_url
from .repository import Rejected


class LocalActionsClient:
    def __init__(self, url='http://127.0.0.1:11434', transport=None):
        self.url, self.transport = local_url(url), transport

    def __call__(self, payload):
        messages = [{'role': 'system', 'content': payload['instructions'] +
                     '\nSelect exactly one allowed action. Return JSON with name and arguments; '
                     'arguments is a JSON-encoded object matching that tool parameters. Tools: ' +
                     json.dumps(payload['tools'], ensure_ascii=False)}]
        for item in payload['input']:
            if item.get('type') == 'reasoning':
                continue
            if isinstance(item.get('content'), list):
                message = {'role': item['role'], 'content': '\n'.join(
                    c['text'] for c in item['content'] if c['type'] == 'input_text')}
                images = [c['image_url'].split(',', 1)[1] for c in item['content'] if c['type'] == 'input_image']
                if images:
                    message['images'] = images
                messages.append(message)
            else:
                messages.append({'role': 'assistant' if item.get('type') == 'function_call' else 'user',
                                 'content': json.dumps(item, ensure_ascii=False)})
        if sum(len(m['content'].encode()) for m in messages) > 40_000:
            raise Rejected('VLM_CONTEXT_TOO_LARGE')
        schema = {'type': 'object', 'properties': {
            'name': {'type': 'string', 'enum': [t['name'] for t in payload['tools']]},
            'arguments': {'type': 'string'}}, 'required': ['name', 'arguments'], 'additionalProperties': False}
        try:
            with httpx.Client(timeout=180, trust_env=False, transport=self.transport) as client:
                response = client.post(self.url + '/api/chat', json={
                    'model': payload['model'], 'messages': messages, 'format': schema,
                    'stream': False, 'think': False, 'keep_alive': 0,
                    'options': {'num_ctx': 16384, 'num_predict': 2048, 'temperature': 0}})
                response.raise_for_status()
                raw = response.json()
            if raw.get('done_reason') != 'stop':
                raise Rejected('VLM_OUTPUT_INCOMPLETE')
            action = json.loads(raw['message']['content'])
            if set(action) != {'name', 'arguments'} or not isinstance(action['arguments'], str):
                raise Rejected('VLM_TOOL_ARGUMENTS')
            counts = [raw.get('prompt_eval_count'), raw.get('eval_count')]
            if any(type(n) is not int or n < 0 for n in counts):
                raise Rejected('VLM_USAGE_MISSING')
            if sum(counts) >= 16384:
                raise Rejected('VLM_CONTEXT_TOO_LARGE')
            return {'status': 'completed', 'output': [{'type': 'function_call',
                    'call_id': str(uuid.uuid4()), **action}],
                    'usage': {'input_tokens': counts[0], 'output_tokens': counts[1]}}
        except httpx.TimeoutException:
            raise Rejected('VLM_TIMEOUT') from None
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, Rejected):
                raise
            raise Rejected('VLM_UNAVAILABLE') from None
