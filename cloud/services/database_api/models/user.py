from sqlalchemy import Column, Integer, String, DateTime, func
from database.connection import Base

class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    mb_user_id = Column(Integer, nullable=False)
    mb_group_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
