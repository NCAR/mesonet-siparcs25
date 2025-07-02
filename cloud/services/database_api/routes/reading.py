from fastapi import APIRouter, Depends, HTTPException
from database.connection import get_db_async
from crud.reading import ReadingService
from schema.reading import ReadingCreate, ReadingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

router = APIRouter(prefix="/api/readings", tags=["Readings"])


@router.get("/", response_model=List[ReadingResponse])
async def read_readings(db: AsyncSession = Depends(get_db_async)):
    service = ReadingService(db)
    return await service.get_readings()


@router.get("/{station_id}", response_model=List[ReadingResponse])
async def read_station_readings(station_id: str, db: AsyncSession = Depends(get_db_async)):
    service = ReadingService(db)
    station_data = await service.get_readings_by_station_id(station_id)
    if not station_data:
        raise HTTPException(status_code=404, detail=f"Readings for station '{station_id}' not found")
    return station_data


@router.post("/", response_model=ReadingResponse)
async def create_reading(data: ReadingCreate, db: AsyncSession = Depends(get_db_async)):
    service = ReadingService(db)
    return await service.create_reading(data)


@router.put("/station/{station_id}/reading/{reading_id}", response_model=ReadingResponse)
async def update_reading(station_id: str, reading_id: str, data: ReadingCreate, db: AsyncSession = Depends(get_db_async)):
    service = ReadingService(db)
    updated = await service.update_reading(station_id, reading_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Reading not found")
    return updated
