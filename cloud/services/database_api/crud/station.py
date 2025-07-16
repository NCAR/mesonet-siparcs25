from sqlalchemy.orm import Session
from models.station import StationModel
from schema.station import StationCreate, StationResponse, StationUpdate
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from typing import List
from datetime import datetime, timezone
from logger import CustomLogger

console = CustomLogger()

class StationService:
    def __init__(self, db: Session):
        self.db = db

    def get_stations(self) -> List[StationResponse]:
        stations = self.db.query(StationModel).all()
        return [station for station in stations]

    def get_station(self, station_id: str) -> StationResponse:
        station = self.db.query(StationModel).filter(StationModel.station_id == station_id).first()
        if not station:
            raise HTTPException(status_code=404, detail=f"Station {station_id} not found")
        return station

    def create_station(self, station_data: StationCreate) -> StationResponse:
        #console.info(f"Creating station {station_data.station_id} with data: {station_data.dict()}")
        data = station_data.dict()

        db_station = StationModel(**data)
        try:
            self.db.add(db_station)
            self.db.commit()
            self.db.refresh(db_station)
        except IntegrityError as e:
            self.db.rollback()
            raise HTTPException(status_code=400, detail=f"Failed to create station {data['station_id']}: {str(e)}")
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Internal error creating station {data['station_id']}: {str(e)}")
        return db_station

    def update_station(self, station_id: str, update_data: StationUpdate) -> StationResponse:
        #console.info(f"Updating station {station_id} with data: {update_data.dict()}")
        station = self.db.query(StationModel).filter(StationModel.station_id == station_id).first()
        data = update_data.dict(exclude_unset=True)

        if station:
            for key, value in data.items():
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
            data["station_id"] = station_id
            data.setdefault("firstname", None)
            data.setdefault("lastname", None)
            data.setdefault("email", None)
            data.setdefault("organization", None)
            if "created_at" not in data or data["created_at"] is None:
                data["created_at"] = datetime.now(timezone.utc)
            try:
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
        
        return station