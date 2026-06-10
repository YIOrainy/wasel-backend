
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.services.users.dal import UsersDAL


class UsersService:
    def __init__(self, session: AsyncSession, users_dal: UsersDAL) -> None:
        self.session = session
        self.users_dal = users_dal

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.users_dal.get_by_id(user_id)

    async def get_by_phone(self, phone: str) -> User | None:
        return await self.users_dal.get_by_phone(phone)

    async def create_user(self, *, name: str, phone: str, email: str | None) -> User:
        user = User(
            user_id=uuid.uuid4(),
            name=name,
            phone_number=phone,
            email=email,
        )
        await self.users_dal.insert(user)
        await self.session.commit()
        await self.session.refresh(user, attribute_names=["capitan_profile"])
        return user
