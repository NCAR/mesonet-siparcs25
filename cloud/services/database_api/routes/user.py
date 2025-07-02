from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from database.connection import get_db_async
from schema.user import UserCreate, UserResponse
from crud.user import UserService
from pydantic import EmailStr

router = APIRouter(prefix="/api/users", tags=["Users"])

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db_async)):
    crud = UserService(db)
    try:
        return await crud.create_user(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[UserResponse])
async def get_all_users(db: AsyncSession = Depends(get_db_async)):
    crud = UserService(db)
    return await crud.get_all_users()


@router.get("/{email}", response_model=UserResponse)
async def get_user_by_email(email: EmailStr, db: AsyncSession = Depends(get_db_async)):
    crud = UserService(db)
    user = await crud.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{email}", response_model=UserResponse)
async def update_user_mb_ids(email: EmailStr, payload: UserCreate, db: AsyncSession = Depends(get_db_async)):
    crud = UserService(db)
    user = await crud.update_user_mb_ids(email, payload.mb_user_id, payload.mb_group_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(email: EmailStr, db: AsyncSession = Depends(get_db_async)):
    crud = UserService(db)
    success = await crud.delete_user(email)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
