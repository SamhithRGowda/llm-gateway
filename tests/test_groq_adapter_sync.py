from app.providers.errors import FatalProviderError, ProviderRateLimitedError, RetryableProviderError
from app.providers.groq_adapter import GROQ_BASE_URL, GroqAdapter


def test_groq_adapter_name_and_base_url():
    adapter = GroqAdapter(api_key="test-key")
    assert adapter.name == "groq"
    assert adapter._base_url == GROQ_BASE_URL


def test_is_retryable_error_classification():
    adapter = GroqAdapter(api_key="test-key")
    assert adapter.is_retryable_error(RetryableProviderError("x")) is True
    assert adapter.is_retryable_error(ProviderRateLimitedError("x")) is True
    assert adapter.is_retryable_error(FatalProviderError("x")) is False
    assert adapter.is_retryable_error(ValueError("x")) is False


def test_adapter_reads_api_key_from_settings_by_default(monkeypatch):
    monkeypatch.setattr("app.providers.groq_adapter.settings.groq_api_key", "groq-from-settings")
    adapter = GroqAdapter()
    assert adapter._api_key == "groq-from-settings"
