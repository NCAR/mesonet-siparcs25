import requests
from typing import List, Optional
from logger import CustomLogger
from .payload import Payload
from .groups import GroupService
from .type_c import DatabaseUser, MetabaseUserRes, MetabaseUserPayload

console = CustomLogger(name="mqtt_listerner.users", log_dir="/cloud/logs")

class UsersService(GroupService):
    def __init__(self, db_url: str, mb_url: str):
        super().__init__(logger=console, mb_url=mb_url)
        self.db_url = db_url
        self.mb_url = mb_url

    def __get(self, url: str) -> List[MetabaseUserRes]:
        url = url if url.endswith('/') else url + '/'
        res = requests.get(url)
        if not (200 <= res.status_code < 300):
            res.raise_for_status()
        return res.json()
    
    def __add(self, url: str, payload: MetabaseUserPayload) -> MetabaseUserRes:
        url = url if url.endswith('/') else url + '/'
        res = requests.post(url, json=payload)
        if not (200 <= res.status_code < 300):
            res.raise_for_status()
        return res.json()
    
    def __map_user(self, url: str, payload: MetabaseUserPayload) -> Optional[str]:
        users = self.__get(url=url)
        
        if any(user.get("email") == payload.get("email") for user in users):
            console.log(f"User {payload.get('email')} already mapped to the database.")
            return payload.get("email")

        user: DatabaseUser = self.__add(url=url, payload=payload)
        user_email = user.get("email")
        if user_email:
            console.log(f"User {user_email} mapped to the database successfully.")
            return user_email
        
    def __map_new_user(self, url: str, user_data: MetabaseUserPayload) -> Optional[str]:    
        payload = Payload() \
            .reset() \
            .set_attr("email", user_data.get("email")) \
            .set_attr("mb_user_id", user_data.get("id")) \
            .set_attr("mb_group_id", user_data.get("user_group_memberships")[0].get("id")) \
            .build()
        return self.__map_user(url, payload)

    def __map_existing_user(self, url: str, user_data: MetabaseUserPayload) -> Optional[str]:
        payload = Payload() \
            .reset() \
            .set_attr("email", user_data.get("email")) \
            .set_attr("mb_user_id", user_data.get("id")) \
            .set_attr("mb_group_id", user_data.get("group_ids")[0]) \
            .build()
        return self.__map_user(url, payload)
    
    def manage(self, station_data) -> Optional[MetabaseUserRes]:
        mb_url = f"{self.mb_url}/users"
        db_url = f"{self.db_url}/api/users/"

        """
        Deal with existing users
        """

        users: List[MetabaseUserRes] = self.__get(mb_url)
        for user in users:
            user_email = user.get('email')
            if station_data.get("email") == user_email:
                console.log(f"User {user_email} already exists in metabase.")

                console.log(f"Map user {user_email} to the database")
                mapped = self.__map_existing_user(url=db_url, user_data=user)
                if mapped:
                    return user
                
        """
        Deal with new users
        """
        
        user_data = Payload() \
            .reset() \
            .set_attr("first_name", station_data.get("firstname")) \
            .set_attr("last_name", station_data.get("lastname")) \
            .set_attr("email", station_data.get("email")) \
            .build()
        
        user_res: MetabaseUserRes = self.__add(mb_url, payload=user_data)
        # console.debug(user_res)
        if user_res.get("error"):
            console.warning(f"Error: {user_res.get('message')}: {user_res.get('reason')}")
            return
        
        console.log(f"User {user_res.get('email')} added to metabase successfully")

        # map user to the database
        mapped = self.__map_new_user(url=db_url, user_data=user_res)
        if mapped:
            console.log(f"Mapped user {user_res.get('email')} to the database")
        
        return user_res
