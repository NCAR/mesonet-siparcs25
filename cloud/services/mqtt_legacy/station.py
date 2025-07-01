import os
import json
from utils import utils_ftn
from logger import CustomLogger
from users import MetabaseUsers

class StationService:
    def __init__(self, logger: CustomLogger, db_url: str, mb_url: str):
        self.console = logger
        self.console.debug(f"Initializing StationService with database URI: {db_url}")
        self.stations_data = self.__load_stations_data("stations_data.json")
        self.db_uri = db_url
        self.mb_url = mb_url

    def __load_stations_data(self, file_name):
        base_dir = os.path.dirname(__file__)
        file_path = os.path.join(base_dir, file_name)
        with open(file_path, "r") as f:
            return json.load(f)
        
    @DeprecationWarning
    def __add_station(self, data):
        db_path = f"{self.db_uri}/api/stations"
        for station in data:
            station_res = utils_ftn.insert(db_path, station)
            # console.debug(f"Station posted. ID: {posted_station}")
            self.console.log(f"Station added with ID: {station_res.get('station_id')}")

    @DeprecationWarning
    def add_default_stations(self):
        self.__add_station(self.stations_data)

    @DeprecationWarning
    def add_new_station(self, station_id, admin_data=None):
        station_data = {
            "station_id": station_id,
            "firstname": admin_data.get("first_name", ""),
            "lastname": admin_data.get("last_name", ""),
            "email": admin_data.get("email", ""),
            "latitude": 40.01499, # Default value, location to NCAR
            "longitude": -105.27055,  # Default value, location to NCAR
        }
        self.__add_station([station_data])

    def get_stations(self):
        path = f"{self.db_uri}/api/stations"
        response = utils_ftn.get_all(path)

        if not response:
            return []
    
        return response
    
    async def __add_station_async(self, data):
        db_path = f"{self.db_uri}/api/stations"
        for station in data:
            station_res = await utils_ftn.insert_async(db_path, station)
            # console.debug(f"Station posted. ID: {posted_station}")
            self.console.log(f"Station added with ID: {station_res.get('station_id')}")

    async def add_default_stations(self):
        await self.__add_station_async(self.stations_data)

    async def add_new_station(self, station_id, admin_data=None):
        station_data = {
            "station_id": station_id,
            "firstname": admin_data.get("first_name", ""),
            "lastname": admin_data.get("last_name", ""),
            "email": admin_data.get("email", ""),
            "latitude": 40.01499, # Default value, location to NCAR
            "longitude": -105.27055,  # Default value, location to NCAR
        }
        await self.__add_station_async([station_data])
    
    async def add_user(self, station_data):
        mb_users = MetabaseUsers(logger=self.console, url=self.mb_uri)
        mb_path = f"{self.mb_url}/users"
        await mb_users.get(path=mb_path)

        payload = {
            "first_name": station_data.get("firstname"),
            "last_name": station_data.get("lastname"),
            "email": station_data.get("email"),
            "password": "assas" # generate a temporal password
        }
