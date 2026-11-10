"""Registry failover, rate limiting and circuit breaking (FR-3, FR-4)."""

import asyncio
from typing import Any

import pytest

from app.core.config import Settings
from app.providers.base import ProviderError
from app.providers.registry import AllProvidersFailed, ProviderRegistry


class FakeProvider:
    """No network: every method is generated from the configured behaviour."""

    def __init__(
        self,
        name: str,
        capabilities: set[str],
        *,
        configured: bool = True,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        self.name = name
        self.capabilities = frozenset(capabilities)
        self._configured = configured
        self._result = result if result is not None else [{"symbol": "X"}]
        self._error = error
        self.calls = 0

    def is_configured(self) -> bool:
        return self._configured

    def __getattr__(self, item: str) -> Any:
        async def call(*args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            if self._error:
                raise ProviderError(self.name, item, self._error)
            return self._result

        return call


def settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        circuit_failure_threshold=2,
        circuit_cooldown_seconds=60,
        **overrides,
    )


def fetch(registry: ProviderRegistry, *args: Any) -> Any:
    return asyncio.run(registry.fetch("quotes", "quotes", *args))


def test_first_healthy_provider_wins() -> None:
    registry = ProviderRegistry(
        [FakeProvider("a", {"quotes"}), FakeProvider("b", {"quotes"})], settings()
    )

    result = fetch(registry, ["^GSPC"])

    assert result.provider == "a"


def test_failover_moves_to_the_next_provider() -> None:
    first = FakeProvider("a", {"quotes"}, error="boom")
    second = FakeProvider("b", {"quotes"})
    registry = ProviderRegistry([first, second], settings())

    result = fetch(registry, ["^GSPC"])

    assert result.provider == "b"
    states = {state.name: state for state in registry.states()}
    assert states["a"].failures == 1
    assert states["a"].last_error == "boom"


def test_circuit_opens_after_the_threshold_and_then_recovers() -> None:
    now = [0.0]
    failing = FakeProvider("a", {"quotes"}, error="boom")
    healthy = FakeProvider("b", {"quotes"})
    registry = ProviderRegistry([failing, healthy], settings(), clock=lambda: now[0])

    fetch(registry)
    fetch(registry)
    calls_after_open = failing.calls
    fetch(registry)

    assert failing.calls == calls_after_open  # skipped while the circuit is open
    states = {state.name: state for state in registry.states()}
    assert states["a"].circuit == "open"

    now[0] = 120.0  # past the cool-down: one half-open probe is allowed
    fetch(registry)
    assert failing.calls == calls_after_open + 1


def test_empty_payload_counts_as_failure() -> None:
    empty = FakeProvider("a", {"quotes"}, result=[])
    healthy = FakeProvider("b", {"quotes"})
    registry = ProviderRegistry([empty, healthy], settings())

    result = fetch(registry)

    assert result.provider == "b"
    assert "empty payload" in {state.name: state for state in registry.states()}["a"].last_error


def test_unconfigured_provider_is_skipped() -> None:
    unconfigured = FakeProvider("a", {"quotes"}, configured=False)
    healthy = FakeProvider("b", {"quotes"})
    registry = ProviderRegistry([unconfigured, healthy], settings())

    assert fetch(registry).provider == "b"
    assert unconfigured.calls == 0


def test_rate_limited_provider_fails_over() -> None:
    limited = FakeProvider("finnhub", {"quotes"})
    healthy = FakeProvider("b", {"quotes"})
    registry = ProviderRegistry(
        [limited, healthy],
        settings(finnhub_rate_per_minute=1, provider_order_indexes=["finnhub", "b"]),
    )

    assert fetch(registry).provider == "finnhub"
    assert fetch(registry).provider == "b"  # bucket exhausted, no sleeping


def test_every_provider_failing_raises() -> None:
    registry = ProviderRegistry([FakeProvider("a", {"quotes"}, error="boom")], settings())

    with pytest.raises(AllProvidersFailed) as excinfo:
        fetch(registry)
    assert "quotes" in str(excinfo.value)
    assert "boom" in str(excinfo.value)


def test_capability_order_ignores_unsupported_providers() -> None:
    news_only = FakeProvider("news", {"news"})
    quotes = FakeProvider("quotes", {"quotes"})
    registry = ProviderRegistry([news_only, quotes], settings())

    assert registry.providers_for("quotes") == ["quotes"]
