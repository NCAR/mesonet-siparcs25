from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, Float, func
from sqlalchemy.orm import relationship
from database.connection import Base

class ReadingModel(Base):
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(String(255), ForeignKey("stations.station_id"), nullable=False)
    edge_id = Column(String(255), nullable=True)
    measurement = Column(String(255), nullable=False)
    reading_value = Column(Float, nullable=False)
    sensor_protocol = Column(String(255), nullable=True)
    rssi = Column(Integer, nullable=True)
    sensor_model = Column(String(255), nullable=False)  # Changed to non-nullable to match ReadingCreate
    timestamp = Column(TIMESTAMP(timezone=True), nullable=True, server_default=func.now())
    longitude = Column(Float, nullable=False)  # Changed to non-nullable to match ReadingCreate
    latitude = Column(Float, nullable=False)  # Changed to non-nullable to match ReadingCreate
    altitude = Column(Float, nullable=False)  # Changed to non-nullable to match ReadingCreate
    
    station = relationship("StationModel", back_populates="readings")
