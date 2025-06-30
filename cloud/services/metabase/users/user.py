from logger import CustomLogger
from utils.session import Session
from utils.odm import ODM
from apis.users.types import APIResponse

class User(ODM):
    def __init__(self, session: Session, logger: CustomLogger):
        super().__init__(session)
        self.console = logger
        self.console.debug("Initializing User management")

    def get_token(self):
        res_data = self.get_all(path="session/properties")
        self.setup_token = res_data.get("setup-token")
        return self.setup_token

    def add_admin(self, data) -> str:
        res_data = self.add_one(path="setup", data=data)
        token = res_data.get('id')
        self.console.log(f"Admin created and login sucessfully with token {token}")
        return token

    async def get_users(self) -> list:
        res = await self.get_all_async(path="user")
        res_data = res.get("data", [])
        if res_data:
            self.console.log(f"{len(res_data)} users retrieved successfully")
        return res_data

    async def add_user(self, payload) -> APIResponse:
        res = await self.add_one_async(path="user", data=payload)
        res_data = res.get("data", {})
        if res_data:
            self.console.log(f"User {res_data.get('email')} has been added successfully.")
        return res_data
