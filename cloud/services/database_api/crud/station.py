from sqlalchemy.orm import Session
from models.station import StationModel
from schema.station import StationCreate, StationResponse
from typing import List
from datetime import datetime
from logger import CustomLogger

console = CustomLogger()

class StationService:
    def __init__(self, db: Session):
        self.db = db

    def get_stations(self) -> List[StationResponse]:
        return self.db.query(StationModel).all()
    
    def get_station(self, station_id: str) -> StationResponse:
        return self.db.query(StationModel).filter(StationModel.station_id == station_id).first()

    def create_station(self, station_data: StationCreate) -> StationResponse:
        db_station = StationModel(**station_data.dict(), timestamp=datetime.now(datetime.timezone.utc))
        self.db.add(db_station)
        self.db.commit()
        self.db.refresh(db_station)
        return db_station

    def update_station(self, station_id: str, update_data: StationCreate) -> StationResponse:
        station = self.get_station(station_id)
        if station:
            for key, value in update_data.dict().items():
                setattr(station, key, value)
            self.db.commit()
            self.db.refresh(station)
        return station

