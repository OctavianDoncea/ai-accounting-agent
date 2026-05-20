import json
import logging
import httpx
from app.config import settings

log = logging.getLogger(__name__)

class OllamaError(Exception):
    pass


class OllamaClient:
    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float = 120.0):
        self.base_url = (base_url or settings.ollama_url).rstrip('/')
        self.model = model or settings.ollama_model
        self.timeout = timeout

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> dict:
        """Send a chat request to Ollama and return the JSON response."""
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'stream': False,
            'format': 'json',
            'options': {'temperature': temperature}
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f'{self.base_url}/api/chat', json=payload)
                resp.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaError(f'Ollama request failed: {e}') from e

        body = resp.json()
        content = body.get('message', {}).get('content', '').strip()
        if not content:
            raise OllamaError('Ollama returned an empty response')

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            # Occasionally the model wraps JSON in prose or code fences
            salvaged = _extract_json_block(content)
            if salvaged is not None:
                return salvaged
            raise OllamaError(f'Could not parse JSON from Ollama output: {e}\nRaw: {content[:500]}') from e

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f'{self.base_url}/api/tags')
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

def _extract_json_block(text: str) -> dict | None:
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end+1])
    except json.JSONDecodeError:
        return None