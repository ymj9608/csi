"""Versioned prompts, conservative token accounting, deadlines and bounded API calls."""
import asyncio
import json
import os
import time
from pathlib import Path
import httpx

PROMPTS = Path(__file__).resolve().parents[1] / 'prompts'
MAX_TURNS = 12
MAX_TOOL_REPEATS = 3
MAX_INPUT_TOKENS = 24000
MAX_OUTPUT_TOKENS = 6000
MAX_RESERVED_TOKENS = 200000
MAX_MODEL_CALLS = 32
WORK_SECONDS = 150

class BudgetExceeded(RuntimeError): pass
class TruncatedOutput(RuntimeError): pass


def prompt(name):
    if name not in {'planner', 'reviewer'}:
        raise ValueError('Unknown prompt')
    return (PROMPTS / (name + '.md')).read_text()


def token_bound(value):
    # UTF-8 byte count upper-bounds byte-tokenized content; deliberately conservative.
    # Add framing/schema overhead instead of claiming an exact provider tokenizer count.
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) + 512


class Ledger:
    def __init__(self, state=None):
        self.data = dict(state or {'startedAt': time.time(), 'calls': 0, 'reservedTokens': 0,
                                  'actualTokens': 0, 'maxInputBound': 0})

    def reserve(self, messages, tools, output_tokens):
        amount = token_bound({'messages': messages, 'tools': tools})
        if amount > MAX_INPUT_TOKENS or output_tokens > MAX_OUTPUT_TOKENS:
            raise BudgetExceeded('REQUEST_CONTEXT_BUDGET')
        if time.time() - self.data['startedAt'] > WORK_SECONDS:
            raise BudgetExceeded('WORK_DEADLINE')
        if self.data['calls'] >= MAX_MODEL_CALLS or self.data['reservedTokens'] + amount + output_tokens > MAX_RESERVED_TOKENS:
            raise BudgetExceeded('SCAN_MODEL_BUDGET')
        self.data['calls'] += 1
        self.data['reservedTokens'] += amount + output_tokens
        self.data['maxInputBound'] = max(self.data['maxInputBound'], amount)


async def completion(messages, ledger, *, tools=None, output_tokens=MAX_OUTPUT_TOKENS, json_output=False):
    base = os.environ.get('LLM_BASE_URL', '')
    key = os.environ.get('LLM_API_KEY', '')
    model = os.environ.get('LLM_MODEL', '')
    if not base.startswith('https://') or not key or not model:
        raise ValueError('LLM_CONFIG')
    payload = {'model': model, 'temperature': 0, 'max_tokens': output_tokens, 'messages': messages}
    if tools:
        payload.update(tools=tools, tool_choice='auto', parallel_tool_calls=False)
    if json_output: payload['response_format'] = {'type': 'json_object'}
    # One initial request + at most two transient retries, each charged to the same ledger.
    for attempt in range(3):
        ledger.reserve(messages, tools, output_tokens)
        remaining = WORK_SECONDS - (time.time() - ledger.data['startedAt'])
        if remaining <= 0: raise BudgetExceeded('WORK_DEADLINE')
        async with httpx.AsyncClient(timeout=min(45, remaining), follow_redirects=False) as client:
            r = await client.post(base.rstrip('/')+'/chat/completions', headers={'Authorization':'Bearer '+key}, json=payload)
            if getattr(r,'status_code',200) in {429,503} and attempt<2:
                await asyncio.sleep(0.5*(attempt+1))
                continue
            r.raise_for_status()
        break
    body = r.json()
    ledger.data['actualTokens'] += int(body.get('usage', {}).get('total_tokens', 0))
    choice = body['choices'][0]
    if choice.get('finish_reason') == 'length': raise TruncatedOutput('OUTPUT_LIMIT')
    if choice.get('finish_reason') in {'content_filter'}: raise ValueError('FILTERED_OUTPUT')
    return choice['message']
