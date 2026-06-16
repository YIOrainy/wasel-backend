import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.entrypoints.api.deps import CurrentUser
from app.realtime import presence

router = APIRouter(tags=["events"])

HEARTBEAT_SECONDS = 15


@router.get("/events")
async def events(user: CurrentUser, feed: str | None = None) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()
    presence.connect(user.user_id, queue)
    if feed == "requests" and user.is_captain:
        presence.join_request_feed(queue)

    async def stream():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                # default=str: payloads carry UUID / Decimal / datetime
                yield f"data: {json.dumps(msg, default=str)}\n\n"
        finally:
            presence.disconnect(user.user_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx response buffering for SSE
        },
    )
