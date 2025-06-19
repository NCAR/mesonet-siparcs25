from sqlalchemy import TIMESTAMP, Column, Integer, String, Float
from sqlalchemy.orm import relationship
from database.connection import Base

class StationModel(Base):
    __tablename__ = "stations"

    station_id = Column(Integer, primary_key=True, index=True)
    longitude = Column(Float)
    latitude = Column(Float)
    firstname = Column(String(50))
    lastname = Column(String(50))
    email = Column(String(20))
    timestamp = Column(TIMESTAMP)

    readings = relationship("ReadingModel", back_populates="station")
