"""``GET /api/config``: non-secret flags for the UI (SRS §7.1).

Nothing here can leak a credential; the frontend uses it for the refresh cooldown, the
chart engine switch and the optional TradingView widget flag.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SettingsDep

router = APIRouter(tags=["config"])


class UiConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True, extra="forbid")

    schema_version: int = Field(default=1, alias="schemaVersion")
    refresh_cooldown_seconds: int = Field(alias="refreshCooldownSeconds")
    polling_fallback_seconds: int = Field(default=30, alias="pollingFallbackSeconds")
    chart_engine: str = Field(alias="chartEngine")
    chart_resolutions: list[str] = Field(alias="chartResolutions")
    enable_tradingview_widget: bool = Field(alias="enableTradingViewWidget")
    live_data_enabled: bool = Field(alias="liveDataEnabled")
    disclaimer: str = (
        "Informational only. Not investment advice. Data may be delayed; check the feed "
        "disclosure in the footer."
    )


@router.get("/config", response_model=UiConfig, summary="Non-secret UI flags")
async def config(settings: SettingsDep) -> UiConfig:
    return UiConfig(
        refresh_cooldown_seconds=settings.refresh_cooldown_seconds,
        chart_engine=settings.chart_engine,
        chart_resolutions=settings.chart_resolutions,
        enable_tradingview_widget=settings.enable_tradingview_widget,
        live_data_enabled=settings.enable_live_data,
    )
