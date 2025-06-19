import yaml
import requests
from orchestrator import OrchestrateData
from logger import CustomLogger
from stations import StationService

console = CustomLogger()

with open('/cloud/config.yaml', 'r') as f:
    mqtt_config = yaml.safe_load(f)

class Application:
    def __init__(self, ip, topics, port, db_base_url):
        station_mdl = StationService(db_uri=db_base_url)
        station_mdl.add_stations()
        OrchestrateData(db_uri=db_base_url, topics=topics, ip=ip, port=port)

if __name__ == "__main__":
    try:
        host = mqtt_config["mqtt"]["host"]
        topics = mqtt_config["mqtt"]["topics"]
        port = mqtt_config["mqtt"]["port"]
        db_base_url = mqtt_config["database_api"]["base_url"]

        Application(host, topics, port, db_base_url)

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
