from utils.session import Session
from logger import CustomLogger
from .collection import Collection

class CollectionServices:
    def __init__(self, session: Session, logger: CustomLogger, db_id: int):
        self.console = logger
        self.collection = Collection(session, logger)
        self.db_id = db_id

    def create_parent_collection(self) -> int | str:
        self.console.log(f"Creating parent collection: {self.collection.name}")
        self.collection.name = "IoTwx Collection"
        self.collection.description = "Collection for IoTwx related dashboards and cards"
        parent_id = self.collection.create()
        if parent_id is None:
            self.console.error("Failed to create parent collection. Exiting.")
            return "root"
        self.console.log(f"Parent collection created with ID: {parent_id}")

        return parent_id

    def create_stations_collection(self, stations: list[str], parent_id: str = "root") -> dict:
        created_collections = {}   
        for station in stations:
            station_id: str = station.get("station_id")
            self.collection.name = f"{station_id.capitalize()} Collection"
            self.collection.description = f"Collection for {station_id} station related dashboards and cards"
            self.console.log(f"Creating collection: {self.collection.name}")
            created_collections[station_id] = self.collection.create(parent_id)

        return created_collections