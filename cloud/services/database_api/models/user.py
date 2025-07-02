from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from database.connection import Base

class UserModel(Base):
    __tablename__ = "users"

    email = Column(String(100), primary_key=True, index=True)
    mb_user_id = Column(Integer, nullable=False)
    mb_group_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    # One-to-many relationship: a user has many stations
    stations = relationship("StationModel", back_populates="user", cascade="all, delete-orphan")