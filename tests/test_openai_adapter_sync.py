from app.providers.errors import FatalProviderError, ProviderRateLimitedError, RetryableProviderError
from app.providers.openai_adapter import OpenAIAdapter


def test_is_retryable_error_classification():
    adapter = OpenAIAdapter(api_key="test-key")
    assert adapter.is_retryable_error(RetryableProviderError("x")) is True
    assert adapter.is_retryable_error(ProviderRateLimitedError("x")) is True
    assert adapter.is_retryable_error(FatalProviderError("x")) is False
    assert adapter.is_retryable_error(ValueError("x")) is False


def test_adapter_reads_api_key_from_settings_by_default(monkeypatch):
    monkeypatch.setattr("app.providers.openai_adapter.settings.openai_api_key", "from-settings")
    adapter = OpenAIAdapter()
    assert adapter._api_key == "from-settings"
