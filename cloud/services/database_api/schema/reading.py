from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ReadingCreate(BaseModel):
    station_id: str
    edge_id: Optional[str] = None
    measurement: str
    reading_value: float
    sensor_protocol: Optional[str] = None
    sensor_model: str
    rssi: Optional[int] = None
    latitude: float
    longitude: float


class ReadingResponse(ReadingCreate):
    id: int
    timestamp: Optional[datetime]

    class Config:
        from_attributes = True
