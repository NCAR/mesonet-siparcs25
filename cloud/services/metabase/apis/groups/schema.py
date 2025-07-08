from pydantic import BaseModel, Field, EmailStr, RootModel
from typing import Dict, List, Optional, Any, TypeVar, Generic

T = TypeVar("T")

class GroupCreate(BaseModel):
    name: str = Field(..., alias="station_id")

class Membership(BaseModel):
    group_id: int
    is_group_manager: Optional[bool] = False
    user_id: int

class GroupResponse(GroupCreate):
    id: int
    name: str
    entity_id: Optional[str] = None
    magic_group_type: Optional[str] = None
    is_tenant_group: bool
    member_count: Optional[int] = None

    model_config = {
        "from_attributes": True,
    }

class MembershipRes(Membership):
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

class DynamicMap(Membership):
    membership_id: int

class MembershipMap(RootModel[Dict[str, List[Membership]]]):
    pass

class APIResponse(BaseModel, Generic[T]):
    message: str
    data: Any
    status: Optional[int] = None
