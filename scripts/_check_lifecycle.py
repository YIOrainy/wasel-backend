"""Throwaway HTTP smoke test of the full shipment lifecycle against the running
server + live DB. Mints real access tokens for a seeded sender + captain, then
drives create -> browse -> bid -> accept -> otps -> pickup -> out-for-delivery
-> deliver exactly as the mobile app does (camelCase JSON, same endpoints,
same 409/422 error semantics).

Run: ./.venv/bin/python scripts/_check_lifecycle.py
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx

from app.core.security import encode_access_token
from app.db.base import AsyncSessionLocal
from app.db.models import CapitanProfile, User

BASE = "http://localhost:8000/api"


async def seed() -> tuple[uuid.UUID, uuid.UUID]:
    async with AsyncSessionLocal() as s:
        sender = User(user_id=uuid.uuid4(), name="LC sender", phone_number=f"+{uuid.uuid4().int % 10**12}")
        captain = User(user_id=uuid.uuid4(), name="LC captain", phone_number=f"+{uuid.uuid4().int % 10**12}")
        s.add(sender)
        s.add(captain)
        await s.flush()
        s.add(CapitanProfile(capitan_profile_id=uuid.uuid4(), user_id=captain.user_id, rating=4.9, total_trips=12))
        await s.commit()
        return sender.user_id, captain.user_id


def main() -> None:
    sender_id, captain_id = asyncio.run(seed())
    sh = {"Authorization": f"Bearer {encode_access_token(sender_id)}"}
    ch = {"Authorization": f"Bearer {encode_access_token(captain_id)}"}
    now = datetime.now(UTC)

    with httpx.Client(base_url=BASE, timeout=10) as c:
        r = c.post("/shipments", headers=sh, json={
            "pickupCity": "Riyadh", "destinationCity": "Jeddah",
            "pickupLat": 24.7, "pickupLng": 46.7, "destinationLat": 21.5, "destinationLng": 39.2,
            "deliveryMode": "regular",
        })
        assert r.status_code == 201, ("create", r.status_code, r.text)
        sid = r.json()["shipmentId"]
        assert r.json()["status"] == "pending"
        print("✓ create -> pending", sid)

        r = c.get("/shipments/open", headers=ch)
        assert r.status_code == 200 and any(x["shipmentId"] == sid for x in r.json()["shipments"])
        print("✓ captain browse sees open shipment")

        r = c.post(f"/shipments/{sid}/bids", headers=ch, json={
            "price": "50",
            "promisedDeliveryTime": (now + timedelta(hours=8)).isoformat(),
        })
        assert r.status_code == 201, ("bid", r.status_code, r.text)
        bid = r.json()["bidId"]
        print("✓ captain placed bid")

        r = c.get("/bids", headers=ch)
        assert r.status_code == 200 and any(b["shipmentId"] == sid for b in r.json()["bids"])
        print("✓ captain my-bids shows it")

        r = c.get(f"/shipments/{sid}/otps", headers=ch)
        assert r.status_code == 404, ("captain otps must 404", r.status_code)
        print("✓ captain blocked from OTPs (404)")

        r = c.post(f"/shipments/{sid}/bids/{bid}/accept", headers=sh)
        assert r.status_code == 200 and r.json()["status"] == "accepted", r.text
        assert r.json()["promisedDeliveryTime"], "accept must snapshot the bid's promise"
        print("✓ sender accept -> accepted (promise snapshotted)")

        r = c.get(f"/shipments/{sid}/otps", headers=sh)
        assert r.status_code == 200, r.text
        pk, dl = r.json()["pickupOtp"], r.json()["deliveryOtp"]
        assert pk and dl
        print(f"✓ sender OTPs: pickup={pk} delivery={dl}")

        bad = "9999" if pk != "9999" else "1111"
        r = c.post(f"/shipments/{sid}/pickup", headers=ch, json={"otp": bad})
        assert r.status_code == 422, ("pickup wrong code", r.status_code, r.text)
        print("✓ pickup with wrong code -> 422")

        r = c.post(f"/shipments/{sid}/deliver", headers=ch, json={"otp": dl})
        assert r.status_code == 409, ("deliver before pickup", r.status_code)
        print("✓ deliver before pickup -> 409 (wrong state)")

        r = c.post(f"/shipments/{sid}/pickup", headers=ch, json={"otp": pk})
        assert r.status_code == 200 and r.json()["status"] == "picked" and r.json()["pickedAt"], r.text
        print("✓ pickup with correct code -> picked")

        r = c.post(f"/shipments/{sid}/out-for-delivery", headers=ch)
        assert r.status_code == 200 and r.json()["status"] == "out_for_delivery" and r.json()["outForDeliveryAt"], r.text
        print("✓ out-for-delivery")

        badd = "9999" if dl != "9999" else "1111"
        r = c.post(f"/shipments/{sid}/deliver", headers=ch, json={"otp": badd})
        assert r.status_code == 422, ("deliver wrong code", r.status_code)
        print("✓ deliver with wrong code -> 422")

        r = c.post(f"/shipments/{sid}/deliver", headers=ch, json={"otp": dl})
        assert r.status_code == 200 and r.json()["status"] == "delivered" and r.json()["deliveredAt"], r.text
        print("✓ deliver with correct code -> delivered")

        r = c.get("/shipments?role=captain", headers=ch)
        assert r.status_code == 200 and any(x["shipmentId"] == sid for x in r.json()["shipments"])
        print("✓ captain deliveries list shows the delivered shipment")

    print("\n✅ ALL LIFECYCLE CHECKS PASSED")


if __name__ == "__main__":
    main()
