from fastapi import APIRouter
from utils.session import Session
from utils.config import Config
from logger import CustomLogger

logger = CustomLogger(name="metabase_db_logs", log_dir="/cloud/logs")
router = APIRouter(prefix="/metabase/users", tags=["Users"])
config = Config()

# Generate metabase session
def get_mb():
    email = config.metabase["admin_data"]["email"]
    password = config.metabase["admin_data"]["password"]
    metabase_base_url = config.metabase["base_url"]
    session = Session(logger, metabase_base_url)
    session.create(email, password)

    try:
        yield session

    finally:
        session.close()
