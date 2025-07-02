from sqlalchemy import TIMESTAMP, Column, ForeignKey, String, Float
from sqlalchemy.orm import relationship
from database.connection import Base

class StationModel(Base):
    __tablename__ = "stations"

    station_id = Column(String(255), primary_key=True, index=True)
    longitude = Column(Float)
    latitude = Column(Float)
    first_name = Column(String(255))
    last_name = Column(String(255))
    email = Column(String(255), ForeignKey("users.email"), nullable=False)
    timestamp = Column(TIMESTAMP)

    readings = relationship("ReadingModel", back_populates="station")
    user = relationship("UserModel", back_populates="stations")
