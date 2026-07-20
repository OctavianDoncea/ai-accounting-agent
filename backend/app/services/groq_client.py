import json
import logging
import httpx
from app.config import settings

log = logging.getLogger(__name__)

GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'

class GroqError(Exception):
    pass


class GroqClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ):
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model
        self.timeout = timeout
        if not self.api_key:
            raise GroqError(
                'GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys'
            )

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> dict:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': temperature,
            'response_format': {'type': 'json_object'},
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(GROQ_API_URL, headers=headers, json=payload)
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500] if exc.response else ""
            raise GroqError(f'Groq API error {exc.response.status_code}: {body}') from exc
        except httpx.HTTPError as exc:
            raise GroqError(f'Groq request failed: {exc}') from exc

        body = resp.json()
        content = (
            body.get('choices', [{}])[0]
            .get('message', {})
            .get('content', '')
            .strip()
        )
        if not content:
            raise GroqError('Groq returned an empty response')

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            salvaged = _extract_json_block(content)
            if salvaged is not None:
                return salvaged
            raise GroqError(
                f'Could not parse JSON from Groq output: {exc}\nRaw: {content[:500]}'
            ) from exc

    def is_available(self) -> bool:
        """Quick check that the API key is valid and the model exists."""
        if not self.api_key:
            return False
        try:
            headers = {'Authorization': f'Bearer {self.api_key}'}
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    'https://api.groq.com/openai/v1/models', headers=headers
                )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False


def _extract_json_block(text: str) -> dict | None:
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
