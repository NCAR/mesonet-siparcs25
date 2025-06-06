import os
import yaml
from dotenv import load_dotenv
from string import Template
from connect_dbs import ConnectDB
from session import Session
from user import User
import requests

from logger import CustomLogger

console = CustomLogger()
load_dotenv()

# Read and expand environment variables before YAML parsing
with open("/app/configs/metabase.yaml", "r") as f:
    content = Template(f.read()).substitute(os.environ)

metabase_config = yaml.safe_load(content)
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

        session = Session(metabase_base_url)
        user = User(session)
        # Setup token is created just once. i.e. when there is no user
        setup_token = user.get_setup_token()

        user_data = self.settings.get("user_data")
        user_config = self.settings.get("config")

        if setup_token is not None:
            # Create new admin else admin already exists
            user.setup_initial_user(setup_token, user_data, user_config)

        # Now login and connect databases
        connect_db = ConnectDB(self.db_name, session)
        connect_db.connect(user_data.get("email"), user_data.get("password"), self.db_payload)

if __name__ == "__main__":
    try:
        Application(settings, db_name, db_payload)
    except requests.exceptions.Timeout:
        console.log("The request timed out")
    except requests.exceptions.ConnectionError:
        console.log("Failed to connect to the server")
    except requests.exceptions.HTTPError as err:
        console.log(f"HTTP error occurred: {err.response.status_code}")
    except requests.exceptions.JSONDecodeError:
        console.log("Response was not valid JSON")
    except requests.exceptions.RequestException as e:
        console.log(f"An unexpected error occurred: {e}")
    except Exception as e:
        console.log(f"Error occurred: {e}")
