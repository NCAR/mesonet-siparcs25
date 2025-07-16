from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Station(BaseModel):
    device: Optional[str] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    altitude: Optional[float] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: Optional[str] = None
    organization: Optional[str] = None
    last_active: Optional[datetime] = None
    created_at: Optional[datetime] = None

class StationCreate(Station):
    station_id: str

class StationUpdate(Station):
    pass

class StationResponse(StationCreate):
    class Config:
        from_attributes = True  # Enable ORM compatibility for SQLAlchemy
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None  # Serialize datetime to ISO 8601
        }