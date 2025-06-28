from typing import List
from fastapi import APIRouter, Depends
from users.user_services import UserServices
from utils.session import Session
from utils.config import Config
from logger import CustomLogger

console = CustomLogger(name="metabase_db_logs", log_dir="/cloud/logs")
router = APIRouter(prefix="/iotwx_api/users", tags=["Users"])
config = Config()

# Generate metabase session
def get_mb():
    email = config.metabase["admin_data"]["email"]
    password = config.metabase["admin_data"]["password"]
    metabase_base_url = config.metabase["base_url"]
    session = Session(metabase_base_url)
    session.create(email, password)

    try:
        yield session

    finally:
        session.close()

@router.get("/", response_model=List)
def get_users(session: Session = Depends(get_mb)):
    console.log(session.headers)
    console.log(session.base_url)
    # user = UserServices()
    return []
