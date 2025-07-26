from fastapi import APIRouter, Depends, HTTPException
from database.connection import get_db_async
from crud.credit import CreditService
from schema.credit import CreditCreate, CreditResponse, CreditUpdate
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

router = APIRouter(prefix="/api/credit-forecast", tags=["Credit-Forecast"])

@router.get("/", response_model=List[CreditResponse])
async def get_forecasts(db: AsyncSession = Depends(get_db_async)):
    service = CreditService(db)
    return await service.get_forecasts()

@router.get("/{station_id}", response_model=List[CreditResponse])
async def get_station_forecast(station_id: str, db: AsyncSession = Depends(get_db_async)):
    service = CreditService(db)
    forecast_data = await service.get_forecast_by_station_id(station_id)
    if not forecast_data:
        raise HTTPException(status_code=404, detail=f"Prediction for station '{station_id}' not found")
    
    return forecast_data

@router.post("/", response_model=CreditResponse)
async def add_forecast(data: CreditCreate, db: AsyncSession = Depends(get_db_async)):
    service = CreditService(db)
    return await service.post_forecast(data)

@router.put("/{station_id}", response_model=CreditResponse)
async def update_forecast(station_id: str, data: CreditUpdate, db: AsyncSession = Depends(get_db_async)):
    service = CreditService(db)
    updated = await service.update_forecast(station_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return updated
