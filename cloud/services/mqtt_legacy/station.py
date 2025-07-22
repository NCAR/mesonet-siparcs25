import os
import json
from redis_c import RedisClient
from utils import request, Payload, Config
from logger import CustomLogger
from users import UsersService
from groups import GroupService
from frontend import FrontendService
from datetime import datetime, timezone

class StationService:
    def __init__(self, logger: CustomLogger, config: Config):
        self.console = logger
        self.stations_data = self.__load_stations_data("stations_data.json")
        self.db_url = config.database_api["base_url"]
        self.mb_url = config.metabase["orch_url"]
        self.users = UsersService(logger, self.db_url, self.mb_url)
        self.groups = GroupService(logger, self.mb_url)
        self.frontend = FrontendService(logger, self.mb_url)

        # Initialize Redis client
        redis_host = config.redis["host"]
        redis_port = config.redis["port"]
        self.active_station_timeout = config.station['active_station_timeout']
        self.redis_client = RedisClient(logger, redis_host, redis_port)

    def __load_stations_data(self, file_name):
        base_dir = os.path.dirname(__file__)
        file_path = os.path.join(base_dir, file_name)
        with open(file_path, "r") as f:
            return json.load(f)
    
    async def __add_or_update_station(self, url: str, station: dict) -> None:
        console = self.console

        # Add created_at and last_active fields
        now = datetime.now(timezone.utc)
        station = {**station, "created_at": now.isoformat(), "last_active": now.isoformat(), "altitude": station.get("altitude", 0.0)}

        # Add the station
        station_res: dict = await request.insert(url, station)
        station_id = station_res.get("station_id")

        filtered_station_res = {k: v for k, v in station_res.items() if v is not None and k not in ["created_at", "last_active"]}
        filtered_station = {k: v for k, v in station.items() if v is not None and k not in ["created_at", "last_active"]}

        if not (filtered_station_res == filtered_station):
            # Update the satation if necessary
            console.debug(f"Updating station: {station_id}")
            station_res: dict = await request.update_one(path=f"{url}/{station_id}", data=station)

        # Add or update the station in Redis
        await self.add_station_to_redis(station_res)
        
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
            .set_attr("email", admin_data.get("email", "")) \
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
    
    async def add_station_to_redis(self, station_data: dict):
        """Add or update a station in Redis."""

        console = self.console
        station_id = station_data.get("station_id")

        if not station_id:
            console.error("Station ID is required to add/update a station in Redis.")
            return
        
        redis_key = f"station:{station_id}"
        redis_station_data = {
            "latitude": str(station_data.pop("latitude", 39.9784)),
            "longitude": str(station_data.pop("longitude", -105.2749)),
            "altitude": str(station_data.pop("altitude", 0.0)),
            "metadata": json.dumps(station_data)
        }

        await self.redis_client.hset(redis_key, mapping=redis_station_data)
        # await self.redis_client.expire(redis_key, self.active_station_timeout)

        console.log(f"[Redis]: Updated station {station_id}.")
