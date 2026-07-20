"""LLM client factory. Selects Ollama or Groq based on config."""

from app.config import settings


def create_llm_client():
    """Return an LLM client instance based on settings.llm_provider."""
    provider = settings.llm_provider.lower()

    if provider == 'groq':
        from app.services.groq_client import GroqClient
        return GroqClient()
    else:
        from app.services.ollama_client import OllamaClient
        return OllamaClient()
