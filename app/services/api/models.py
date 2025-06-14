from sqlalchemy import Column, Integer, String, Float, TIMESTAMP
from database import Database

db = Database()
Base = db.base

class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(String, unique=True, index=True, nullable=False)
    status = Column(String)
    longitude = Column(Float)
    latitude = Column(Float)
    timestamp = Column(TIMESTAMP)
