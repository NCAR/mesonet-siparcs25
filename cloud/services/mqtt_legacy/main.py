from orchestrator import OrchestrateData
from logger import CustomLogger
import yaml
import requests

console = CustomLogger()

with open('/cloud/config.yaml', 'r') as f:
    mqtt_config = yaml.safe_load(f)["mqtt"]

class Application:
    def __init__(self, ip, topics, port):
        self.ip = ip
        self.topics = topics
        self.port = port

        table_to_write_to = "readings"
        OrchestrateData(table_to_write_to, self.topics, self.ip, self.port)

if __name__ == "__main__":
    try:
        host = mqtt_config["host"]
        topics = mqtt_config["topics"]
        port = mqtt_config["port"]

        Application(host, topics, port)

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
