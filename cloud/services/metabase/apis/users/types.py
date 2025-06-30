from pydantic import BaseModel, EmailStr
from typing import Optional, List, TypedDict
from datetime import datetime

class UserData(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str

class UserResponse(UserData):
    id: int
    common_name: str
    last_login: Optional[datetime] = None
    date_joined: datetime
    updated_at: datetime
    is_active: bool
    is_superuser: bool
    is_qbnewb: bool
    group_ids: List[int]
    personal_collection_id: int
    locale: Optional[str] = None
    login_attributes: Optional[dict] = None
    tenant_id: Optional[int] = None
    sso_source: Optional[str] = None

class APIResponse(TypedDict):
    message: str
    data: UserData
    status: int
