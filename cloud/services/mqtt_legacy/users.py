from typing import List, Optional
from utils import request, Payload
from logger import CustomLogger
from type_c import DatabaseUser, MetabaseExisitngUser, MetabaseNewUser

class UsersService:
    def __init__(self, logger: CustomLogger, db_url: str, mb_url: str):
        self.console = logger
        self.db_url = db_url
        self.mb_url = mb_url

    async def get(self, url: str) -> List[MetabaseExisitngUser]:
        url = url if url.endswith('/') else url + '/'
        return await request.get_all(url)
    
    async def add(self, url: str, payload) -> MetabaseNewUser | DatabaseUser:
        url = url if url.endswith('/') else url + '/'
        return await request.insert(url, payload)
    
    async def map_user(self, url: str, payload: MetabaseNewUser | MetabaseExisitngUser) -> Optional[str]:
        console = self.console
        users = await self.get(url=url)
        
        if any(user.get("email") == payload.get("email") for user in users):
            console.log(f"User {payload.get('email')} already mapped to the database.")
            return payload.get("email")

        user: DatabaseUser = await self.add(url=url, payload=payload)
        user_email = user.get("email")
        if user_email:
            console.log(f"User {user_email} mapped to the database successfully.")
            return user_email
        
    async def map_new_user(self, url: str, user_data: MetabaseNewUser) -> Optional[str]:    
        payload = Payload() \
            .reset() \
            .set_attr("email", user_data.get("email")) \
            .set_attr("mb_user_id", user_data.get("id")) \
            .set_attr("mb_group_id", user_data.get("user_group_memberships")[0].get("id")) \
            .build()
        return await self.map_user(url, payload)

    async def map_existing_user(self, url: str, user_data: MetabaseExisitngUser) -> Optional[str]:
        payload = Payload() \
            .reset() \
            .set_attr("email", user_data.get("email")) \
            .set_attr("mb_user_id", user_data.get("id")) \
            .set_attr("mb_group_id", user_data.get("group_ids")[0]) \
            .build()
        return await self.map_user(url, payload)
    
    async def manage(self, station_data) -> Optional[MetabaseNewUser | MetabaseExisitngUser]:
        console = self.console
        mb_url = f"{self.mb_url}/users"
        db_url = f"{self.db_url}/api/users/"

        """
        Deal with existing users
        """

        users: List[MetabaseExisitngUser] = await self.get(mb_url)
        for user in users:
            user_email = user.get('email')
            if station_data.get("email") == user_email:
                console.log(f"User {user_email} already exists in metabase.")

                console.log(f"Map user {user_email} to the database")
                mapped = await self.map_existing_user(url=db_url, user_data=user)
                if mapped:
                    return user
                
        """
        Deal with new users
        """
        
        user_data = Payload() \
            .reset() \
            .set_attr("first_name", station_data.get("first_name")) \
            .set_attr("last_name", station_data.get("last_name")) \
            .set_attr("email", station_data.get("email")) \
            .set_attr("password", "@siparcs255") \
            .build()
        
        user_res: MetabaseNewUser = await self.add(mb_url, payload=user_data)
        # console.debug(user_res)
        if user_res.get("error"):
            console.error(f"{user_res.get('message')}: {user_res.get('reason')}")
            return
        
        console.log(f"User {user_res.get('email')} added to metabase successfully")

        # map user to the database
        console.log(f"Map user {user_res.get('email')} to the database")
        mapped = await self.map_new_user(url=db_url, user_data=user_res)
        if mapped:
            return user_res
