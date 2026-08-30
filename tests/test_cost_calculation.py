from decimal import Decimal

from app.usage.cost_calculator import calculate_cost


def test_calculate_cost_openai_gpt4o_mini():
    # pricing.yaml: gpt-4o-mini input_per_1k=0.00015, output_per_1k=0.0006
    cost = calculate_cost("openai", "gpt-4o-mini", input_tokens=1000, output_tokens=1000)
    assert cost == Decimal("0.00015") + Decimal("0.0006")


def test_calculate_cost_groq_llama():
    # pricing.yaml: llama-3.1-8b-instant input_per_1k=0.00005, output_per_1k=0.00008
    cost = calculate_cost("groq", "llama-3.1-8b-instant", input_tokens=500, output_tokens=200)
    expected = (Decimal("0.00005") * 500 / 1000) + (Decimal("0.00008") * 200 / 1000)
    assert cost == expected


def test_calculate_cost_zero_tokens_is_zero():
    cost = calculate_cost("openai", "gpt-4o-mini", input_tokens=0, output_tokens=0)
    assert cost == Decimal("0")


def test_calculate_cost_unknown_model_returns_zero_not_error():
    cost = calculate_cost("openai", "some-future-model-not-in-pricing-yaml", input_tokens=100, output_tokens=100)
    assert cost == Decimal("0")


def test_calculate_cost_unknown_provider_returns_zero_not_error():
    cost = calculate_cost("unknown-provider", "some-model", input_tokens=100, output_tokens=100)
    assert cost == Decimal("0")
