import os
import requests
from typing import TypedDict
from logger import CustomLogger
from utils.session import Session
from utils.config import Config

from connect.mb_service import MetabaseService
from connect.db_services import DatabaseService
from dashboards.dash_services import DashboardServices
from cards.card_services import CardServices
from mb_collections.collection_services import CollectionServices
from models.model_services import ModelServices

console = CustomLogger(name="metabase_logs", log_dir="/cloud/logs")

class InitComponents(TypedDict):
    collection: CollectionServices
    dashboard: DashboardServices
    card: CardServices
    model: ModelServices
    database: DatabaseService

class Application:
    def __init__(self):
        config = Config()
        metabase_base_url = config.metabase["base_url"]
        self.session = Session(metabase_base_url)

        self.instances = self.__initialize(config) # Initialize all components
        console.log("Application components initialized successfully.")        

    def __initialize(self, config) -> InitComponents:
        db_name = os.getenv("ORCH_DB_NAME")
        db_payload = config.metabase["database"]
        db_service_url = config.database_api["base_url"]
        admin_data = config.metabase["admin_data"]
        mb_config = config.metabase["config"]

        metabase = MetabaseService(self.session, console, db_name, db_payload)
        mb_db_id = metabase.connect(admin_data, mb_config)

        if mb_db_id is None:
            console.error(f"Database '{db_name}' does not exist in Metabase. Please check your configuration.")
            raise ValueError(f"Database '{db_name}' does not exist in Metabase.")
        
        console.log(f"Database '{db_name}' is validated with ID: {mb_db_id}")

        card = CardServices(self.session, console, mb_db_id)
        model = ModelServices(self.session, console, mb_db_id)
        dashboard = DashboardServices(self.session, console, mb_db_id)
        collection = CollectionServices(self.session, console, mb_db_id)
        database = DatabaseService(db_service_url)

        return {
            "collection": collection,
            "dashboard": dashboard,
            "card": card,
            "model": model,
            "database": database,
        }

    def create_collection(self) -> list[str]:
        collection = self.instances.get("collection")
        parent_collection = collection.create_parent_collection()

        database = self.instances.get("database")
        stations = database.get_stations()
        if not len(stations):
            console.error("No station(s) found. Please ensure the database is populated with station data.")
            return
    
        return collection.create_stations_collection(stations, parent_collection)


    def create_model(self, station_id: str, collection_id="root") -> None:
        model = self.instances.get("model")
        model.create_station_pivot(station_id, collection_id)

    def create_dashcard(self, station_id: str, collection_id="root") -> None:
        card = self.instances.get("card")
        card.create_map_card(station_id, collection_id)

        dashboard = self.instances.get("dashboard")
        dashboard.create_dashboard(station_id, collection_id)
        dashboard.merge_card(card.id)

if __name__ == "__main__":
    try:
        app = Application()
        collection_ids = app.create_collection()
        console.debug(f"Created collections with IDs: {collection_ids}")

        for station_id, collection_id in collection_ids.items():
            console.debug(f"Creating model and dashcard for collection ID: {collection_id}")
            app.create_model(station_id, collection_id)
            app.create_dashcard(station_id, collection_id)
    
    except requests.exceptions.Timeout:
        console.exception("The request timed out")
    except requests.exceptions.ConnectionError as e:
        console.exception(f"Failed to connect to the server: {e}")
    except requests.exceptions.HTTPError as e:
        console.exception(f"HTTP error occurred: {e}")
    except requests.exceptions.JSONDecodeError as e:
        console.exception(f"Response was not valid JSON. {e}")
    except requests.exceptions.RequestException as e:
        console.exception(f"An unexpected error occurred: {e}")
    except Exception as e:
        console.exception(f"Error occurred: {e}")
