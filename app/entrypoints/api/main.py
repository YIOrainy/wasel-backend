import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.cache.base import close_redis, init_redis
from app.core.error_handlers import register_exception_handlers
from app.db.base import engine
from app.entrypoints.api import auth, saved_locations

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    await init_redis()
    try:
        yield
    finally:
        await close_redis()
        await engine.dispose()  # close the connection pool cleanly


app = FastAPI(title="Wasel", version="0.1.0", lifespan=lifespan)

register_exception_handlers(app)
app.include_router(auth.router, prefix="/api")
app.include_router(saved_locations.router, prefix="/api")
