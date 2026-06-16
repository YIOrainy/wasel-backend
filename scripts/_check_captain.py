"""Check captain-side additions: list_my_bids (+status) and get_viewable_shipment
allowing a captain to view an open (pending) shipment. Run against a throwaway DB.
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.exceptions import NotFoundError
from app.db.base import AsyncSessionLocal
from app.db.models import CapitanProfile, User
from app.db.models._enums import BidStatus
from app.entrypoints.api.deps import get_viewable_shipment
from app.schemas.shipment import ShipmentRequest
from app.services.shipments.dal import BidsDAL, ShipmentsDAL
from app.services.shipments.service import ShipmentsService
from app.services.users.dal import UsersDAL


async def mk_user(s, name) -> uuid.UUID:
    uid = uuid.uuid4()
    s.add(User(user_id=uid, name=name, phone_number=f"+{uuid.uuid4().int % 10**12}"))
    await s.commit()
    return uid


async def mk_captain(s, name) -> User:
    uid = await mk_user(s, name)
    s.add(CapitanProfile(capitan_profile_id=uuid.uuid4(), user_id=uid))
    await s.commit()
    return await UsersDAL(s).get_by_id(uid)  # loaded with capitan_profile → is_captain


def _req() -> ShipmentRequest:
    now = datetime.now(UTC)
    return ShipmentRequest(
        pickup_city="Riyadh", destination_city="Jeddah",
        pickup_lat=24.7, pickup_lng=46.7, destination_lat=21.5, destination_lng=39.2,
        expected_pickup_time=now + timedelta(hours=2),
        expected_delivery_time=now + timedelta(hours=8),
    )


async def main() -> None:
    async with AsyncSessionLocal() as s:
        svc = ShipmentsService(s, ShipmentsDAL(s), BidsDAL(s))
        sender = await mk_user(s, "sender")
        cap = await mk_captain(s, "cap")
        cap2 = await mk_captain(s, "cap2")

        a = (await svc.create(sender_id=sender, data=_req())).shipment_id
        b = (await svc.create(sender_id=sender, data=_req())).shipment_id
        await svc.place_bid(shipment_id=a, capitan_id=cap.user_id, price=Decimal("10"))
        await svc.place_bid(shipment_id=b, capitan_id=cap.user_id, price=Decimal("20"))

        mine = await svc.list_my_bids(cap.user_id)
        assert {x.shipment_id for x in mine} == {a, b}
        assert mine[0].created_at >= mine[1].created_at, "newest first"
        print("list_my_bids: ok (both, newest first)")

        bid_a = next(x for x in mine if x.shipment_id == a)
        await svc.accept_bid(shipment_id=a, bid_id=bid_a.bid_id, sender_id=sender)
        assert {x.shipment_id for x in await svc.list_my_bids(cap.user_id, BidStatus.ACCEPTED)} == {a}
        assert {x.shipment_id for x in await svc.list_my_bids(cap.user_id, BidStatus.PENDING)} == {b}
        print("list_my_bids status filter: ok")

        # browsing captain can view an open (pending) shipment they're not party to
        assert (await get_viewable_shipment(b, cap2, ShipmentsDAL(s))).shipment_id == b
        print("captain views pending shipment (not party): ok")

        # non-captain non-party → 404
        rando = await UsersDAL(s).get_by_id(await mk_user(s, "rando"))
        try:
            await get_viewable_shipment(b, rando, ShipmentsDAL(s))
            raise SystemExit("FAIL: non-party non-captain should 404")
        except NotFoundError:
            print("non-party non-captain 404: ok")

        # captain can't view a non-pending shipment they're not party to (a is accepted)
        try:
            await get_viewable_shipment(a, cap2, ShipmentsDAL(s))
            raise SystemExit("FAIL: captain viewing non-pending non-own should 404")
        except NotFoundError:
            print("captain cannot view non-pending non-own: ok")

        print("\nALL CAPTAIN CHECKS PASSED")


asyncio.run(main())
