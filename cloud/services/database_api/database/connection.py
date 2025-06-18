from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from logger import CustomLogger
import os

db_name = os.getenv("ORCH_DB_NAME", "iotwx_db")
db_user = os.getenv("ORCH_DB_USER", "postgres")
db_host = os.getenv("ORCH_DB_HOST", "postgres")
db_pass = os.getenv("ORCH_DB_PASS", "postgres")
db_port = os.getenv("POSTGRES_PORT", 5432)
DATABASE_URL = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

console = CustomLogger()
Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
