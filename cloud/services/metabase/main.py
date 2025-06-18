import os
import yaml
import requests
from dotenv import load_dotenv
from string import Template
from connect_dbs import ConnectDB
from session import Session
from user import User
from logger import CustomLogger
from dashboard import Dashboard
from card import Card

console = CustomLogger()
load_dotenv()

# Read and expand environment variables before YAML parsing
with open("/cloud/config.yaml", "r") as f:
    content = Template(f.read()).substitute(os.environ)

metabase_config = yaml.safe_load(content)["metabase"]
settings = {
    "user_data": metabase_config["admin_data"],
    "config": metabase_config["config"]
}
db_name = os.getenv("ORCH_DB_NAME")
db_payload = metabase_config["database"]
metabase_base_url = metabase_config["base_url"]

class Application:
    def __init__(self, settings, db_name, db_payload):
        self.settings = settings
        self.db_name = db_name
        self.db_payload = db_payload
        self.session = Session(metabase_base_url)

        # Metabase attributes
        self.mb_db = None
        self.connect_db()

    def connect_db(self):
        user = User(self.session)
        # Setup token is created just once. i.e. when there is no user
        setup_token = user.get_setup_token()

        user_data = self.settings.get("user_data")
        user_config = self.settings.get("config")

        if setup_token is not None:
            # Create new admin else admin already exists
            user.setup_initial_user(setup_token, user_data, user_config)

        # Now login and connect databases
        self.mb_db = ConnectDB(self.db_name, self.session)
        self.mb_db.connect(user_data.get("email"), user_data.get("password"), self.db_payload)

    def create_dashboard(self):
        db_id = self.mb_db.validate_db()
        card_name = "Stations Map"
        dash_name = "IoTwx Dashboard"
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

        card = Card(self.session, card_name, question)
        card_id = card.create(display="map", vis_settings=visualization)

        dashboard = Dashboard(self.session, dash_name)
        dash_id = dashboard.create()

        # console.debug(f"db_id: {dash_id}, card_id: {card_id}")
        dashboard.add_card(dash_id, card_id)

if __name__ == "__main__":
    try:
        app = Application(settings, db_name, db_payload)
        app.create_dashboard()
    
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
