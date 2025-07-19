from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from logger import CustomLogger
import os

db_name = os.getenv("ORCH_DB_NAME", "iotwx_db")
db_user = os.getenv("ORCH_DB_USER", "postgres")
db_host = os.getenv("ORCH_DB_HOST", "postgres")
db_pass = os.getenv("ORCH_DB_PASS", "postgres")
db_port = os.getenv("POSTGRES_PORT", 5432)
DATABASE_URL = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

console = CustomLogger()

# --- Async Engine and Session ---
async_engine = create_async_engine(DATABASE_URL, echo=True, future=True)
async_session = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

# --- Dependency for FastAPI ---
async def get_db_async() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session