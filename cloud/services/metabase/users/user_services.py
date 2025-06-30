from logger import CustomLogger
from utils.session import Session
from .user import User
from utils.payload import Payload
from apis.users.types import UserData, APIResponse

class UserServices:
    def __init__(self, session: Session, logger: CustomLogger):
        self.users = User(session, logger)

    def get_cached_setup_token(self):
        return self.users.get_token()
    
    def setup_initial_user(self, setup_token, user_data, prefs) -> str:
        body = {
            "token": setup_token,
            "user": user_data,
            "prefs": prefs
        }
        return self.users.add_admin(body)

    async def get_all_users(self):
        return await self.users.get_users()
    
    async def add_user(self, data: UserData) -> APIResponse:
        payload = Payload() \
            .reset() \
            .set_attr("email", data.email) \
            .set_attr("first_name", data.first_name) \
            .set_attr("last_name", data.last_name) \
            .build()
        
        return await self.users.add_user(payload)
