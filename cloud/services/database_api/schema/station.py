from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime

class StationCreate(BaseModel):
    station_id: str
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


class StationUpdate(BaseModel):
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


class StationResponse(BaseModel):
    id: int
    station_id: str
    device: Optional[str]
    longitude: Optional[float]
    latitude: Optional[float]
    altitude: Optional[float]
    firstname: Optional[str]
    lastname: Optional[str]
    email: Optional[str]
    organization: Optional[str]
    last_active: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True  # Enable ORM compatibility for SQLAlchemy
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None  # Serialize datetime to ISO 8601
        }