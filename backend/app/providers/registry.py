"""Provider registry: capability routing, ordered failover, token buckets, circuit breakers.

FR-3/FR-4 and `AGENTS.md` rule 3 live here. Routes and services call ``registry.fetch``
and never touch an adapter, so failover, rate limiting and failure accounting cannot be
bypassed. The registry does not retry inside a provider: a failed call moves to the next
provider in the documented order, which is what keeps a provider hiccup from becoming a
retry storm against a free tier.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.providers.base import Capability, MarketDataProvider, ProviderError

logger = logging.getLogger(__name__)

ORDER_FIELDS: Mapping[Capability, str] = {
    "quotes": "provider_order_indexes",
    "movers": "provider_order_movers",
    "status": "provider_order_status",
    "news": "provider_order_news",
    "history": "provider_order_indexes",
}


class AllProvidersFailed(RuntimeError):
    """Every provider for a capability failed, was rate-limited, or is unconfigured."""

    def __init__(self, capability: Capability, reasons: Mapping[str, str]) -> None:
        detail = "; ".join(f"{name}: {reason}" for name, reason in reasons.items())
        super().__init__(f"no provider served {capability} ({detail or 'none configured'})")
        self.capability = capability
        self.reasons = dict(reasons)


@dataclass(slots=True)
class ProviderHealth:
    """Everything `/api/health` needs to prove failover is working (SRS §7.1)."""

    name: str
    calls: int = 0
    failures: int = 0
    skipped: int = 0
    last_success_at: str | None = None
    last_error: str | None = None
    circuit: str = "closed"
    remaining_tokens: float = 0.0


class TokenBucket:
    """A conservative per-provider budget: 70% of the documented quota by default."""

    def __init__(
        self,
        rate_per_minute: int,
        *,
        burst: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rate_per_second = max(rate_per_minute, 1) / 60.0
        self._capacity = float(burst if burst is not None else max(1, rate_per_minute // 10))
        self._tokens = self._capacity
        self._updated = clock()
        self._clock = clock

    def try_take(self) -> bool:
        now = self._clock()
        self._tokens = min(
            self._capacity, self._tokens + (now - self._updated) * self._rate_per_second
        )
        self._updated = now
        if self._tokens < 1.0:
            return False
        self._tokens -= 1.0
        return True

    @property
    def remaining(self) -> float:
        return round(self._tokens, 2)


class CircuitBreaker:
    """Closed → open after N consecutive failures → half-open probe after a cool-down."""

    def __init__(
        self,
        *,
        threshold: int = 3,
        cooldown_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open = False

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self._half_open:
            return "half_open"
        if self._clock() - self._opened_at >= self._cooldown:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        state = self.state
        if state == "closed":
            return True
        if state == "open":
            return False
        # Half-open: let exactly one probe through until it resolves.
        self._half_open = True
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._half_open = False

    def record_failure(self) -> None:
        self._failures += 1
        if self._half_open:
            # The probe failed: stay open for another cool-down.
            self._opened_at = self._clock()
            self._half_open = False
            return
        if self._failures >= self._threshold:
            self._opened_at = self._clock()
            self._half_open = False


@dataclass(frozen=True, slots=True)
class FetchResult:
    """A successful provider response together with the provider that served it."""

    provider: str
    value: Any


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProviderRegistry:
    """Routes each capability through the configured order, failing over on error."""

    def __init__(
        self,
        providers: Sequence[MarketDataProvider],
        settings: Settings,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._providers = {provider.name: provider for provider in providers}
        self._settings = settings
        self._clock = clock
        self._health = {name: ProviderHealth(name) for name in self._providers}
        self._buckets: dict[str, TokenBucket] = {}
        self._breakers: dict[str, CircuitBreaker] = {}
        for name in self._providers:
            rate = self._rate_for(name)
            self._buckets[name] = TokenBucket(rate, clock=clock)
            self._breakers[name] = CircuitBreaker(
                threshold=settings.circuit_failure_threshold,
                cooldown_seconds=settings.circuit_cooldown_seconds,
                clock=clock,
            )

    # -- introspection ---------------------------------------------------------
    def _rate_for(self, name: str) -> int:
        if name == "alpaca":
            return self._settings.alpaca_rate_per_minute
        if name == "finnhub":
            return self._settings.finnhub_rate_per_minute
        if name == "yfinance":
            # No published quota: the politeness rule is one call per interval.
            return max(1, 60 // max(1, self._settings.yfinance_min_interval_seconds))
        # Local or test providers are not rate limited beyond a sane default.
        return 60

    def order(self, capability: Capability) -> list[str]:
        configured: list[str] = getattr(self._settings, ORDER_FIELDS[capability])
        # Anything that supports the capability but was left out still gets a chance,
        # so adding a provider cannot silently drop a section.
        remaining = sorted(
            name
            for name, provider in self._providers.items()
            if capability in provider.capabilities and name not in configured
        )
        return [*configured, *remaining]

    def providers_for(self, capability: Capability) -> list[str]:
        return [
            name
            for name in self.order(capability)
            if name in self._providers and capability in self._providers[name].capabilities
        ]

    def states(self) -> list[ProviderHealth]:
        for name, breaker in self._breakers.items():
            health = self._health[name]
            health.circuit = breaker.state
            health.remaining_tokens = self._buckets[name].remaining
        return sorted(self._health.values(), key=lambda item: item.name)

    def configured(self) -> list[str]:
        return [name for name, p in self._providers.items() if p.is_configured()]

    async def aclose(self) -> None:
        """Close any provider-owned HTTP clients on shutdown."""
        for provider in self._providers.values():
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()

    # -- the only way to reach a provider --------------------------------------
    async def fetch(
        self, capability: Capability, method: str, *args: Any, **kwargs: Any
    ) -> FetchResult:
        reasons: dict[str, str] = {}
        for name in self.providers_for(capability):
            provider = self._providers[name]
            health = self._health[name]
            breaker = self._breakers[name]

            if not provider.is_configured():
                health.skipped += 1
                reasons[name] = "not configured"
                continue
            if not breaker.allow():
                health.skipped += 1
                reasons[name] = f"circuit {breaker.state}"
                continue
            if not self._buckets[name].try_take():
                health.skipped += 1
                reasons[name] = "rate limited"
                continue

            health.calls += 1
            try:
                value = await getattr(provider, method)(*args, **kwargs)
            except ProviderError as exc:
                self._fail(name, exc.reason)
                reasons[name] = exc.reason
                continue
            except Exception as exc:  # noqa: BLE001 - adapters raise vendor errors
                # Never log the exception text: it can carry URLs with keys in them.
                reason = type(exc).__name__
                self._fail(name, reason)
                reasons[name] = reason
                continue

            if value is None or (isinstance(value, (list, tuple, dict)) and not value):
                self._fail(name, "empty payload")
                reasons[name] = "empty payload"
                continue

            breaker.record_success()
            health.last_success_at = _now_iso()
            health.last_error = None
            return FetchResult(provider=name, value=value)

        raise AllProvidersFailed(capability, reasons)

    def _fail(self, name: str, reason: str) -> None:
        self._health[name].failures += 1
        self._health[name].last_error = reason
        self._breakers[name].record_failure()
        logger.warning("provider %s failed: %s", name, reason)
