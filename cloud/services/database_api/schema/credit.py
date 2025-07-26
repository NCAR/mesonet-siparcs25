from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CreditCreate(BaseModel):
    station_id: str
    longitude: float
    latitude: float
    forecast_for: datetime
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[str] = None

class CreditUpdate(CreditCreate):
    id: Optional[int] = None  # Allow id to be optional for updates
    station_id: Optional[str] = None  # Allow station_id to be optional for updates

class CreditResponse(CreditCreate):
    id: int

    class Config:
        from_attributes = True  # Enable ORM compatibility
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None  # Serialize datetime to ISO 8601
        }