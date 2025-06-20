import os
import json
from utils import utils_ftn
from logger import CustomLogger

console = CustomLogger()

class StationService:
    def __init__(self, db_uri):
        self.stations_data = self.__load_stations_data("stations_data.json")
        self.db_uri = db_uri

    def __load_stations_data(self, file_name):
        base_dir = os.path.dirname(__file__)
        file_path = os.path.join(base_dir, file_name)
        with open(file_path, "r") as f:
            return json.load(f)
        
    def __add_station(self, data):
        path = f"{self.db_uri}/api/stations"
        for station in data:
            res = utils_ftn.insert(path, station)
            # console.debug(f"Station posted. ID: {posted_station}")
            console.debug(f"Station added with ID: {res.get('station_id')}")

    def add_default_stations(self):
        self.__add_station(self.stations_data)

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

