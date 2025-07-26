from datetime import datetime, timezone
from zoneinfo import ZoneInfo
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
        try:
            result = await self.db.execute(
                select(CreditModel).where(
                    CreditModel.station_id == forecast_data.station_id,
                    CreditModel.forecast_for == forecast_data.forecast_for
                )
            )
            existing_forecast = result.scalar_one_or_none()

            utc_now = datetime.now(ZoneInfo("UTC"))
            denver_time = utc_now.astimezone(ZoneInfo("America/Denver"))
            forecast_data_dict = {**forecast_data.model_dump(), "prediction_time": denver_time}

            if existing_forecast:
                for key, value in forecast_data_dict.items():
                    if hasattr(existing_forecast, key):
                        setattr(existing_forecast, key, value)
                await self.db.commit()
                await self.db.refresh(existing_forecast)
                return CreditResponse.model_validate(existing_forecast)

            new_forecast = CreditModel(**forecast_data_dict)
            self.db.add(new_forecast)
            await self.db.commit()
            await self.db.refresh(new_forecast)
            return CreditResponse.model_validate(new_forecast)

        except IntegrityError as e:
            await self.db.rollback()
            raise HTTPException(status_code=400, detail=f"Failed to forecast for station {forecast_data.station_id}: {str(e)}")
        except Exception as e:
            await self.db.rollback()
            print(e)
            raise HTTPException(status_code=500, detail=f"Internal error forecasting for station {forecast_data.station_id}: {str(e)}")


    async def update_forecast(self, station_id: str, forecast_data: CreditUpdate) -> CreditResponse:
        result = await self.db.execute(
            select(CreditModel).where(
                CreditModel.station_id == forecast_data.station_id,
                CreditModel.forecast_for == forecast_data.forecast_for.astimezone(timezone.utc)
            )
        )
        existing_forecast = result.scalar_one_or_none()
        updated_forecast = {**forecast_data.model_dump()}
        
        for key, value in updated_forecast.items():
            if hasattr(existing_forecast, key):
                setattr(existing_forecast, key, value)
        try:
            await self.db.commit()
            await self.db.refresh(existing_forecast)
        except IntegrityError as e:
            await self.db.rollback()
            raise HTTPException(status_code=400, detail=f"Failed to forecast for station {station_id}: {str(e)}")
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Internal error forecasting for station {station_id}: {str(e)}")
        
        return CreditResponse.model_validate(existing_forecast)
