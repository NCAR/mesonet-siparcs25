from sqlite3 import IntegrityError
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models.user import UserModel
from typing import Optional, List
from schema.user import UserCreate, UserResponse

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: EmailStr) -> Optional[UserResponse]:
        result = await self.db.execute(select(UserModel).where(UserModel.email == email))
        user = result.scalar_one_or_none()
        if user:
            return UserResponse.model_validate(user)
        return None

    async def get_all_users(self) -> List[UserResponse]:
        result = await self.db.execute(select(UserModel))
        users = result.scalars().all()
        return [UserResponse.model_validate(user) for user in users]

    async def create_user(self, payload: UserCreate) -> UserResponse:
        try:
            user = UserModel(**payload.model_dump())
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            return UserResponse.model_validate(user)
            
        except IntegrityError as e:
            await self.db.rollback()
            raise ValueError(f"User {user.email} already exists.") from e

    async def create_user_if_not_exists(self, payload: UserCreate) -> UserResponse:
        existing = await self.get_user_by_email(payload.email)
        if existing:
            return existing
        return await self.create_user(payload)

    async def update_user_mb_ids(self, email: EmailStr, mb_user_id: int, mb_group_id: int) -> Optional[UserResponse]:
        result = await self.db.execute(select(UserModel).where(UserModel.email == email))
        user = result.scalar_one_or_none()

        if not user:
            return None

        user.mb_user_id = mb_user_id
        user.mb_group_id = mb_group_id

        await self.db.commit()
        await self.db.refresh(user)

        return UserResponse.model_validate(user)

    async def delete_user(self, email: EmailStr) -> bool:
        result = await self.db.execute(select(UserModel).where(UserModel.email == email))
        user = result.scalar_one_or_none()

        if not user:
            return False

        await self.db.delete(user)
        await self.db.commit()
        return True
