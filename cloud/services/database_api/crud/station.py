from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from models.station import StationModel
from schema.station import StationCreate, StationResponse, StationUpdate
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime, timezone
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

            db_station = StationModel(**station_data.model_dump())
            self.db.add(db_station)
            await self.db.commit()
            await self.db.refresh(db_station)
            return StationResponse.model_validate(db_station)

        except IntegrityError as e:
            await self.db.rollback()
            raise ValueError(f"Station with ID {station_data.station_id} already exists.") from e
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Internal error creating station {station_data['station_id']}: {str(e)}")

    async def update_station(self, station_id: str, update_data: StationUpdate) -> StationResponse:
        #console.info(f"Updating station {station_id} with data: {update_data.dict()}")

        result = await self.db.execute(select(StationModel).where(StationModel.station_id == update_data.station_id))
        station = result.scalar_one_or_none()
        data = update_data.dict(exclude_unset=True)

        if station:
            for key, value in data.items():
                if hasattr(station, key):
                    setattr(station, key, value)
            try:
                self.db.commit()
                self.db.refresh(station)
            except IntegrityError as e:
                self.db.rollback()
                raise HTTPException(status_code=400, detail=f"Failed to update station {station_id}: {str(e)}")
            except Exception as e:
                self.db.rollback()
                raise HTTPException(status_code=500, detail=f"Internal error updating station {station_id}: {str(e)}")
        else:
            data["station_id"] = station_id
            data.setdefault("firstname", None)
            data.setdefault("lastname", None)
            data.setdefault("email", None)
            data.setdefault("organization", None)
            if "created_at" not in data or data["created_at"] is None:
                data["created_at"] = datetime.now(timezone.utc)
            try:
                station = StationModel(**data)
                self.db.add(station)
                self.db.commit()
                self.db.refresh(station)
            except IntegrityError as e:
                self.db.rollback()
                raise HTTPException(status_code=400, detail=f"Failed to create station {station_id}: {str(e)}")
            except Exception as e:
                self.db.rollback()
                raise HTTPException(status_code=500, detail=f"Internal error creating station {station_id}: {str(e)}")
        
        return StationResponse.model_validate(station)