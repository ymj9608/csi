"""Local Qwen action adapter; same host tool/evidence/verification gates as OpenAI."""
import json
import uuid
import copy
import httpx
from architecture_agent.vision import local_url
from .repository import Rejected
from .runtime_settings import integer


class LocalActionsClient:
    def __init__(self, url='http://127.0.0.1:11434', transport=None):
        self.url, self.transport = local_url(url), transport

    def __call__(self, payload):
        messages = [{'role': 'system', 'content': payload['instructions'] +
                     '\nSelect exactly one allowed action. Return JSON with name and arguments; '
                     'arguments must be an OBJECT matching that tool parameters. '
                     'Use concise instructions; do not repeat supplied code or policy. Tools: ' +
                     json.dumps(payload['tools'], ensure_ascii=False, separators=(',', ':'))}]
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
        alternatives = []
        for tool in payload['tools']:
            parameters = copy.deepcopy(tool['parameters'])
            for field in parameters['properties'].values():
                if field.get('type') == 'string':
                    field['maxLength'] = 1800
                elif field.get('type') == 'array':
                    field['maxItems'] = 16
            alternatives.append({'type':'object', 'additionalProperties':False,
                'required':['name','arguments'], 'properties':{
                    'name':{'const':tool['name']}, 'arguments':parameters}})
        schema = {'anyOf': alternatives}
        context_size = integer('CSI_LOCAL_VLM_NUM_CTX', 16384, 8192, 32768)
        timeout = min(integer('CSI_LOCAL_VLM_TIMEOUT_SECONDS', 600, 30, 900),
                      payload.get('_timeout_seconds', 900))
        if timeout <= 0:
            raise Rejected('VLM_TIME_BUDGET')
        try:
            with httpx.Client(timeout=timeout, trust_env=False, transport=self.transport) as client:
                response = client.post(self.url + '/api/chat', json={
                    'model': payload['model'], 'messages': messages, 'format': schema,
                    'stream': False, 'think': False,
                    'keep_alive': integer('CSI_LOCAL_VLM_KEEP_ALIVE_SECONDS', 300, 0, 600),
                    'options': {'num_ctx': context_size,
                                'num_predict': integer('CSI_LOCAL_VLM_NUM_PREDICT', 1024, 256, 2048),
                                'temperature': 0}})
                response.raise_for_status()
                raw = response.json()
            if raw.get('done_reason') != 'stop':
                raise Rejected('VLM_OUTPUT_INCOMPLETE')
            content = raw.get('message', {}).get('content')
            if not isinstance(content, str) or not content.strip():
                raise Rejected('VLM_EMPTY_FINAL_CONTENT')
            action = json.loads(content)
            if set(action) != {'name', 'arguments'} or not isinstance(action['arguments'], (str, dict)):
                raise Rejected('VLM_TOOL_ARGUMENTS')
            if isinstance(action['arguments'], dict):
                action['arguments'] = json.dumps(action['arguments'], ensure_ascii=False)
            counts = [raw.get('prompt_eval_count'), raw.get('eval_count')]
            if any(type(n) is not int or n < 0 for n in counts):
                raise Rejected('VLM_USAGE_MISSING')
            if sum(counts) >= context_size:
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
