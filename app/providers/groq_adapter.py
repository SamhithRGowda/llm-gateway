"""Groq provider adapter.

Per PLAN.md Section 6: "Because Groq's chat completions API is
OpenAI-compatible, GroqAdapter can subclass or heavily reuse OpenAIAdapter's
HTTP logic with a different base URL/model list." This adapter subclasses
OpenAIAdapter unchanged, swapping only the base URL and the API key source.
"""
from app.config import settings
from app.providers.openai_adapter import DEFAULT_TIMEOUT_SECONDS, OpenAIAdapter

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqAdapter(OpenAIAdapter):
    name = "groq"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = GROQ_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        super().__init__(
            api_key=api_key if api_key is not None else settings.groq_api_key,
            base_url=base_url,
            timeout=timeout,
        )
