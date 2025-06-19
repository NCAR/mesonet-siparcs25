from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ReadingCreate(BaseModel):
    station_id: str
    device: Optional[str] = None
    measurement: str
    reading_value: float
    sensor_protocol: Optional[str] = None
    sensor_model: str
    signal_strength: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ReadingResponse(ReadingCreate):
    id: int
    timestamp: Optional[datetime]

    class Config:
        from_attributes = True
