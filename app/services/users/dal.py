
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import User


class UsersDAL:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.session.execute(
            select(User)
            .where(User.user_id == user_id)
            .options(selectinload(User.capitan_profile))  
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        result = await self.session.execute(
            select(User)
            .where(User.phone_number == phone)
            .options(selectinload(User.capitan_profile))  
        )
        return result.scalar_one_or_none()

    async def insert(self, user: User) -> None:
        self.session.add(user)
        await self.session.flush()
