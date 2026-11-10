"""``GET /api/market`` (SRS §5.3): the current snapshot, schema-shaped and camelCase.

``?refresh=1`` forces a rebuild behind a per-client cooldown (FR-16); a client that asks
too soon gets 429 with ``Retry-After``, which the UI turns into a disabled button.
"""

from __future__ import annotations

import math
import time

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.deps import ServiceDep, SettingsDep, StoreDep
from app.models import MarketSnapshot

router = APIRouter(tags=["market"])

#: client -> monotonic timestamp of its last forced refresh.
_last_refresh: dict[str, float] = {}


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _prune(now: float, cooldown: float) -> None:
    for key in [key for key, stamp in _last_refresh.items() if now - stamp > cooldown * 6]:
        del _last_refresh[key]


@router.get("/market", response_model=MarketSnapshot, summary="Latest market snapshot")
async def market(
    store: StoreDep,
    service: ServiceDep,
    settings: SettingsDep,
    request: Request,
    refresh: int = Query(default=0, description="1 forces a rebuild within the cooldown"),
) -> MarketSnapshot:
    if refresh:
        now = time.monotonic()
        cooldown = float(settings.refresh_cooldown_seconds)
        _prune(now, cooldown)
        key = _client_key(request)
        wait = cooldown - (now - _last_refresh.get(key, 0.0))
        if wait > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="refresh too soon",
                headers={"Retry-After": str(max(1, math.ceil(wait)))},
            )
        _last_refresh[key] = now
        await service.refresh(force=True)

    snapshot = store.current()
    if snapshot is None:
        # Cold start with nothing good yet (FR-18). Fabricating a snapshot is forbidden
        # (AGENTS.md rule 9), so the honest answer is "not yet" rather than a fake 200.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="no market snapshot has been built yet",
        )
    return snapshot
