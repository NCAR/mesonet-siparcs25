from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class StationCreate(BaseModel):
    station_id: str
    longitude: float
    latitude: float
    first_name: str
    last_name: str
    email: str

class StationResponse(StationCreate):
    timestamp: Optional[datetime]

    class Config:
        from_attributes = True
