from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.cache.base import get_redis
from app.db.base import engine

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness — the process is up. No dependency checks: a DB/Redis outage must
    not cause the orchestrator to restart a healthy process (that's readiness)."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> JSONResponse:
    """Readiness — can we actually serve? Checks the backing services. 503 if any
    is down → orchestrator stops routing traffic until it recovers."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:
        checks["db"] = "down"
        healthy = False

    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "down"
        healthy = False

    code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=code,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )
