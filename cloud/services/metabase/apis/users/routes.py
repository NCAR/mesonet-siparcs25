from typing import List, cast
from fastapi import APIRouter, Depends
import requests
from users.user_services import UserServices
from utils.session import Session
from utils.config import Config
from logger import CustomLogger
from .schema import UserData, UserResponse

console = CustomLogger(name="metabase_db_logs", log_dir="/cloud/logs")
router = APIRouter(prefix="/metabase/users", tags=["Users"])
config = Config()

# Generate metabase session
def get_mb():
    email = config.metabase["admin_data"]["email"]
    password = config.metabase["admin_data"]["password"]
    metabase_base_url = config.metabase["base_url"]
    session = Session(console, metabase_base_url)
    session.create(email, password)

    try:
        yield session

    finally:
        session.close()

@router.get("/", response_model=List[UserResponse])
async def get_users(session: Session = Depends(get_mb)):
    async def __(user: UserServices):
        return await user.get_all_users()

    return await main(session, __)

@router.post("/", response_model=UserResponse | dict)
async def add_user(data: UserData, session: Session = Depends(get_mb)):
    async def __(user: UserServices):
        user_res = await user.add_user(data)

        if not user_res:
            return cast(dict, user_res)
        
        return cast(UserResponse, user_res)

    return await main(session, __)

async def main(session: Session, callback):
    try:
        user_service = UserServices(session, console)
        return await callback(user_service)
    
    except requests.exceptions.Timeout:
        console.exception("The request timed out")
    except requests.exceptions.ConnectionError as e:
        console.exception(f"Failed to connect to the server: {e}")
    except requests.exceptions.HTTPError as e:
        console.exception(f"HTTP error occurred: {e}")
        return {
            "error": True,
            "message": f"Ouch! There is something wrong with your request.",
            "status": e.response.status_code if e.response else 400,
            "reason": e.response.text if e.response else str(e),
        }
    except requests.exceptions.JSONDecodeError as e:
        console.exception(f"Response was not valid JSON. {e}")
    except requests.exceptions.RequestException as e:
        console.exception(f"An unexpected error occurred: {e}")
    except Exception as e:
        console.exception(f"Error occurred: {e}")
