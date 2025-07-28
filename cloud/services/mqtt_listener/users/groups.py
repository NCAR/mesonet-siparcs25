import requests
from pydantic import EmailStr
from logger import CustomLogger
from .payload import Payload
from .type_c import \
    MetabaseGroupPayload as GroupPayload, \
    MetabaseGroupRes as GroupRes, \
    MetabaseMembership as MembershipPayload

class GroupService:
    def __init__(self, logger: CustomLogger, mb_url: str):
        self.console = logger
        self.mb_url = mb_url

    def __add(self, path: str, payload: GroupPayload | MembershipPayload) -> GroupRes:
        url = f"{self.mb_url}/{path}"
        url = url if url.endswith('/') else url + '/'
        res = requests.post(url, json=payload)
        if not (200 <= res.status_code < 300):
            res.raise_for_status()
        return res.json()

    def create_group(self, station_id: str, email: EmailStr) -> GroupRes:
        console = self.console
        payload: GroupPayload = Payload() \
            .reset() \
            .set_attr("station_id", station_id) \
            .set_attr("email", email) \
            .build()
        
        group = self.__add(path="group", payload=payload)
        if not group:
            console.log(f"Group with the sation ID {station_id} already exists.")
            return {}
        
        return group
