"""``GET /api/health`` (SRS §5.3): provider circuits, per-section freshness, build info.

This is the endpoint the runbook uses to prove failover works and to see which section is
stale, so it reports provider state even when every provider has failed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import RegistryDep, SettingsDep, StoreDep

router = APIRouter(tags=["health"])


class ProviderState(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    name: str
    circuit: str
    calls: int
    failures: int
    skipped: int
    last_success_at: str | None = Field(default=None, alias="lastSuccessAt")
    last_error: str | None = Field(default=None, alias="lastError")
    remaining_tokens: float = Field(default=0.0, alias="remainingTokens")


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    status: Literal["ok", "degraded"] = "ok"
    service: str
    version: str
    schema_version: int = Field(default=1, alias="schemaVersion")
    mode: Literal["live", "replay"] = "replay"
    last_refresh_at: str | None = Field(default=None, alias="lastRefreshAt")
    section_age_seconds: int | None = Field(default=None, alias="sectionAgeSeconds")
    sections: dict[str, str] = Field(default_factory=dict)
    providers: list[ProviderState] = Field(default_factory=list)


@router.get("/health", response_model=HealthResponse, summary="Liveness, providers and freshness")
async def health(store: StoreDep, registry: RegistryDep, settings: SettingsDep) -> HealthResponse:
    snapshot = store.current()
    age: int | None = None
    if snapshot is not None:
        try:
            fetched = datetime.fromisoformat(snapshot.fetched_at.replace("Z", "+00:00"))
            age = max(0, int((datetime.now(UTC) - fetched).total_seconds()))
        except ValueError:  # pragma: no cover - contract pattern makes this unreachable
            age = None

    states = [
        ProviderState(
            name=state.name,
            circuit=state.circuit,
            calls=state.calls,
            failures=state.failures,
            skipped=state.skipped,
            last_success_at=state.last_success_at,
            last_error=state.last_error,
            remaining_tokens=state.remaining_tokens,
        )
        for state in registry.states()
    ]
    sections = dict(snapshot.status) if snapshot is not None else {}
    degraded = snapshot is None or any(value == "error" for value in sections.values())
    return HealthResponse(
        status="degraded" if degraded else "ok",
        service=settings.app_name,
        version=settings.app_version,
        mode="live" if settings.enable_live_data else "replay",
        last_refresh_at=snapshot.fetched_at if snapshot is not None else None,
        section_age_seconds=age,
        sections=sections,
        providers=states,
    )
