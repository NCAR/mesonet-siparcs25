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

console = CustomLogger()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/iotwx_db")

class Database:
    def __init__(self):
        self.db = self.get_db()
        self.base = declarative_base()
        self.engine = create_engine(DATABASE_URL)

    def get_db(self):
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
