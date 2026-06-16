"""Throwaway self-check for the shipment bidding service against the live DB.
Run: DATABASE_URL=...localhost... ./.venv/bin/python scripts/_check_shipments.py
Exercises the money/state path: create -> bid -> bid -> accept -> races.
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.exceptions import NotFoundError, ShipmentNotAcceptableError
from app.db.base import AsyncSessionLocal
from app.db.models import User
from app.db.models._enums import BidStatus, ShipmentStatus
from app.schemas.shipment import ShipmentRequest
from app.services.shipments.dal import BidsDAL, ShipmentsDAL
from app.services.shipments.service import ShipmentsService


async def mk_user(session, name) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(User(user_id=uid, name=name, phone_number=f"+{uuid.uuid4().int % 10**12}"))
    await session.commit()
    return uid


def _req() -> ShipmentRequest:
    now = datetime.now(UTC)
    return ShipmentRequest(
        pickup_city="Riyadh", destination_city="Jeddah",
        pickup_lat=24.7, pickup_lng=46.7, destination_lat=21.5, destination_lng=39.2,
        receiver_phone_number=None, expected_pickup_time=now + timedelta(hours=2),
        expected_delivery_time=now + timedelta(hours=8), pickup_asap=False,
    )


async def main() -> None:
    async with AsyncSessionLocal() as s:
        svc = ShipmentsService(s, ShipmentsDAL(s), BidsDAL(s))
        sender = await mk_user(s, "sender")
        cap1 = await mk_user(s, "cap1")
        cap2 = await mk_user(s, "cap2")

        now = datetime.now(UTC)
        ship = await svc.create(sender_id=sender, data=ShipmentRequest(
            pickup_city="Riyadh", destination_city="Jeddah",
            pickup_lat=24.7, pickup_lng=46.7, destination_lat=21.5, destination_lng=39.2,
            receiver_phone_number=None, expected_pickup_time=now + timedelta(hours=2),
            expected_delivery_time=now + timedelta(hours=8), pickup_asap=False,
        ))
        assert ship.status == ShipmentStatus.PENDING
        assert ship.expires_at > now and ship.expires_at <= now + timedelta(hours=1, seconds=5)
        assert ship.price is None  # NULL until a bid is accepted
        print("create: ok")

        # two captains bid; cap1 re-bids (upsert, not a 2nd row)
        b1 = await svc.place_bid(shipment_id=ship.shipment_id, capitan_id=cap1, price=Decimal("50"))
        rebid = await svc.place_bid(shipment_id=ship.shipment_id, capitan_id=cap1, price=Decimal("45"))
        b2 = await svc.place_bid(shipment_id=ship.shipment_id, capitan_id=cap2, price=Decimal("60"))
        # the returned object (what endpoints serialize) must reflect the new price
        assert rebid.price == Decimal("45"), f"re-bid return stale: {rebid.price}"
        assert rebid.bid_id == b1.bid_id, "re-bid must update the same row, not insert"
        # the DB row, read fresh in a separate query, must also be 45 and singular
        fresh = await BidsDAL(s).get_for_shipment(ship.shipment_id)
        assert len(fresh) == 2, f"expected 2 bids, got {len(fresh)}"
        cap1_row = [x for x in fresh if x.capitan_id == cap1][0]
        assert cap1_row.price == Decimal("45"), f"db row stale: {cap1_row.price}"
        print("bid upsert: ok (2 bids, cap1 price updated to 45 in return + db)")

        # capture ids as plain values: the 409 paths below rollback, which expires
        # every ORM object in this session (a test-only concern — endpoints don't
        # reuse objects across operations).
        ship_id, b1_id, b2_id = ship.shipment_id, b1.bid_id, b2.bid_id

        # open feed shows it
        assert any(x.shipment_id == ship_id for x in await svc.list_open())
        print("browse open: ok")

        # sender accepts cap1's bid
        accepted = await svc.accept_bid(shipment_id=ship_id, bid_id=b1_id, sender_id=sender)
        assert accepted.status == ShipmentStatus.ACCEPTED
        assert accepted.capitan_id == cap1
        assert accepted.price == Decimal("45")
        bids = await BidsDAL(s).get_for_shipment(ship_id)
        won = [x for x in bids if x.bid_id == b1_id][0]
        lost = [x for x in bids if x.bid_id == b2_id][0]
        assert won.status == BidStatus.ACCEPTED and lost.status == BidStatus.REJECTED
        print("accept: ok (winner accepted, loser rejected, price snapshotted)")

        # double-accept -> 409 (gate)
        try:
            await svc.accept_bid(shipment_id=ship_id, bid_id=b2_id, sender_id=sender)
            raise SystemExit("FAIL: second accept should have raised")
        except ShipmentNotAcceptableError:
            print("double-accept rejected: ok")

        # accept by a non-owner -> gate's sender_id mismatch -> 409
        try:
            await svc.accept_bid(shipment_id=ship_id, bid_id=b1_id, sender_id=cap2)
            raise SystemExit("FAIL: non-owner accept should have raised")
        except ShipmentNotAcceptableError:
            print("non-owner accept rejected: ok")

        # bidding after accept -> 409
        try:
            await svc.place_bid(shipment_id=ship_id, capitan_id=cap2, price=Decimal("30"))
            raise SystemExit("FAIL: bid after accept should have raised")
        except ShipmentNotAcceptableError:
            print("bid-after-accept rejected: ok")

        # admin cancel from accepted (non-terminal) -> cancelled
        cancelled = await svc.cancel(ship_id)
        assert cancelled.status == ShipmentStatus.CANCELLED
        # cancel again (now terminal) -> 409
        try:
            await svc.cancel(ship_id)
            raise SystemExit("FAIL: cancel of terminal should have raised")
        except ShipmentNotAcceptableError:
            print("cancel + terminal-recancel rejected: ok")

        # cancel a missing shipment -> 404
        try:
            await svc.cancel(uuid.uuid4())
            raise SystemExit("FAIL: cancel missing should 404")
        except NotFoundError:
            print("cancel-missing 404: ok")

        # ── sender cancel (pending-only) ─────────────────────────────────────
        s2 = (await svc.create(sender_id=sender, data=_req())).shipment_id
        assert (await svc.cancel_by_sender(s2, sender)).status == ShipmentStatus.CANCELLED
        print("sender cancel pending: ok")
        # non-owner -> 404
        s3 = (await svc.create(sender_id=sender, data=_req())).shipment_id
        try:
            await svc.cancel_by_sender(s3, cap2)
            raise SystemExit("FAIL: non-owner sender-cancel should 404")
        except NotFoundError:
            print("sender cancel non-owner 404: ok")
        # accepted shipment -> sender can't cancel (409)
        s4 = (await svc.create(sender_id=sender, data=_req())).shipment_id
        b4 = (await svc.place_bid(shipment_id=s4, capitan_id=cap1, price=Decimal("20"))).bid_id
        await svc.accept_bid(shipment_id=s4, bid_id=b4, sender_id=sender)
        try:
            await svc.cancel_by_sender(s4, sender)
            raise SystemExit("FAIL: sender cancel of accepted should 409")
        except ShipmentNotAcceptableError:
            print("sender cancel accepted rejected (409): ok")

        # ── captain withdraw bid ─────────────────────────────────────────────
        s5 = (await svc.create(sender_id=sender, data=_req())).shipment_id
        w = (await svc.place_bid(shipment_id=s5, capitan_id=cap1, price=Decimal("30"))).bid_id
        await svc.withdraw_bid(shipment_id=s5, bid_id=w, capitan_id=cap1)
        assert await BidsDAL(s).get_for_shipment(s5) == [], "withdrawn bid should be gone"
        print("withdraw pending bid: ok (deleted)")
        # withdraw someone else's bid -> 404
        w2 = (await svc.place_bid(shipment_id=s5, capitan_id=cap2, price=Decimal("31"))).bid_id
        try:
            await svc.withdraw_bid(shipment_id=s5, bid_id=w2, capitan_id=cap1)
            raise SystemExit("FAIL: withdraw other's bid should 404")
        except NotFoundError:
            print("withdraw non-owner bid 404: ok")
        # accept then withdraw -> 409 (accepted bid can't be withdrawn)
        await svc.accept_bid(shipment_id=s5, bid_id=w2, sender_id=sender)
        try:
            await svc.withdraw_bid(shipment_id=s5, bid_id=w2, capitan_id=cap2)
            raise SystemExit("FAIL: withdraw accepted bid should 409")
        except ShipmentNotAcceptableError:
            print("withdraw accepted bid rejected (409): ok")

        # ── accept-vs-withdraw gate: withdraw first, then accept -> 404 ───────
        s6 = (await svc.create(sender_id=sender, data=_req())).shipment_id
        w3 = (await svc.place_bid(shipment_id=s6, capitan_id=cap1, price=Decimal("32"))).bid_id
        await svc.withdraw_bid(shipment_id=s6, bid_id=w3, capitan_id=cap1)
        try:
            await svc.accept_bid(shipment_id=s6, bid_id=w3, sender_id=sender)
            raise SystemExit("FAIL: accept of withdrawn bid should 404")
        except NotFoundError:
            print("accept withdrawn bid 404 (race gate): ok")

        # ── my shipments (role filter) ──────────────────────────────────────
        u = await mk_user(s, "u-sender")
        c = await mk_user(s, "u-cap")
        s_a = (await svc.create(sender_id=u, data=_req())).shipment_id  # stays pending
        s_b = (await svc.create(sender_id=u, data=_req())).shipment_id
        b = (await svc.place_bid(shipment_id=s_b, capitan_id=c, price=Decimal("10"))).bid_id
        await svc.accept_bid(shipment_id=s_b, bid_id=b, sender_id=u)  # s_b → captain c

        sent = {x.shipment_id for x in await svc.list_for_user(u, role="sender")}
        assert sent == {s_a, s_b}, sent
        won = {x.shipment_id for x in await svc.list_for_user(c, role="captain")}
        assert won == {s_b}, won
        assert {x.shipment_id for x in await svc.list_for_user(u)} == {s_a, s_b}  # u: sender of both
        assert {x.shipment_id for x in await svc.list_for_user(c)} == {s_b}  # c: captain of one
        print("my-shipments role filter (sender / captain / both): ok")

        print("\nALL CHECKS PASSED")


asyncio.run(main())
