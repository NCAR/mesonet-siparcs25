import requests
from typing import List
from apis.groups.schema import GroupCreate, GroupResponse, Membership, MembershipRes, MembershipMap, APIResponse
from logger import CustomLogger
from utils.session import Session
from utils.odm import ODM
from utils.payload import Payload
from fastapi import status

class GroupServices(ODM):
    def __init__(self, session: Session, logger: CustomLogger, name: str):
        self.__name = name
        self.session = session
        self.console = logger

    @property
    def name(self) -> str :
        return self.__name

    @name.setter
    def name(self, value) -> None :
        console = self.console
        if value:
            console.log("Seting a new group name")
            self.__name = value

    async def __already_a_member(self, path: str, user_id: int, group_id: int) -> bool:
        membership_map: MembershipMap = await self.get_all(path)
        user_membership = membership_map.get(str(user_id))

        if not user_membership:
            return False

        return any(m.get("group_id") == group_id for m in user_membership)

    async def get_all(self, path: str) -> List[GroupResponse] | MembershipMap:
        console = self.console
        res = await self.get_all_async(path)
        data, msg, status = res.get("data"), res.get("message"), res.get("status")

        if not (data and msg and status):
            console.error("Error retrieving groups/members")
            raise requests.exceptions.HTTPError(res.text)

        return data

    async def create(self, path: str, body: GroupCreate) -> GroupResponse:
        console = self.console
        name = f"{self.__name.lower()}_{body.name.lower()}"
        payload = Payload() \
            .reset() \
            .set_attr("name", name) \
            .build()
        
        groups: List[GroupResponse] = await self.get_all(path)
        console.log(f"{len(data)} groups retrieved successfully.")
        if any(group.get("name") == name for group in groups):
            console.log(f"Group with station ID '{body.name}' already exists.")
            return {}

        res = await self.add_one_async(path=path, data=payload)
        data, msg, status = res.get("data"), res.get("message"), res.get("status")

        if not (data and msg and status):
            console.error("Error creating group")
            raise requests.exceptions.HTTPError(res.text)
        
        console.log(f"Group {data.get('id')}: {msg.lower()}.\nStatus: {status}")
        return data

    async def membership(self, path: str, body: Membership) -> APIResponse[MembershipRes]:
        console = self.console
        user_id, group_id, is_group_manager = body.user_id, body.group_id, body.is_group_manager

        is_already_a_member = await self.__already_a_member(path, user_id, group_id)
        if is_already_a_member:
            console.log(f"User {user_id} is already a member of group {group_id}")
            return {
                "message": f"User {user_id} is already a member of group {group_id}",
                "data": {},
                "status": status.HTTP_400_BAD_REQUEST
            }

        console.log(f"Registering user '{user_id}' in group '{group_id}'")
        payload = Payload() \
            .reset() \
            .set_attr("group_id", group_id) \
            .set_attr("is_group_manager", is_group_manager) \
            .set_attr("user_id", user_id) \
            .build()
        
        res = await self.add_one_async(path=path, data=payload)
        data: MembershipRes = res.get("data")
        msg: str = res.get("message")
        status_code: int = res.get("status")

        if not (data and msg and status_code):
            console.error(f"Error assigning user {user_id} to group {group_id}")
            raise requests.exceptions.HTTPError(res.text)
        
        console.log(f"User {user_id}: {msg.lower()}. to group {group_id}\nStatus: {status_code}")
        return res
