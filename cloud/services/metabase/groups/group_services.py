from typing import List
import requests
from apis.groups.schema import GroupCreate, GroupResponse
from logger import CustomLogger
from utils.session import Session
from utils.odm import ODM
from utils.payload import Payload

class GroupServices(ODM):
    def __init__(self, session: Session, logger: CustomLogger, name: str):
        self.__name = name
        self.__path = "permissions/group"
        self.session = session
        self.console = logger

    @property
    def name(self) -> str :
        return self.__name
    
    @property
    def path(self) -> str :
        return self.__path

    @name.setter
    def name(self, value) -> None :
        console = self.console
        if value:
            console.log("Seting a new group name")
            self.__name = value

    async def get_all(self) -> List[GroupResponse]:
        console = self.console
        res = await self.get_all_async(self.__path)
        data, msg, status = res.get("data"), res.get("message"), res.get("status")

        if not (data and msg and status):
            console.error("Error retrieving groups")
            raise requests.exceptions.HTTPError(res.text)
        
        console.log(f"{len(data)} groups retrieved successfully.")
        return data

    async def create(self, body: GroupCreate) -> GroupResponse:
        console = self.console
        name = f"{self.__name.lower()}_{body.name.lower()}"
        payload = Payload() \
            .reset() \
            .set_attr("name", name) \
            .build()
        
        groups = await self.get_all()
        if any(group.get("name") == name for group in groups):
            console.log(f"Group with station ID '{body.name}' already exists.")
            return {}

        res = await self.add_one_async(path=self.__path, data=payload)
        data, msg, status = res.get("data"), res.get("message"), res.get("status")

        if not (data and msg and status):
            console.error("Error creating group")
            raise requests.exceptions.HTTPError(res.text)
        
        console.log(f"Group {data.get('id')}: {msg.lower()}.\nStatus: {status}")
        return data

    async def register_member(self):
        pass
