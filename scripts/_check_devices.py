"""Self-check for device registration against the live DB.
Run: DATABASE_URL=...+psycopg...localhost... PYTHONPATH=. ./.venv/bin/python scripts/_check_devices.py
Proves: register, multi-device, re-register (no dup + updated_at bump),
reassign-only-the-sent-token, owner-scoped + idempotent delete.
"""
import asyncio
import uuid

from app.db.base import AsyncSessionLocal
from app.db.models import User
from app.services.devices.dal import DevicesDAL
from app.services.devices.service import DevicesService


async def mk_user(s, name) -> uuid.UUID:
    uid = uuid.uuid4()
    s.add(User(user_id=uid, name=name, phone_number=f"+{uuid.uuid4().int % 10**12}"))
    await s.commit()
    return uid


async def tokens(svc, user_id) -> set[str]:
    return {d.fcm_token for d in await svc.tokens_for(user_id)}


async def main() -> None:
    async with AsyncSessionLocal() as s:
        svc = DevicesService(s, DevicesDAL(s))
        a = await mk_user(s, "A")
        b = await mk_user(s, "B")
        iphone = "tok_iphone_" + uuid.uuid4().hex
        ipad = "tok_ipad_" + uuid.uuid4().hex

        d1 = await svc.register(user_id=a, fcm_token=iphone, platform="ios")
        await svc.register(user_id=a, fcm_token=ipad, platform="ios")
        assert await tokens(svc, a) == {iphone, ipad}
        print("register two devices for A: ok")

        # re-register the iPhone token -> same row, no dup, updated_at bumped
        before = d1.updated_at
        d1b = await svc.register(user_id=a, fcm_token=iphone, platform="ios")
        assert await tokens(svc, a) == {iphone, ipad}, "must not duplicate"
        assert d1b.device_id == d1.device_id, "same row reused"
        assert d1b.updated_at > before, "updated_at should bump on refresh"
        print("re-register upsert (no dup, updated_at bumped): ok")

        # reassign the iPhone token to B — only the sent token moves; iPad untouched
        await svc.register(user_id=b, fcm_token=iphone, platform="ios")
        assert await tokens(svc, a) == {ipad}, "A keeps only the iPad"
        assert await tokens(svc, b) == {iphone}, "B owns the iPhone now"
        print("reassign iPhone-only (iPad untouched): ok")

        # owner-scoped delete: A tries to delete B's iPhone token -> no-op
        await svc.unregister(user_id=a, fcm_token=iphone)
        assert await tokens(svc, b) == {iphone}, "non-owner delete must be a no-op"
        print("delete scoped to owner (non-owner no-op): ok")

        # real logout delete by the owner
        await svc.unregister(user_id=b, fcm_token=iphone)
        assert await tokens(svc, b) == set()
        print("owner logout delete: ok")

        # idempotent: deleting a missing token doesn't raise
        await svc.unregister(user_id=a, fcm_token="does_not_exist")
        print("delete missing (idempotent): ok")

        print("\nALL DEVICE CHECKS PASSED")


asyncio.run(main())
