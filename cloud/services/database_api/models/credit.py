from sqlalchemy import TIMESTAMP, Column, Integer, String, Float
from database.connection import Base

class CreditModel(Base):
    __tablename__ = "credit_forecast"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    station_id = Column(String(255), nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    forecast_for = Column(TIMESTAMP(timezone=False), nullable=False)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    pressure = Column(Float, nullable=True)
    wind_speed = Column(Float, nullable=True)
    wind_direction = Column(Float, nullable=True)
    prediction_time = Column(TIMESTAMP(timezone=True), nullable=True)
