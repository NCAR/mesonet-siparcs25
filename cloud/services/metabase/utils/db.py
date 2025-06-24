import requests

class DatabaseService:
    def __init__(self, db_service_url: str):
        self.db_service_url = db_service_url

    def get_stations(self):
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