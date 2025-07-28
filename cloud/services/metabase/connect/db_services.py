import requests
from typing import TypedDict

class Station(TypedDict):
    station_id: str
    longitude: float
    latitude: float
    firstname: str
    lastname: str
    email: str

class DatabaseService:
    def __init__(self, db_service_url: str):
        self.db_service_url = db_service_url

    def get_stations(self) -> list[Station]:
        """
        Retrieves all stations from the database.
        """
        path = f"{self.db_service_url}/api/stations"
        res = requests.get(path)
        res.raise_for_status()
        response = res.json()
        if not response:
            return []
    
        return response