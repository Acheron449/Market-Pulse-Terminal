"""Chart endpoints backing the datafeed adapter (FR-28, docs/tradingview.md §4).

All responses are camelCase; the adapter is the only place that speaks TradingView's
snake_case. History failures answer 502 so the library can keep its existing bars.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import ChartServiceDep, StoreDep
from app.providers.registry import AllProvidersFailed

router = APIRouter(prefix="/chart", tags=["chart"])


class BarModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class HistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    symbol: str
    resolution: str
    bars: list[BarModel]
    no_data: bool = Field(alias="noData")
    source: str
    status: str
    as_of: str = Field(alias="asOf")


@router.get("/config", summary="Datafeed configuration")
async def config(service: ChartServiceDep) -> dict[str, object]:
    return service.config()


@router.get("/symbols", summary="Symbol search")
async def symbols(
    service: ChartServiceDep, store: StoreDep, query: str = ""
) -> list[dict[str, str]]:
    snapshot = store.current()
    movers: list[str] = []
    if snapshot is not None:
        movers.extend(row.symbol for row in snapshot.gainers)
        movers.extend(row.symbol for row in snapshot.most_active)
    return service.search(query, movers)


@router.get("/symbols/{symbol}", summary="Symbol descriptor")
async def symbol_info(service: ChartServiceDep, symbol: str) -> dict[str, object]:
    info = service.symbol_info(symbol)
    if info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown symbol")
    return info


@router.get("/history", response_model=HistoryResponse, summary="Bars for a resolution")
async def history(
    service: ChartServiceDep,
    symbol: str,
    resolution: str,
    start: int = Query(alias="from", ge=0),
    end: int = Query(alias="to", ge=0),
    count_back: int = Query(default=300, alias="countBack", ge=2),
) -> HistoryResponse:
    try:
        payload = await service.history(symbol, resolution, start, end, count_back)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AllProvidersFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=[{"section": "chart", "message": str(exc)[:180]}],
        ) from exc
    return HistoryResponse.model_validate(payload)


@router.get("/time", summary="Server time in seconds")
async def server_time(service: ChartServiceDep) -> dict[str, int]:
    return {"time": service.server_time()}
