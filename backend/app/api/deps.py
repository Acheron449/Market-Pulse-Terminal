"""Shared FastAPI dependencies, read from application state."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.providers.registry import ProviderRegistry
from app.services.chart_service import ChartService
from app.services.event_bus import EventBus
from app.services.snapshot_service import SnapshotService
from app.services.snapshot_store import SnapshotStore


def get_store(request: Request) -> SnapshotStore:
    store: SnapshotStore = request.app.state.snapshot_store
    return store


def get_service(request: Request) -> SnapshotService:
    service: SnapshotService = request.app.state.snapshot_service
    return service


def get_bus(request: Request) -> EventBus:
    bus: EventBus = request.app.state.event_bus
    return bus


def get_registry(request: Request) -> ProviderRegistry:
    registry: ProviderRegistry = request.app.state.registry
    return registry


def get_chart_service(request: Request) -> ChartService:
    service: ChartService = request.app.state.chart_service
    return service


def get_app_settings() -> Settings:
    return get_settings()


StoreDep = Annotated[SnapshotStore, Depends(get_store)]
ServiceDep = Annotated[SnapshotService, Depends(get_service)]
BusDep = Annotated[EventBus, Depends(get_bus)]
RegistryDep = Annotated[ProviderRegistry, Depends(get_registry)]
ChartServiceDep = Annotated[ChartService, Depends(get_chart_service)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
