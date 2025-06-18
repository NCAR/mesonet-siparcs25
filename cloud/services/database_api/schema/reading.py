from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ReadingCreate(BaseModel):
    station_id: str
    device: Optional[str]
    measurement: str
    reading_value: float
    sensor_protocol: Optional[str]
    sensor_model: str
    signal_strength: Optional[float]
    latitude: Optional[float]
    longitude: Optional[float]

class ReadingResponse(ReadingCreate):
    id: int
    timestamp: Optional[datetime]

    class Config:
        from_attributes = True
