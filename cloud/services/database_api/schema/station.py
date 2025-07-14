from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class StationCreate(BaseModel):
    station_id: str
    longitude: float
    latitude: float
    firstname: str
    lastname: str
    organization: str
    email: str

class StationUpdate(BaseModel):
    station_id: Optional[str] = None  # Optional, but set in endpoint
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    organization: Optional[str] = None
    email: Optional[str] = None
    timestamp: Optional[datetime] = None  # Match table's timestamp field

class StationResponse(BaseModel):
    id: int
    station_id: str
    device: Optional[str] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    altitude: Optional[float] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    organization: Optional[str] = None
    email: Optional[str] = None
    created_at : Optional[datetime] = None
    last_active: Optional[datetime] = None

    class Config:
        from_attributes = True