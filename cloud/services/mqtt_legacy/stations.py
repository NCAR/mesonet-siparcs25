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

    def add_stations(self):
        path = f"{self.db_uri}/api/stations"

        for station in self.stations_data:
            utils_ftn.insert(path, station)
            # console.debug(f"Station posted. ID: {posted_station}")
        console.log("All stations added successfully.")
