import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Device
from app.services.devices.dal import DevicesDAL


class DevicesService:
    def __init__(self, session: AsyncSession, devices_dal: DevicesDAL) -> None:
        self.session = session
        self.devices_dal = devices_dal

    async def register(
        self, *, user_id: uuid.UUID, fcm_token: str, platform: str
    ) -> Device:
        device = await self.devices_dal.upsert(
            user_id=user_id, fcm_token=fcm_token, platform=platform
        )
        await self.session.commit()
        return device

    async def unregister(self, *, user_id: uuid.UUID, fcm_token: str) -> None:
        await self.devices_dal.delete(user_id=user_id, fcm_token=fcm_token)
        await self.session.commit()

    async def tokens_for(self, user_id: uuid.UUID) -> list[Device]:
        return await self.devices_dal.tokens_for(user_id)