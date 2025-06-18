from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class StationCreate(BaseModel):
    station_id: str
    status: str
    longitude: float
    latitude: float
    firstname: str
    lastname: str
    email: str

class StationResponse(StationCreate):
    id: int
    timestamp: Optional[datetime]

    class Config:
        from_attributes = True
