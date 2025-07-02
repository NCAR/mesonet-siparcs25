from fastapi import APIRouter, Depends, HTTPException
from database.connection import get_db_async
from crud.station import StationService
from schema.station import StationCreate, StationResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

router = APIRouter(prefix="/api/stations", tags=["Stations"])

@router.get("/", response_model=List[StationResponse])
async def read_stations(db: AsyncSession = Depends(get_db_async)):
    service = StationService(db)
    return await service.get_stations()


@router.get("/{station_id}", response_model=Optional[StationResponse])
async def read_station(station_id: str, db: AsyncSession = Depends(get_db_async)):
    service = StationService(db)
    station = await service.get_station(station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return station


@router.post("/", response_model=StationResponse)
async def create_station(data: StationCreate, db: AsyncSession = Depends(get_db_async)):
    service = StationService(db)
    try:
        return await service.create_station(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{station_id}", response_model=StationResponse)
async def update_station(station_id: str, data: StationCreate, db: AsyncSession = Depends(get_db_async)):
    service = StationService(db)
    updated = await service.update_station(station_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Station not found")
    return updated
