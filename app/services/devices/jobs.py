"""Device background jobs: the Expo push-send task."""

from uuid import UUID

import httpx
from procrastinate import RetryStrategy

from app.db.base import AsyncSessionLocal
from app.integrations import expo
from app.jobs.app import procrastinate_app
from app.services.devices.dal import DevicesDAL
from app.services.devices.service import DevicesService

# Retry only transient transport failures (network/5xx). A bad payload (4xx) or
# any other error won't be retried.
RETRY = RetryStrategy(max_attempts=3, exponential_wait=2, retry_exceptions=[httpx.HTTPError])


@procrastinate_app.task(name="send_push", queue="push", retry=RETRY)
async def send_push(user_id: str, msg: dict) -> None:
    """Push an event to a user's devices via Expo. Loads their tokens, sends,
    and prunes any the gateway reports as dead. No-op if the user has no tokens
    (e.g. they declined notification permission)."""
    async with AsyncSessionLocal() as session:
        service = DevicesService(session, DevicesDAL(session))
        devices = await service.tokens_for(UUID(user_id))
        tokens = [d.fcm_token for d in devices]
        if not tokens:
            return

        messages = expo.build_messages(tokens, msg["type"], msg)
        tickets = await expo.push(messages)  # raises httpx.HTTPError → retried

        for token in expo.dead_tokens(tickets, tokens):
            await service.unregister(user_id=UUID(user_id), fcm_token=token)
