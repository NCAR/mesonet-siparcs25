from pydantic import BaseModel, Field
from typing import Optional

class GroupCreate(BaseModel):
    name: str = Field(..., alias="station_id")

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
