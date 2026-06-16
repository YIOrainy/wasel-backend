"""Shipment background jobs: the expiry task + the enqueue dispatcher."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal
from app.db.models import Shipment
from app.jobs.app import procrastinate_app
from app.realtime.notify import notify
from app.services.shipments.dal import BidsDAL, ShipmentsDAL
from app.services.shipments.service import ShipmentsService


@procrastinate_app.task(name="expire_shipment", queue="shipments")
async def expire_shipment(shipment_id: str) -> None:
    async with AsyncSessionLocal() as session:
        service = ShipmentsService(session, ShipmentsDAL(session), BidsDAL(session))
        sender_id = await service.expire(UUID(shipment_id))
        if sender_id is not None:
            await notify(sender_id, "shipment_expired", {"shipment_id": shipment_id})


class ShipmentExpiryDispatcher:
    """Enqueues the expiry job on the SAME DB connection as the shipment write,
    so the job row and the shipment commit atomically — no separate-commit
    window. Borrowing the session's psycopg connection also means the API never
    needs the Procrastinate connector pool just to defer."""

    async def enqueue_expiry(self, session: AsyncSession, shipment: Shipment) -> None:
        job = expire_shipment.configure(
            schedule_at=shipment.expires_at
        ).make_new_job(shipment_id=str(shipment.shipment_id))
        connection = await session.connection()
        raw = await connection.get_raw_connection()
        await procrastinate_app.job_manager.defer_job_async(
            job, connection=raw.driver_connection
        )
