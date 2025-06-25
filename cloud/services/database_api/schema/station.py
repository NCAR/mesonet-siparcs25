from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class StationCreate(BaseModel):
    station_id: str
    device: Optional[str] = None
    longitude: float
    latitude: float
    firstname: str
    lastname: str
    organization: str
    email: str

class StationResponse(StationCreate):
    id: int
    timestamp: Optional[datetime]

    class Config:
        from_attributes = True
