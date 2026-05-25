"""LLM API 调用层。

Provider-agnostic，通过配置文件支持不同 API。
OpenAI 兼容接口 和 Anthropic 接口都支持。
"""

import json
import os
import re
from typing import Any

import httpx


class LLMError(Exception):
    """LLM 调用异常。"""


def _resolve_env(value: str) -> str:
    """将 ${VAR_NAME} 替换为环境变量值。"""
    def _replace(m: re.Match) -> str:
        return os.environ.get(m.group(1), '')
    return re.sub(r'\$\{(\w+)\}', _replace, value)


class LLMClient:
    def __init__(self, config: dict[str, Any]):
        self.provider = config.get('provider', 'openai')
        self.model = config['model']
        self.max_tokens = config.get('max_tokens', 4096)
        self.temperature = config.get('temperature', 0.1)
        self.base_url = config['base_url'].rstrip('/')
        self.api_key = _resolve_env(config['api_key'])

        self._headers = {
            'Content-Type': 'application/json',
        }
        if self.provider == 'openai':
            self._headers['Authorization'] = f'Bearer {self.api_key}'
        elif self.provider == 'anthropic':
            self._headers['x-api-key'] = self.api_key
            self._headers['anthropic-version'] = '2023-06-01'
        # 自定义额外 header
        extra = config.get('headers', {})
        for k, v in extra.items():
            self._headers[k] = _resolve_env(v)

    def call(self, system_prompt: str, user_message: str) -> tuple[str, dict]:
        """调用 LLM，返回 (文本, token用量)。

        Args:
            system_prompt: 系统提示词（prompt 模板）
            user_message: 用户消息（研报文本）

        Returns:
            (响应文本, 用量: {prompt_tokens, completion_tokens, total_tokens})
        """
        if self.provider == 'anthropic':
            return self._call_anthropic(system_prompt, user_message)
        return self._call_openai(system_prompt, user_message)

    def _call_openai(self, system_prompt: str, user_message: str) -> tuple[str, dict]:
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_message},
            ],
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f'{self.base_url}/chat/completions',
                headers=self._headers,
                json=payload,
            )
        if resp.status_code != 200:
            raise LLMError(
                f'API error {resp.status_code}: {resp.text[:500]}'
            )
        body = resp.json()
        text = body['choices'][0]['message']['content']
        usage = body.get('usage', {})
        return text, {'prompt_tokens': usage.get('prompt_tokens', 0),
                       'completion_tokens': usage.get('completion_tokens', 0),
                       'total_tokens': usage.get('total_tokens', 0)}

    def _call_anthropic(self, system_prompt: str, user_message: str) -> tuple[str, dict]:
        payload = {
            'model': self.model,
            'max_tokens': self.max_tokens,
            'system': system_prompt,
            'messages': [
                {'role': 'user', 'content': user_message},
            ],
            'temperature': self.temperature,
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f'{self.base_url}/messages',
                headers=self._headers,
                json=payload,
            )
        if resp.status_code != 200:
            raise LLMError(
                f'API error {resp.status_code}: {resp.text[:500]}'
            )
        body = resp.json()
        text = body['content'][0]['text']
        usage = body.get('usage', {})
        return text, {'prompt_tokens': usage.get('input_tokens', 0),
                       'completion_tokens': usage.get('output_tokens', 0),
                       'total_tokens': usage.get('input_tokens', 0) + usage.get('output_tokens', 0)}

    def call_json(self, system_prompt: str, user_message: str) -> tuple[dict, dict]:
        """调用 LLM 并解析返回的 JSON。

        Returns:
            (解析后的 JSON 字典, token用量)
        """
        text, usage = self.call(system_prompt, user_message)
        # 尝试从代码块中提取 JSON
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            text = match.group(1)
        text = text.strip()
        # 去掉可能的非 JSON 前缀/后缀
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            text = text[start:end + 1]
        return json.loads(text), usage
