from sqlalchemy.orm import Session
from models.station import StationModel
from schema.station import StationCreate, StationResponse, StationUpdate
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from typing import List
from datetime import datetime,timezone
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
        db_station = StationModel(**station_data.dict(), timestamp= datetime.now(timezone.utc).isoformat())
        self.db.add(db_station)
        self.db.commit()
        self.db.refresh(db_station)
        return db_station

    def update_station(self, station_id: str, update_data: StationUpdate) -> StationResponse:
        station = self.get_station(station_id)
        if station:
            # Update existing station
            for key, value in update_data.dict(exclude_unset=True).items():
                if hasattr(station, key):
                    setattr(station, key, value)
            try:
                self.db.commit()
                self.db.refresh(station)
            except IntegrityError as e:
                self.db.rollback()
                raise HTTPException(status_code=400, detail=f"Failed to update station {station_id}: {str(e)}")
            except Exception as e:
                self.db.rollback()
                raise HTTPException(status_code=500, detail=f"Internal error updating station {station_id}: {str(e)}")
        else:
            # Create new station if it doesn't exist (upsert behavior)
            try:
                # Ensure station_id is included
                data = update_data.dict(exclude_unset=True)
                data["station_id"] = station_id
                # Set default values for required fields if not provided
                data.setdefault("firstname", "")
                data.setdefault("lastname", "")
                data.setdefault("email", "")
                data.setdefault("organization", "")
                station = StationModel(**data)
                self.db.add(station)
                self.db.commit()
                self.db.refresh(station)
            except IntegrityError as e:
                self.db.rollback()
                raise HTTPException(status_code=400, detail=f"Failed to create station {station_id}: {str(e)}")
            except Exception as e:
                self.db.rollback()
                raise HTTPException(status_code=500, detail=f"Internal error creating station {station_id}: {str(e)}")
        
        return StationResponse.from_orm(station)

