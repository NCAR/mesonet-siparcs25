import yaml
import requests
from orchestrator import OrchestrateData
from logger import CustomLogger

console = CustomLogger(name="mqtt_logs", log_dir="/cloud/logs")

class Application:
    def __init__(self, ip, topics, port, db_base_url, admin_data=None):
        OrchestrateData(console, db_uri=db_base_url, topics=topics, ip=ip, port=port, admin_data=admin_data)

if __name__ == "__main__":
    try:
        with open('/cloud/config.yaml', 'r') as f:
            config = yaml.safe_load(f)

        if not config:
            raise ValueError("Configuration file is empty or not properly formatted.")
        
        host = config["mqtt"]["host"]
        topics = config["mqtt"]["topics"]
        port = config["mqtt"]["port"]
        db_base_url = config["database_api"]["base_url"]
        admin_data = config["metabase"]["admin_data"]

        Application(host, topics, port, db_base_url, admin_data)

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
