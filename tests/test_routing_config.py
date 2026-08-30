import pytest

from app.routing.config import ProviderChainEntry, UnknownModelAliasError, resolve_chain


def test_resolve_known_alias_returns_ordered_chain():
    chain = resolve_chain("fast-cheap")
    assert chain == [
        ProviderChainEntry(provider="groq", model="llama-3.1-8b-instant"),
        ProviderChainEntry(provider="openai", model="gpt-4o-mini"),
    ]


def test_resolve_balanced_alias_prefers_openai_first():
    chain = resolve_chain("balanced")
    assert chain[0].provider == "openai"
    assert chain[1].provider == "groq"


def test_resolve_premium_alias_is_openai_only():
    chain = resolve_chain("premium")
    assert len(chain) == 1
    assert chain[0].provider == "openai"
    assert chain[0].model == "gpt-4o"


def test_resolve_unknown_alias_raises():
    with pytest.raises(UnknownModelAliasError):
        resolve_chain("does-not-exist")
