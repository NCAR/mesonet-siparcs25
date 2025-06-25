import os
import yaml
import requests
from dotenv import load_dotenv
from string import Template
from connect.dbs import ConnectDB
from utils.session import Session
from utils.db import DatabaseService
from users.user import User
from logger import CustomLogger
from dashboards.dashboard import Dashboard
from cards.card import Card
from mb_collections.collection import Collection
from models.model import Model
from typing import TypedDict

console = CustomLogger(name="metabase_logs", log_dir="/cloud/logs")

class InitComponents(TypedDict):
    collection: Collection
    dashboard: Dashboard
    card: Card
    model: Model
    user: User
    db_service: DatabaseService
    mb_db: ConnectDB

class Application:
    def __init__(self, settings, db_name, db_payload, metabase_base_url, db_service_url=None):
        self.settings = settings
        self.db_name = db_name
        self.db_payload = db_payload
        self.db_service_url = db_service_url
        self.session = Session(metabase_base_url)

        self.instances = self.__initialize() # Initialize all components
        console.log("Application components initialized successfully.")
        self.__connect_db() # Connect to Metabase and validate the database

    def __initialize(self) -> InitComponents:
        collection = Collection(self.session, console)
        dashboard = Dashboard(self.session, console)
        card = Card(self.session, console)
        user = User(self.session, console)
        mb_db = ConnectDB(self.session, console, self.db_name)
        model = Model(self.session, console)
        db_service = DatabaseService(self.db_service_url)

        return {
            "collection": collection,
            "dashboard": dashboard,
            "card": card,
            "model": model,
            "user": user,
            "db_service": db_service,
            "mb_db": mb_db
        }

    def __connect_db(self) -> None:
        user = self.instances.get("user")
        # Setup token is created just once. i.e. when there is no user
        setup_token = user.get_setup_token()

        user_data = self.settings.get("user_data")
        user_config = self.settings.get("config")

        if setup_token is not None:
            # Create new admin else admin already exists
            console.log("Authenticating the Admin ...")
            user.setup_initial_user(setup_token, user_data, user_config)

        # Now login and connect databases
        console.log(f"Connecting to Metabase database: {self.db_name}")
        mb_db = self.instances.get("mb_db")
        mb_db.connect(user_data.get("email"), user_data.get("password"), self.db_payload)

    def create_collection(self) -> list[str]:
        created_collections = {} # Dict to store created collections
        collection = self.instances.get("collection")
        collection.name = "IoTwx Collection"
        collection.description = "Collection for IoTwx related dashboards and cards"

        stations = self.instances.get("db_service").get_stations()
        if not len(stations):
            console.error("No station(s) found. Please ensure the database is populated with station data.")
            return "root"  # Default to root if no stations are found
        
        # Create a parent collection if it doesn't exist
        console.log(f"Creating parent collection: {collection.name}")
        parent_id = collection.create()
        if parent_id is None:
            console.error("Failed to create parent collection. Exiting.")
            return []
        console.log(f"Parent collection created with ID: {parent_id}")
        
        for station in stations:
            station_id: str = station.get("station_id")
            collection.name = f"{station_id.capitalize()} Collection"
            collection.description = f"Collection for {station_id} station related dashboards and cards"
            console.log(f"Creating collection: {collection.name}")
            created_collections[station_id] = collection.create(parent_id)

        return created_collections

    def create_model(self, station_id: str, collection_id="root") -> None:
        model = self.instances.get("model")
        mb_db = self.instances.get("mb_db")
        db_id = mb_db.validate_db()
        if db_id is None:
            console.error("Database validation failed. Exiting.")
            return
    
        measurement_query = model.build_measurement_query(station_id)
        measurement = model.get_measurements(measurement_query, db_id, collection_id)
        # console.debug(f"Fetched measurements: {measurement}")
        model_query = model.build_pivot_query(measurement, station_id)
        model_name = f"{station_id}'s Readings"

        if len(measurement) and model_query:
            card = self.instances.get("card")
            card.name = model_name
            question = {
                "type": "native",
                "native": {"query": model_query},
                "database": db_id
            }
            console.log(f"Creating model card: {card.name} for station: {station_id}")
            card.create(question=question, display="table", collection_id=collection_id)

    def create_dashcard(self, station_id: str, collection_id="root") -> None:
        dashboard = self.instances.get("dashboard")
        dashboard.name = f"{station_id}'s Dashboard"

        card = self.instances.get("card")
        card.name = f"{station_id}'s Map"

        mb_db = self.instances.get("mb_db")
        db_id = mb_db.validate_db()

        question = {
            "type": "native",
            "native": {"query": "SELECT * FROM stations LIMIT 10"},
            "database": db_id
        }
        visualization = {
            "map.latitude_column": "latitude",
            "map.longitude_column": "longitude",
            "color_enabled": False,
            "size_enabled": False,
            "map.type": "pin"
        }

        console.log(f"Creating dashboard: {dashboard.name}")
        dash_id = dashboard.create(collection_id)

        console.log(f"Creating card: {card.name} for dashboard: {dashboard.name}")
        card_id = card.create(question, display="map", vis_settings=visualization, collection_id=collection_id)
        
        if dash_id is None or card_id is None:
            console.error("Failed to create dashboard or card. Exiting.")
            return
        console.log(f"Adding card: {card.name} (id={card_id}) to dashboard: {dashboard.name} (id={dash_id})")
        # Add card to dashboard
        dashboard.add_card(dash_id, card_id)
        console.log(f"Dashboard '{dashboard.name}' with card '{card.name}' created successfully.")

if __name__ == "__main__":
    try:
        load_dotenv()
        # Read and expand environment variables before YAML parsing
        with open("/cloud/config.yaml", "r") as f:
            content = Template(f.read()).substitute(os.environ)

        if not content.strip():
            raise ValueError("Configuration file is empty or not properly formatted.")

        configs = yaml.safe_load(content)
        metabase_config = configs["metabase"]
        settings = {
            "user_data": metabase_config["admin_data"],
            "config": metabase_config["config"]
        }
        db_name = os.getenv("ORCH_DB_NAME")
        db_payload = metabase_config["database"]
        metabase_base_url = metabase_config["base_url"]
        db_base_url = configs["database_api"]["base_url"]

        app = Application(settings, db_name, db_payload, metabase_base_url, db_service_url=db_base_url)
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
