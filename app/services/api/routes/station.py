from fastapi import APIRouter, Depends, HTTPException
from requests import Session
from database.connection import SessionLocal
from crud.station import StationService
from schema.station import StationCreate, StationResponse
from typing import List

router = APIRouter(prefix="/stations", tags=["Stations"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[StationResponse])
def read_stations(db: Session = Depends(get_db)):
    service = StationService(db)
    return service.get_stations()

@router.get("/{station_id}", response_model=StationResponse)
def read_station(station_id: str, db: Session = Depends(get_db)):
    service = StationService(db)
    station = service.get_station(station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return station

@router.post("/", response_model=StationResponse)
def create_station(data: StationCreate, db: Session = Depends(get_db)):
    service = StationService(db)
    return service.create_station(data)

@router.put("/{station_id}", response_model=StationResponse)
def update_station(station_id: str, data: StationCreate, db: Session = Depends(get_db)):
    service = StationService(db)
    updated = service.update_station(station_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Station not found")
    return updated
