from logger import CustomLogger
from utils.session import Session
from .user import User

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

    def get_all_users(self):
        self.users.get_users()
