from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from models.station import StationModel
from schema.station import StationCreate, StationResponse
from typing import List, Optional
from datetime import datetime
from logger import CustomLogger

console = CustomLogger()

class StationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_stations(self) -> List[StationResponse]:
        result = await self.db.execute(select(StationModel))
        stations = result.scalars().all()
        return [StationResponse.model_validate(s) for s in stations]

    async def get_station(self, station_id: str) -> Optional[StationResponse]:
        result = await self.db.execute(
            select(StationModel).where(StationModel.station_id == station_id)
        )
        station = result.scalar_one_or_none()
        if station:
            return StationResponse.model_validate(station)
        return None

    async def create_station(self, station_data: StationCreate) -> StationResponse:
        try:
            # Check for existing station
            result = await self.db.execute(
                select(StationModel).where(StationModel.station_id == station_data.station_id)
            )
            existing_station = result.scalar_one_or_none()
            if existing_station:
                return StationResponse.model_validate(existing_station)

            db_station = StationModel(**station_data.model_dump(), timestamp=datetime.utcnow())
            self.db.add(db_station)
            await self.db.commit()
            await self.db.refresh(db_station)
            return StationResponse.model_validate(db_station)

        except IntegrityError as e:
            await self.db.rollback()
            raise ValueError(f"Station with ID {station_data.station_id} already exists.") from e

    async def update_station(self, station_id: str, update_data: StationCreate) -> Optional[StationResponse]:
        result = await self.db.execute(
            select(StationModel).where(StationModel.station_id == station_id)
        )
        station = result.scalar_one_or_none()

        if not station:
            return None

        for key, value in update_data.model_dump().items():
            setattr(station, key, value)

        await self.db.commit()
        await self.db.refresh(station)
        return StationResponse.model_validate(station)
