"""Model alias -> provider chain configuration, per PLAN.md Section 7.

Routing is static and config-driven (not ML-based, not adaptive) -- a
priority-ordered chain of {provider, model} entries per logical model alias,
loaded from model_aliases.yaml.
"""
from dataclasses import dataclass
from pathlib import Path

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "model_aliases.yaml"


@dataclass(frozen=True)
class ProviderChainEntry:
    provider: str
    model: str


class UnknownModelAliasError(Exception):
    def __init__(self, alias: str):
        super().__init__(f"Unknown model alias: {alias!r}")
        self.alias = alias


def load_model_aliases(path: Path = _DEFAULT_CONFIG_PATH) -> dict[str, list[ProviderChainEntry]]:
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    aliases: dict[str, list[ProviderChainEntry]] = {}
    for alias, chain in raw.get("model_aliases", {}).items():
        aliases[alias] = [ProviderChainEntry(provider=e["provider"], model=e["model"]) for e in chain]
    return aliases


MODEL_ALIASES: dict[str, list[ProviderChainEntry]] = load_model_aliases()


def resolve_chain(alias: str) -> list[ProviderChainEntry]:
    """Return the ordered provider/model chain for `alias`.

    Raises UnknownModelAliasError if the alias isn't configured.
    """
    try:
        return MODEL_ALIASES[alias]
    except KeyError:
        raise UnknownModelAliasError(alias) from None
