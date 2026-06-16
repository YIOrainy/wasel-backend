"""End-to-end check for the Procrastinate expiry job against the live DB + worker.
Run: DATABASE_URL=...+psycopg...localhost... PYTHONPATH=. ./.venv/bin/python scripts/_check_worker.py
Proves: dispatcher enqueues atomically with create; defer -> worker -> task ->
service.expire -> status flip; and the guard (accepted/not-due survive).
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text, update

from app.db.base import AsyncSessionLocal
from app.db.models import Shipment, User
from app.db.models._enums import ShipmentStatus
from app.jobs.app import procrastinate_app
from app.schemas.shipment import ShipmentRequest
from app.services.shipments.dal import BidsDAL, ShipmentsDAL
from app.services.shipments.jobs import ShipmentExpiryDispatcher, expire_shipment
from app.services.shipments.service import ShipmentsService


def _req() -> ShipmentRequest:
    now = datetime.now(UTC)
    return ShipmentRequest(
        pickup_city="Riyadh", destination_city="Jeddah",
        pickup_lat=24.7, pickup_lng=46.7, destination_lat=21.5, destination_lng=39.2,
        receiver_phone_number=None, expected_pickup_time=now + timedelta(hours=2),
        expected_delivery_time=now + timedelta(hours=8), pickup_asap=False,
    )


async def mk_user(s, name) -> uuid.UUID:
    uid = uuid.uuid4()
    s.add(User(user_id=uid, name=name, phone_number=f"+{uuid.uuid4().int % 10**12}"))
    await s.commit()
    return uid


async def force_past_due(s, sid) -> None:
    await s.execute(
        update(Shipment).where(Shipment.shipment_id == sid)
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await s.commit()


async def jobs_for(sid) -> int:
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            text(
                "SELECT count(*) FROM procrastinate_jobs "
                "WHERE task_name='expire_shipment' AND args->>'shipment_id' = :sid"
            ),
            {"sid": str(sid)},
        )
        return r.scalar_one()


async def status_of(sid) -> ShipmentStatus:
    async with AsyncSessionLocal() as s:
        return (await s.get(Shipment, sid)).status


async def main() -> None:
    async with procrastinate_app.open_async():
        async with AsyncSessionLocal() as s:
            sender = await mk_user(s, "sender")
            cap = await mk_user(s, "cap")
            svc = ShipmentsService(s, ShipmentsDAL(s), BidsDAL(s))
            svc_disp = ShipmentsService(
                s, ShipmentsDAL(s), BidsDAL(s), ShipmentExpiryDispatcher()
            )

            # (0) dispatcher enqueues a job atomically with create
            d = (await svc_disp.create(sender_id=sender, data=_req())).shipment_id
            assert await jobs_for(d) == 1, "dispatcher should enqueue exactly one job"
            print("dispatcher enqueue (atomic with create): ok")

            # (A) pending + past-due -> expires via the worker
            a = (await svc.create(sender_id=sender, data=_req())).shipment_id
            await force_past_due(s, a)

            # (B) pending but NOT past-due -> guard: must survive
            b = (await svc.create(sender_id=sender, data=_req())).shipment_id

            # (C) accepted (then past-due) -> guard: must survive
            c = (await svc.create(sender_id=sender, data=_req())).shipment_id
            bid = await svc.place_bid(shipment_id=c, capitan_id=cap, price=Decimal("40"))
            await svc.accept_bid(shipment_id=c, bid_id=bid.bid_id, sender_id=sender)
            await force_past_due(s, c)

        # defer due-now expiry jobs for all three, run the worker until drained
        due = datetime.now(UTC) - timedelta(seconds=1)
        for sid in (a, b, c):
            await expire_shipment.configure(schedule_at=due).defer_async(shipment_id=str(sid))
        await procrastinate_app.run_worker_async(wait=False, install_signal_handlers=False)

        assert await status_of(a) == ShipmentStatus.EXPIRED, "A should be expired"
        print("worker chain: ok (pending + past-due -> expired)")
        assert await status_of(b) == ShipmentStatus.PENDING, "B must survive (not due)"
        print("guard (not due): ok (stayed pending)")
        assert await status_of(c) == ShipmentStatus.ACCEPTED, "C must survive (accepted)"
        print("guard (accepted): ok (stayed accepted — no cancel-on-accept needed)")
        print("\nALL WORKER CHECKS PASSED")


asyncio.run(main())
