from sqlalchemy.orm import Session
from models.reading import ReadingModel
from schema.reading import ReadingCreate, ReadingResponse
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime, timezone
from logger import CustomLogger

console = CustomLogger()

class ReadingService:
    def __init__(self, db: Session):
        self.db = db

    def get_readings(self, station_id: Optional[str] = None) -> List[ReadingResponse]:
        query = self.db.query(ReadingModel)
        if station_id:
            query = query.filter(ReadingModel.station_id == station_id)
        readings = query.all()
        return [reading for reading in readings]

    def get_reading(self, reading_id: int) -> ReadingResponse:
        reading = self.db.query(ReadingModel).filter(ReadingModel.id == reading_id).first()
        if not reading:
            raise HTTPException(status_code=404, detail=f"Reading {reading_id} not found")
        return reading

    def create_reading(self, reading_data: ReadingCreate) -> ReadingResponse:
        #console.info(f"Creating reading for station {reading_data.station_id} with data: {reading_data.dict()}")
        data = reading_data.dict()
        db_reading = ReadingModel(**data)
        try:
            self.db.add(db_reading)
            self.db.commit()
            self.db.refresh(db_reading)
        except IntegrityError as e:
            self.db.rollback()
            raise HTTPException(status_code=400, detail=f"Failed to create reading for station {data['station_id']}: {str(e)}")
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Internal error creating reading for station {data['station_id']}: {str(e)}")
        return db_reading