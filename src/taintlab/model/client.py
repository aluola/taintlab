import json
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from taintlab.model.protocol import ACTION_SCHEMA

DEFAULT_CONFIG = {
    'endpoint': 'http://127.0.0.1:8080/v1/chat/completions',
    'model': 'Qwen3-0.6B-Q8_0', 'temperature': 0.2, 'top_p': 0.9,
    'max_tokens': 512, 'context_size': 4096, 'max_rounds': 9,
    'format_retries': 1, 'timeout_seconds': 120, 'task_timeout_seconds': 240,
}

class ContextBudgetError(RuntimeError):
    pass

def load_config():
    config = DEFAULT_CONFIG.copy()
    p = Path('configs/model.json')
    if p.exists():
        config.update(json.loads(p.read_text(encoding='utf-8-sig')))
    return config

class LocalModel:
    backend_type = 'local_llama_cpp'
    def __init__(self, config=None):
        self.config = config or load_config()
        endpoint = self.config.get('endpoint', DEFAULT_CONFIG['endpoint'])
        u = urlparse(endpoint)
        if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1') or u.username or u.password:
            raise ValueError('Only explicit local HTTP inference endpoints are permitted')
        self.endpoint = endpoint

    def generate(self, messages, seed, timeout_seconds=None):
        payload = {
            'model': self.config.get('model', 'local'), 'messages': messages,
            'temperature': self.config['temperature'], 'top_p': self.config['top_p'],
            'max_tokens': self.config['max_tokens'], 'seed': seed,
            'top_k':self.config.get('top_k',40),'min_p':self.config.get('min_p',0.05),'repeat_penalty':self.config.get('repeat_penalty',1.0),
            'stream': False, 'cache_prompt': False,
            'response_format': {'type': 'json_schema', 'json_schema': {'name':'agent_action', 'strict': True, 'schema': ACTION_SCHEMA}},
            'chat_template_kwargs': {'enable_thinking': False},
        }
        start = time.monotonic()
        # Ignore environment proxy settings; never follow a redirect to a remote host.
        with httpx.Client(timeout=min(self.config['timeout_seconds'],timeout_seconds) if timeout_seconds is not None else self.config['timeout_seconds'], trust_env=False, follow_redirects=False) as client:
            response = client.post(self.endpoint, json=payload)
            if response.status_code==400 and any(term in response.text.lower() for term in ('context','exceed','too long','n_ctx')):
                raise ContextBudgetError('context_budget_exceeded')
            response.raise_for_status()
            obj = response.json()
        return obj['choices'][0]['message']['content'], obj.get('usage', {}), time.monotonic()-start

class ScriptedModel:
    """Deterministic unit-test fixture. Never a formal-experiment backend."""
    backend_type = 'scripted_test'
    config = DEFAULT_CONFIG
    def __init__(self, actions):
        self.actions = iter(actions)
    def generate(self, messages, seed):
        action = next(self.actions)
        return action if isinstance(action,str) else json.dumps(action,ensure_ascii=False), {}, 0.0
