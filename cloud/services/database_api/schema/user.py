from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    mb_user_id: int
    mb_group_id: int

class UserResponse(UserCreate):
    created_at: Optional[datetime]

    class Config:
        from_attributes = True
