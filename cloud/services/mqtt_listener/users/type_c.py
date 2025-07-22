from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class UserGroupMembership(BaseModel):
    id: int

class LoginAttributes(BaseModel):
    ANY_ADDITIONAL_PROPERTY: Optional[str]

class MetabaseUserPayload(BaseModel):
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

class MetabaseUserRes(MetabaseUserPayload):
    user_group_memberships: Optional[List[UserGroupMembership]] = None
    group_ids: Optional[List[int]] = None
    personal_collection_id: Optional[int] = None

    class Config:
        from_attributes = True

class DatabaseUser(BaseModel):
    email: EmailStr
    mb_user_id: int
    mb_group_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class MetabaseGroupPayload(BaseModel):
    name: str = Field(..., alias="station_id")

class MetabaseGroupRes(MetabaseGroupPayload):
    id: int
    entity_id: Optional[str] = None
    magic_group_type: Optional[str] = None
    is_tenant_group: bool
    member_count: Optional[int] = None

class MetabaseMembership(BaseModel):
    group_id: int
    is_group_manager: Optional[bool] = False
    user_id: int

class MembershipRes(MetabaseMembership):
    email: EmailStr
    first_name: str
    column: Optional[Any] = Field(default_factory=None, alias="?column?")
    membership_id: int
    is_superuser: bool
    id: int
    last_name: str
    common_name: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }
