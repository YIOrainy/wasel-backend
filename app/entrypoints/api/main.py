import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.cache.base import close_redis, init_redis
from app.core.error_handlers import register_exception_handlers
from app.db.base import engine
from app.entrypoints.api import (
    auth,
    bids,
    devices,
    events,
    health,
    saved_locations,
    shipments,
)
from app.jobs.app import procrastinate_app

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    await init_redis()
    # Open the Procrastinate connector so endpoints can defer jobs (the worker
    # process runs separately). Does not run jobs here — only enqueues them.
    async with procrastinate_app.open_async():
        try:
            yield
        finally:
            await close_redis()
            await engine.dispose()  # close the connection pool cleanly


app = FastAPI(title="Wasel", version="0.1.0", lifespan=lifespan)

register_exception_handlers(app)
app.include_router(health.router)  # /healthz, /readyz — no /api prefix
app.include_router(auth.router, prefix="/api")
app.include_router(saved_locations.router, prefix="/api")
app.include_router(shipments.router, prefix="/api")
app.include_router(bids.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(devices.router, prefix="/api")
