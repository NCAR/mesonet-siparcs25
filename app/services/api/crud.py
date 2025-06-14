from sqlalchemy.orm import Session
from models import Station
from typing import List
from datetime import datetime
from logger import CustomLogger

console = CustomLogger()

class ReadWriteDB:
    def __init__(self, db: Session):
        self.db = db

    def get_stations(self) -> List[Station]:
        return self.db.query(Station).all()
    
    def get_station(self, station_id: str) -> Station:
        return self.db.query(Station).filter(Station.station_id == station_id).first()

    def create_station(self, station_data: dict) -> Station:
        db_station = Station(**station_data, timestamp=datetime.utcnow())
        self.db.add(db_station)
        self.db.commit()
        self.db.refresh(db_station)
        return db_station

    def update_station(self, station_id: str, update_data: dict) -> Station:
        station = self.get_station(station_id)
        if station:
            for key, value in update_data.items():
                setattr(station, key, value)
            self.db.commit()
            self.db.refresh(station)
        return station

