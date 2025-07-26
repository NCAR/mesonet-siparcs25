from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models.credit import CreditModel
from schema.credit import CreditCreate, CreditResponse, CreditUpdate
from typing import List
from sqlalchemy.exc import IntegrityError

class CreditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_forecasts(self) -> List[CreditResponse]:
        result = await self.db.execute(select(CreditModel))
        forecasts = result.scalars().all()
        return [CreditResponse.model_validate(f) for f in forecasts]
    
    async def get_forecast_by_station_id(self, station_id: str) -> List[CreditResponse]:
        result = await self.db.execute(
            select(CreditModel).where(CreditModel.station_id == station_id)
        )
        forecasts = result.scalars().all()
        return [CreditResponse.model_validate(r) for r in forecasts]
    
    async def post_forecast(self, forecast_data: CreditCreate) -> CreditResponse:
        result = await self.db.execute(
            select(CreditModel).where(
                CreditModel.station_id == forecast_data.station_id,
                CreditModel.forecast_for == forecast_data.forecast_for
            )
        )
        existing_forecast = result.scalar_one_or_none()

        if existing_forecast:
            return await self.update_forecast(existing_forecast.station_id, forecast_data)
    
        try:
            forecast = CreditModel(**forecast_data.model_dump())
            self.db.add(forecast)
            await self.db.commit()
            await self.db.refresh(forecast)
        except IntegrityError as e:
            await self.db.rollback()
            raise HTTPException(status_code=400, detail=f"Failed to forecast for station {forecast_data.station_id}: {str(e)}")
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Internal error forecasting for station {forecast_data.station_id}: {str(e)}")
        
        return forecast

    async def update_forecast(self, station_id: str, forecast_data: CreditUpdate) -> CreditResponse:
        result = await self.db.execute(
            select(CreditModel).where(CreditModel.station_id == forecast_data.station_id)
        )
        existing_forecast = result.scalar_one_or_none()
        updated_forecast = forecast_data.dict(exclude_unset=True)
        
        for key, value in updated_forecast.items():
            if hasattr(existing_forecast, key):
                setattr(existing_forecast, key, value)
        try:
            await self.db.commit()
            await self.db.refresh(existing_forecast)
        except IntegrityError as e:
            await self.db.rollback()
            raise HTTPException(status_code=400, detail=f"Failed to update station {station_id}: {str(e)}")
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Internal error updating station {station_id}: {str(e)}")
        
        return CreditResponse.model_validate(existing_forecast)
