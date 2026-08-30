"""Estimated cost calculation, per PLAN.md Section 10.

Loads pricing.yaml once at import time and exposes calculate_cost(). Pricing
is data (app/pricing/pricing.yaml), never hardcoded here.
"""
from decimal import Decimal
from pathlib import Path

import yaml

_DEFAULT_PRICING_PATH = Path(__file__).resolve().parent.parent / "pricing" / "pricing.yaml"


def _load_pricing(path: Path = _DEFAULT_PRICING_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


_PRICING = _load_pricing()


def calculate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Return the estimated cost in USD for a request, per app/pricing/pricing.yaml.

    Returns Decimal("0") if the provider/model isn't present in the pricing
    config (e.g. a new model not yet added to pricing.yaml), rather than
    raising, so cost tracking never breaks the chat endpoint.
    """
    model_pricing = _PRICING.get(provider, {}).get(model)
    if model_pricing is None:
        return Decimal("0")

    input_cost = Decimal(str(model_pricing["input_per_1k"])) * Decimal(input_tokens) / Decimal(1000)
    output_cost = Decimal(str(model_pricing["output_per_1k"])) * Decimal(output_tokens) / Decimal(1000)
    return input_cost + output_cost
