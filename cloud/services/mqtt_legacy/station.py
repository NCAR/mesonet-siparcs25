import os
import json
from utils import request, Payload
from logger import CustomLogger
from users import UsersService
from groups import GroupService
from frontend import FrontendService

class StationService:
    def __init__(self, logger: CustomLogger, db_url: str, mb_url: str):
        self.console = logger
        self.stations_data = self.__load_stations_data("stations_data.json")
        self.db_url = db_url
        self.users = UsersService(logger, db_url, mb_url)
        self.groups = GroupService(logger, mb_url)
        self.frontend = FrontendService(logger, mb_url)

    def __load_stations_data(self, file_name):
        base_dir = os.path.dirname(__file__)
        file_path = os.path.join(base_dir, file_name)
        with open(file_path, "r") as f:
            return json.load(f)
    
    async def __add_station(self, data):
        console = self.console
        url = f"{self.db_url}/api/stations/"

        for station in data:
            # Manage a user at realtime
            user = await self.users.manage(station)
            if not (user and user.get("email")):
                console.warning("The user already exists in the database.")

            # Manage a group at realtime
            station_id = station.get("station_id", "test")
            group = await self.groups.manage(user, station_id)
            if group:
                group_name = group.get("name")
                console.log(f"Group '{group_name}' has been added successfully")

            # Manage collection/models/dashboards/cards at realtime in metabase
            frontend = self.frontend.manage()

            # Add the station
            station_res = await request.insert(url, station)
            station_id = station_res.get('station_id')
            self.console.log(f"Station added/refreshed with ID: {station_id}")

    async def add_default_stations(self):
        await self.__add_station(self.stations_data)

    async def add_new_station(self, station_id, admin_data=None):
        station_data = Payload() \
            .reset() \
            .set_attr("station_id", station_id) \
            .set_attr("first_name", admin_data.get("first_name", "")) \
            .set_attr("last_name", admin_data.get("last_name", "")) \
            .set_attr("email", admin_data.get("email")) \
            .set_attr("latitude", 40.01499) \
            .set_attr("longitude", -105.27055) \
            .build()

        await self.__add_station([station_data])

    async def get_stations(self):
        url = f"{self.db_url}/api/stations/"
        response = await request.get_all(url)

        if not response:
            return []
        return response
