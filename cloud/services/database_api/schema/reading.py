from pydantic import BaseModel, validator
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
    altitude: float
    timestamp: Optional[datetime] = None


class ReadingResponse(ReadingCreate):
    id: int
    timestamp: Optional[datetime]

    class Config:
        from_attributes = True  # Enable ORM compatibility
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None  # Serialize datetime to ISO 8601
        }