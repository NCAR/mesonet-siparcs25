from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime


class UserGroupMembership(BaseModel):
    id: int

class LoginAttributes(BaseModel):
    ANY_ADDITIONAL_PROPERTY: Optional[str]

class MetabaseUser(BaseModel):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    common_name: str
    locale: Optional[str]
    last_login: Optional[datetime]
    is_active: bool
    is_qbnewb: bool
    is_superuser: bool
    date_joined: datetime
    updated_at: datetime
    sso_source: Optional[str]
    tenant_id: Optional[str]
    login_attributes: Optional[Dict[str, Any]]

class MetabaseNewUser(MetabaseUser):
    user_group_memberships: List[UserGroupMembership]

    class Config:
        from_attributes = True

class MetabaseExisitngUser(MetabaseUser):
    group_ids: List[int]
    personal_collection_id: int

    class Config:
        from_attributes = True

class DatabaseUser(BaseModel):
    email: EmailStr
    mb_user_id: int
    mb_group_id: int
    created_at: datetime

    class Config:
        from_attributes = True    

