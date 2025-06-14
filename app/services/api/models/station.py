from sqlalchemy import Column, Integer, String, Float, TIMESTAMP
from database.connection import Base

class StationModel(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(String, unique=True, index=True, nullable=False)
    status = Column(String)
    longitude = Column(Float)
    latitude = Column(Float)
    firstname = Column(String)
    lastname = Column(String)
    email = Column(String)
    timestamp = Column(TIMESTAMP)
