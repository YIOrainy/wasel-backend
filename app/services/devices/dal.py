import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Device


class DevicesDAL:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self, *, user_id: uuid.UUID, fcm_token: str, platform: str
    ) -> Device:
        stmt = pg_insert(Device).values(
            device_id=uuid.uuid4(),
            user_id=user_id,
            fcm_token=fcm_token,
            platform=platform,
        )

        stmt = (
            stmt.on_conflict_do_update(
                index_elements=[Device.fcm_token],
                set_={
                    Device.user_id: stmt.excluded.user_id,
                    Device.platform: stmt.excluded.platform,
                    Device.updated_at: func.now(),  # bump on reassign/refresh
                },
            )
            .returning(Device)
        )

        result = await self.session.execute(
            stmt, execution_options={"populate_existing": True}
        )
        return result.scalar_one()

    async def tokens_for(self, user_id: uuid.UUID) -> list[Device]:
        stmt = select(Device).where(Device.user_id == user_id)

        result = await self.session.scalars(stmt)

        return list(result.all())

    async def delete(self, *, user_id: uuid.UUID, fcm_token: str) -> int:
        stmt = delete(Device).where(
            Device.fcm_token == fcm_token,
            Device.user_id == user_id,
        )

        result = await self.session.execute(stmt)

        return result.rowcount or 0