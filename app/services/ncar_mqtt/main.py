from orchestrator_data import OrchestrateData
from stations_db import StationsDB
import os
import yaml
import requests
from app.services.logger import CustomLogger

console = CustomLogger()

db_name = os.getenv("ORCH_DB_NAME", "iotwx_db")
db_user = os.getenv("ORCH_DB_USER", "postgres")
db_host = os.getenv("ORCH_DB_HOST", "postgres")
db_pass = os.getenv("ORCH_DB_PASS", "postgres")
db_port = os.getenv("POSTGRES_PORT", 5432)

con_string = f"dbname={db_name} user={db_user} password={db_pass} host={db_host} port={db_port}"

with open('/app/configs/mqtt.yaml', 'r') as f:
    mqtt_config = yaml.safe_load(f)

class Application:
    def __init__(self, con_string, ip, topics, port):
        self.con_string = con_string
        self.ip = ip
        self.topics = topics
        self.port = port

        stations = StationsDB(self.con_string, "stations")
        stations.create_table()
        stations.insert_station()
        OrchestrateData(self.con_string, "readings", self.topics, self.ip, self.port)

if __name__ == "__main__":
    try:
        host = mqtt_config["mqtt"]["host"]
        topics = mqtt_config["mqtt"]["topics"]
        port = mqtt_config["mqtt"]["port"]

        Application(con_string, host, topics, port)
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
