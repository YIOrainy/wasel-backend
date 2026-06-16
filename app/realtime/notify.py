"""The one delivery seam. Domain code calls notify(); transport (SSE when the
user has a live stream, else an Expo push) lives behind it. Best-effort: never
raises into the caller — a failed notification must not fail the business op."""

import logging
import uuid
from typing import Any

from app.realtime import presence

log = logging.getLogger(__name__)


async def notify(user_id: uuid.UUID, event_type: str, payload: dict[str, Any]) -> None:
    msg = {"type": event_type, **payload}
    streams = presence.streams_for(user_id)
    if streams:
        for queue in streams:
            queue.put_nowait(msg)  # unbounded queue → never blocks/raises
    else:
        await _push_fallback(user_id, msg)


async def notify_request_feed(event_type: str, payload: dict[str, Any]) -> None:
    msg = {"type": event_type, **payload}
    for queue in presence.request_feed():
        queue.put_nowait(msg)


async def _push_fallback(user_id: uuid.UUID, msg: dict[str, Any]) -> None:
    """User has no live stream → enqueue an Expo push (non-blocking + retryable).
    Lazy import keeps this module free of the jobs/worker graph. Best-effort: a
    failed enqueue is logged, never propagated — a missed push must not fail the
    business operation that triggered it."""
    from app.services.devices.jobs import send_push

    try:
        await send_push.defer_async(user_id=str(user_id), msg=msg)
    except Exception:
        log.exception(
            "failed to enqueue push: user=%s event=%s", user_id, msg.get("type")
        )
