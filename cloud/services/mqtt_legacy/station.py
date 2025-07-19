import os
import json
from utils import request, Payload
from logger import CustomLogger
from users import UsersService
from groups import GroupService
from frontend import FrontendService
from datetime import datetime, timezone

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
    
    async def __add_or_update_station(self, url: str, station: dict) -> None:
        console = self.console

        # Add created_at and last_active fields
        now = datetime.now(timezone.utc)
        station = {**station, "created_at": now.isoformat(), "last_active": now.isoformat()}

        # Add the station
        station_res: dict = await request.insert(url, station)
        station_id = station_res.get("station_id")

        filtered_station_res = {k: v for k, v in station_res.items() if v is not None and k not in ["created_at", "last_active"]}
        filtered_station = {k: v for k, v in station.items() if v is not None and k not in ["created_at", "last_active"]}

        if not (filtered_station_res == filtered_station):
            # Update the satation if necessary
            console.debug(f"Updating station: {station_id}")
            station_res: dict = await request.update_one(path=f"{url}/{station_id}", data=station)
        
        self.console.log(f"Station added or updated with ID: {station_id}")

    async def add_default_stations(self):
        console = self.console
        
        url = f"{self.db_url}/api/stations"

        for station in self.stations_data:
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

            # TODO: Manage collection/models/dashboards/cards at realtime in metabase
            # frontend = self.frontend.manage()

            # Add or update station data
            await self.__add_or_update_station(url, station)

    async def add_new_station(self, station_id, admin_data={}):
        station_data = Payload() \
            .reset() \
            .set_attr("station_id", station_id) \
            .set_attr("firstname", admin_data.get("first_name", "")) \
            .set_attr("lastname", admin_data.get("last_name", "")) \
            .set_attr("email", os.getenv("MB_ADMIN_EMAIL", "")) \
            .set_attr("altitude", 0.0) \
            .set_attr("organization", "NCAR") \
            .set_attr("device", "") \
            .set_attr("latitude", 40.01499) \
            .set_attr("longitude", -105.27055) \
            .build()
        
        # Add the station
        url = f"{self.db_url}/api/stations/"
        self.console.warning(station_data)
        station_res = await request.insert(url, station_data)
        station_id = station_res.get('station_id')
        self.console.log(f"Station added/refreshed with ID: {station_id}")

    async def get_stations(self):
        url = f"{self.db_url}/api/stations/"
        response = await request.get_all(url)

        if not response:
            return []
        return response
