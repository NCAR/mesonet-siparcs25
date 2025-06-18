from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, Float, func
from sqlalchemy.orm import relationship
from database.connection import Base

class ReadingModel(Base):
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(String(255), ForeignKey("stations.station_id"), nullable=False)
    device = Column(String(255))
    measurement = Column(String(255))
    reading_value = Column(Float, nullable=False)
    sensor_protocol = Column(String(255))
    sensor_model = Column(String(255))
    timestamp = Column(TIMESTAMP, server_default=func.now())

    station = relationship("StationModel", back_populates="readings")
