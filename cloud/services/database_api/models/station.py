from sqlalchemy import TIMESTAMP, Column, Integer, String, Float, func
from sqlalchemy.orm import relationship
from database.connection import Base

class StationModel(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(String(255), unique=True, nullable=False)
    device = Column(String(50),nullable=True)
    longitude = Column(Float)
    latitude = Column(Float)
    altitude = Column(Float,nullable=True)
    firstname = Column(String(50),nullable=True)
    lastname = Column(String(50),nullable=True)
    email = Column(String(50),nullable=True)
    organization = Column(String(50),nullable=True)
    last_active = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP)
    readings = relationship("ReadingModel", back_populates="station")
