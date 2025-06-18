from sqlalchemy.orm import Session
from models.reading import ReadingModel
from schema.reading import ReadingCreate, ReadingResponse
from typing import List
from datetime import datetime
from logger import CustomLogger

console = CustomLogger()

class ReadingService:
    def __init__(self, db: Session):
        self.db = db

    def get_readings(self) -> List[ReadingResponse]:
        return self.db.query(ReadingModel).all()
    
    def get_readings_by_station_id(self, station_id):
        return self.db.query(ReadingModel).filter(ReadingModel.station_id == station_id).all()

    def create_reading(self, reading_data: ReadingCreate) -> ReadingResponse:
        db_reading = ReadingModel(**reading_data.dict(), timestamp=datetime.utcnow())
        self.db.add(db_reading)
        self.db.commit()
        self.db.refresh(db_reading)
        return db_reading

    def update_reading(self, station_id: str, reading_id: str, update_data: ReadingCreate) -> ReadingResponse:
        reading = self.db.query(ReadingModel).filter(ReadingModel.station_id == station_id and ReadingModel.id == reading_id).all()
        if reading:
            for key, value in update_data.dict().items():
                setattr(reading, key, value)
            self.db.commit()
            self.db.refresh(reading)
        return reading

