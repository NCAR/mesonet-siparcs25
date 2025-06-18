from fastapi import APIRouter, Depends, HTTPException
from requests import Session
from database.connection import SessionLocal
from crud.reading import ReadingService
from schema.reading import ReadingCreate, ReadingResponse
from typing import List

router = APIRouter(prefix="/api/readings", tags=["Readings"])

# DB generator
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[ReadingResponse])
def read_readings(db: Session = Depends(get_db)):
    service = ReadingService(db)
    return service.get_readings()

@router.get("/{station_id}", response_model=ReadingResponse)
def read_station_readings(station_id: str, db: Session = Depends(get_db)):
    service = ReadingService(db)
    station_data = service.get_readings_by_station_id(station_id)
    if not station_data:
        raise HTTPException(status_code=404, detail=f"Readings for {station_id} not found")
    return station_data

@router.post("/", response_model=ReadingResponse)
def create_reading(data: ReadingCreate, db: Session = Depends(get_db)):
    service = ReadingService(db)
    return service.create_reading(data)

@router.put("/station/{station_id}/reading/{reading_id}", response_model=ReadingResponse)
def update_reading(station_id: str, reading_id: str, data: ReadingCreate, db: Session = Depends(get_db)):
    service = ReadingService(db)
    updated = service.update_reading(station_id, reading_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Reading not found")
    return updated
