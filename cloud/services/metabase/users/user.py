from logger import CustomLogger
from utils.session import Session
from utils.odm import ODM

class User(ODM):
    def __init__(self, session: Session, logger: CustomLogger):
        super().__init__(session)
        self.console = logger
        self.console.debug("Initializing User management")

    def get_token(self):
        path = "session/properties"
        res_data = self.get_all(path)
        self.setup_token = res_data.get("setup-token")
        return self.setup_token

    def add_admin(self, data) -> str:
        res_data = self.add_one(path="setup", data=data)
        token = res_data.get('id')
        self.console.log(f"Admin created and login sucessfully with token {token}")
        return token

    def get_users(self):
        res_data = self.get_all(path="setup")
        self.console.log(f"{len(res_data)} users retrieved successfully")
