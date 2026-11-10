"""FastAPI application entry point: `uv run uvicorn app.main:app --reload --port 8000`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.chart import router as chart_router
from app.api.config import router as config_router
from app.api.health import router as health_router
from app.api.market import router as market_router
from app.api.stream import router as stream_router
from app.core.cache import SnapshotCache
from app.core.config import REPO_ROOT, get_settings
from app.core.scheduler import SnapshotScheduler
from app.providers.factory import build_registry
from app.services.chart_service import ChartService
from app.services.event_bus import EventBus
from app.services.market_hours import DEFAULT_CALENDAR
from app.services.replay import load_replay_snapshot
from app.services.snapshot_service import SnapshotService
from app.services.snapshot_store import SnapshotStore

logger = logging.getLogger(__name__)

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def create_app(*, seed_replay: bool = True, start_scheduler: bool | None = None) -> FastAPI:
    """Build the application. A factory keeps tests from sharing global state.

    ``seed_replay`` fills the store from the recorded provider payload outside production
    so the dashboard has something contract-valid to show before live data is enabled. The
    scheduler only runs when ``ENABLE_LIVE_DATA`` is on: replay mode is not refreshed.
    """
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    store = SnapshotStore()
    bus = EventBus()
    cache = SnapshotCache(settings.database_path)
    registry = build_registry(settings)
    service = SnapshotService(settings, registry, store, bus, cache, DEFAULT_CALENDAR)
    chart_service = ChartService(settings, registry, DEFAULT_CALENDAR)
    scheduler = SnapshotScheduler(service, settings)
    should_schedule = settings.enable_live_data if start_scheduler is None else start_scheduler

    if seed_replay:
        replay = load_replay_snapshot(settings)
        if replay is not None:
            store.replace(replay)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # FR-18: serve the persisted last-good snapshot immediately, then refresh.
        persisted = await cache.load()
        if store.current() is None and persisted is not None:
            store.replace(persisted)
        if should_schedule:
            scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()
            await registry.aclose()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.state.snapshot_store = store
    application.state.event_bus = bus
    application.state.snapshot_service = service
    application.state.chart_service = chart_service
    application.state.registry = registry

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    application.include_router(health_router, prefix="/api")
    application.include_router(market_router, prefix="/api")
    application.include_router(stream_router, prefix="/api")
    application.include_router(config_router, prefix="/api")
    application.include_router(chart_router, prefix="/api")

    _mount_static(application)
    return application


def _mount_static(application: FastAPI) -> None:
    """Serve a built SPA when it exists, so one container can host the whole app."""
    dist = Path(FRONTEND_DIST)
    if dist.is_dir() and (dist / "index.html").is_file():
        application.mount("/", StaticFiles(directory=dist, html=True), name="frontend")


app = create_app()
