from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from models.reading import ReadingModel
from schema.reading import ReadingCreate, ReadingResponse
from typing import List, Optional
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from logger import CustomLogger

console = CustomLogger()

class ReadingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_readings(self) -> List[ReadingResponse]:
        result = await self.db.execute(select(ReadingModel))
        readings = result.scalars().all()
        return [ReadingResponse.model_validate(r) for r in readings]

    async def get_readings_by_station_id(self, station_id: str) -> List[ReadingResponse]:
        result = await self.db.execute(
            select(ReadingModel).where(ReadingModel.station_id == station_id)
        )
        readings = result.scalars().all()
        return [ReadingResponse.model_validate(r) for r in readings]

    async def create_reading(self, reading_data: ReadingCreate) -> ReadingResponse:
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