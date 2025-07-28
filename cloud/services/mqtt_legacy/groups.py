from pydantic import EmailStr
from logger import CustomLogger
from utils import request, Payload, premium
from utils.type_c import \
    MetabaseGroupPayload as GroupPayload, \
    MetabaseGroupRes as GroupRes, \
    MetabaseUserRes as UserRes, \
    MetabaseMembership as MembershipPayload

class GroupService:
    def __init__(self, logger: CustomLogger, mb_url: str):
        self.console = logger
        self.mb_url = mb_url

    async def __add(self, path: str, payload: GroupPayload | MembershipPayload) -> GroupRes:
        url = f"{self.mb_url}/{path}"
        url = url if url.endswith('/') else url + '/'
        return await request.insert(url, payload)
    
    @premium("Available only in Metabase Pro Plans")
    async def membership(self, group_id: int, user_id: int) -> None:
        console = self.console
        payload: MembershipPayload = Payload() \
            .reset() \
            .set_attr("group_id", group_id) \
            .set_attr("is_group_manager", True) \
            .set_attr("user_id", user_id) \
            .build()
        
        membership_res = await self.__add(path="membership", payload=payload)
        console.debug(membership_res)

    async def create(self, station_id: str, email: EmailStr) -> GroupRes:
        console = self.console
        payload: GroupPayload = Payload() \
            .reset() \
            .set_attr("station_id", station_id) \
            .set_attr("email", email) \
            .build()
        
        group = await self.__add(path="group", payload=payload)
        if not group:
            console.log(f"Group with the sation ID {station_id} already exists.")
            return {}
        
        return group
    
    async def manage(self, user: UserRes, station_id: str) -> GroupRes:
        group = await self.create(station_id, user.get("email"))
        self.membership(group.get("id"), user.get("id"))
        return group
