from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from models.reading import ReadingModel
from schema.reading import ReadingCreate, ReadingResponse
from typing import List, Optional
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
        db_reading = ReadingModel(**reading_data.model_dump(), timestamp=datetime.utcnow())
        
        try:
            self.db.add(db_reading)
            await self.db.commit()
            await self.db.refresh(db_reading)
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Internal error creating reading {reading_data['id']}: {str(e)}")
        
        return ReadingResponse.model_validate(db_reading)

    async def update_reading(self, station_id: str, reading_id: str, update_data: ReadingCreate) -> Optional[ReadingResponse]:
        result = await self.db.execute(
            select(ReadingModel).where(
                ReadingModel.station_id == station_id,
                ReadingModel.id == reading_id
            )
        )
        reading = result.scalar_one_or_none()
        if reading is None:
            return None

        for key, value in update_data.model_dump().items():
            setattr(reading, key, value)

        await self.db.commit()
        await self.db.refresh(reading)
        return ReadingResponse.model_validate(reading)
