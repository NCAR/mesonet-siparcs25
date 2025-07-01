import os
import json
from utils import request, Payload
from logger import CustomLogger
from users import MetabaseUsers

class StationService:
    def __init__(self, logger: CustomLogger, db_url: str, mb_url: str):
        self.console = logger
        self.stations_data = self.__load_stations_data("stations_data.json")
        self.db_uri = f"{db_url}/api/stations/"
        self.mb_users = MetabaseUsers(logger=logger, base_url=mb_url)

    def __load_stations_data(self, file_name):
        base_dir = os.path.dirname(__file__)
        file_path = os.path.join(base_dir, file_name)
        with open(file_path, "r") as f:
            return json.load(f)
    
    async def __add_station(self, data):
        for station in data:
            station_res = await request.insert(self.db_uri, station)
            station_id = station_res.get('station_id')
            self.console.log(f"Station added/refreshed with ID: {station_id}")

            if station_id:
                await self.add_user(station_res)

    async def add_default_stations(self):
        await self.__add_station(self.stations_data)

    async def add_new_station(self, station_id, admin_data=None):
        station_data = {
            "station_id": station_id,
            "firstname": admin_data.get("first_name", ""),
            "lastname": admin_data.get("last_name", ""),
            "email": admin_data.get("email", ""),
            "latitude": 40.01499, # Default value, location to NCAR
            "longitude": -105.27055,  # Default value, location to NCAR
        }
        await self.__add_station([station_data])

    async def get_stations(self):
        response = await request.get_all(self.db_uri)

        if not response:
            return []
        return response
    
    async def add_user(self, station_data):
        console = self.console
        path = "users"

        users = await self.mb_users.get(path)
        if any(station_data.get("email") == user.get("email") for user in users):
            console.warning(f"User {station_data.get('email')} already exists in metabase.")
            return
        
        user_data = Payload() \
            .reset() \
            .set_attr("first_name", station_data.get("firstname")) \
            .set_attr("last_name", station_data.get("lastname")) \
            .set_attr("email", station_data.get("email")) \
            .set_attr("password", "asss") \
            .build()
        
        user_res = await self.mb_users.add(path, payload=user_data)
        # console.debug(user_res)
        if user_res.get("error"):
            console.error(f"{user_res.get('message')}: {user_res.get('reason')}")
            return
        
        console.log(f"User {user_res.get('email')} added successfully")
