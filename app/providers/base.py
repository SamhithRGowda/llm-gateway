"""Provider abstraction: normalized request/response types and the
ProviderAdapter interface, per PLAN.md Section 6.

Each concrete adapter translates between this gateway-neutral shape and a
specific provider's API format, so the rest of the gateway never needs to
know which provider actually served a request.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class NormalizedRequest:
    messages: list[dict]
    max_tokens: int | None = None
    temperature: float | None = None


@dataclass
class NormalizedResponse:
    content: str
    input_tokens: int
    output_tokens: int
    raw_provider_model: str


class ProviderAdapter(ABC):
    name: str

    @abstractmethod
    def is_retryable_error(self, exc: Exception) -> bool:
        """Whether `exc` (raised by `send`) should be retried against this
        same provider."""
        ...

    @abstractmethod
    async def send(self, model: str, request: NormalizedRequest) -> NormalizedResponse:
        """Send `request` to `model` on this provider and return a
        NormalizedResponse, or raise a ProviderError subclass on failure."""
        ...
