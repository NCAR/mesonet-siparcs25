from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    authority_level: Optional[str] = "official"
    namespace: Optional[str] = None
    parent_id: Optional[int] = None

class CollectionRes(CollectionCreate):
    authority_level: Optional[str] = None
    archived: bool
    slug: str
    archive_operation_id: Optional[int] = None
    personal_owner_id: Optional[int] = None
    type: Optional[str] = None
    is_sample: bool
    id: int
    archived_directly: Optional[bool] = None
    entity_id: str
    location: str
    namespace: Optional[str] = None
    created_at: datetime
