"""Self-check for the SSE presence + notify seam (no DB, pure in-process).
Run: PYTHONPATH=. ./.venv/bin/python scripts/_check_sse.py
"""
import asyncio
import uuid

from app.realtime import notify as notify_mod
from app.realtime import presence


async def main() -> None:
    uid = uuid.uuid4()
    q: asyncio.Queue = asyncio.Queue()
    presence.connect(uid, q)

    # direct event -> lands on the user's stream
    await notify_mod.notify(uid, "new_bid", {"bid": {"price": "45"}})
    msg = q.get_nowait()
    assert msg == {"type": "new_bid", "bid": {"price": "45"}}, msg
    print("direct notify -> stream: ok")

    # request-feed broadcast -> lands on subscribed streams
    presence.join_request_feed(q)
    await notify_mod.notify_request_feed("new_request", {"shipment_id": "s1"})
    msg = q.get_nowait()
    assert msg["type"] == "new_request" and msg["shipment_id"] == "s1", msg
    print("request-feed broadcast: ok")

    # disconnect removes the stream from BOTH directories
    presence.disconnect(uid, q)
    assert presence.streams_for(uid) == [] and q not in presence.request_feed()
    print("disconnect cleanup: ok")

    # offline user -> FCM fallback path, must not raise
    await notify_mod.notify(uuid.uuid4(), "shipment_expired", {"shipment_id": "x"})
    print("offline fallback (no raise): ok")

    # multi-device: two streams for one user both receive
    q1, q2 = asyncio.Queue(), asyncio.Queue()
    presence.connect(uid, q1)
    presence.connect(uid, q2)
    await notify_mod.notify(uid, "bid_accepted", {"shipment_id": "s2"})
    assert q1.get_nowait()["type"] == "bid_accepted"
    assert q2.get_nowait()["type"] == "bid_accepted"
    print("multi-device fan-out: ok")

    print("\nALL SSE CHECKS PASSED")


asyncio.run(main())
