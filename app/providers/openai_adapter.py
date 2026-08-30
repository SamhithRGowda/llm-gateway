"""OpenAI provider adapter.

Translates between the gateway's NormalizedRequest/NormalizedResponse and
OpenAI's Chat Completions API. Uses a plain httpx call rather than the
official SDK to keep the dependency footprint minimal (per PLAN.md's
general "don't over-engineer" guidance) -- Groq's adapter (Phase 3) can
reuse this same HTTP shape since Groq's API is OpenAI-compatible.
"""
import httpx

from app.config import settings
from app.providers.base import NormalizedRequest, NormalizedResponse, ProviderAdapter
from app.providers.errors import FatalProviderError, ProviderRateLimitedError, RetryableProviderError

OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0


class OpenAIAdapter(ProviderAdapter):
    name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str = OPENAI_BASE_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._base_url = base_url
        self._timeout = timeout

    def is_retryable_error(self, exc: Exception) -> bool:
        return isinstance(exc, RetryableProviderError)

    async def send(self, model: str, request: NormalizedRequest) -> NormalizedResponse:
        payload: dict = {"model": model, "messages": request.messages}
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.post("/chat/completions", json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise RetryableProviderError(f"{self.name} request failed: {exc}") from exc

        self._raise_for_status(response)

        body = response.json()
        choice = body["choices"][0]
        usage = body.get("usage", {})

        return NormalizedResponse(
            content=choice["message"]["content"],
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            raw_provider_model=body.get("model", model),
        )

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise ProviderRateLimitedError(
                f"{self.name} rate limited (429): {response.text}",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if response.status_code >= 500:
            raise RetryableProviderError(f"{self.name} server error ({response.status_code}): {response.text}")
        # 400/401/403/404 and any other 4xx: not retryable
        raise FatalProviderError(f"{self.name} request error ({response.status_code}): {response.text}")
