"""``GET /api/stream``: Server-Sent Events with a snapshot on connect (FR-14).

Heartbeat every 15 s keeps proxies and mobile networks from closing an idle connection.
The frontend falls back to polling when this stream is unavailable (FR-15).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import BusDep, StoreDep
from app.models import MarketSnapshot

router = APIRouter(tags=["stream"])

HEARTBEAT_SECONDS = 15


def _event(name: str, snapshot: MarketSnapshot) -> bytes:
    payload = json.dumps(snapshot.model_dump(mode="json"), separators=(",", ":"))
    return f"event: {name}\ndata: {payload}\n\n".encode()


@router.get("/stream", summary="Snapshot push stream")
async def stream(request: Request, store: StoreDep, bus: BusDep) -> StreamingResponse:
    async def events() -> AsyncIterator[bytes]:
        queue = bus.subscribe()
        try:
            current = store.current()
            if current is not None:
                yield _event("snapshot", current)
            while True:
                if await request.is_disconnected():
                    return
                try:
                    snapshot = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield b": heartbeat\n\n"
                    continue
                yield _event("snapshot", snapshot)
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # nginx would otherwise buffer the stream into uselessness.
            "X-Accel-Buffering": "no",
        },
    )
