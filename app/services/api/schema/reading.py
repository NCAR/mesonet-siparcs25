from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ReadingCreate(BaseModel):
    station_id: str
    device: str
    measurement: str
    reading_value: float
    sensor_protocol: str
    sensor_model: str
    signal_strength: float

class ReadingResponse(ReadingCreate):
    id: int
    timestamp: Optional[datetime]

    class Config:
        from_attributes = True
