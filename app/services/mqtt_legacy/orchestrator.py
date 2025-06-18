import paho.mqtt.client as mqtt
from logger import CustomLogger
from utils import utils_ftn
import requests
import random
import json
import os

console = CustomLogger()

class OrchestrateData:
    def __init__(self, table_name, topics, ip, port=1883):
        self.topics = topics
        self.ip = ip
        self.port = port
        self.table_name = table_name

        self.__listen_and_store_readings()

    def _on_connect(self, client, _, __, rc):
        console.log("Connected with result code " + str(rc))

        for topic in self.topics:
            client.subscribe(topic)

    def _on_message(self, _, __, msg):
        readings = {}
        decoded = msg.payload.decode()
        decoded = decoded.strip().split('\n')
        
        for data in decoded:
            key, value = data.split(':', 1)

            match key.strip():
                case "m":
                    readings["reading_value"] = value.strip()
                case "t":
                    readings["timestamp"] = utils_ftn.parse_unix_time(value.strip())
                case "rssi":
                    readings["signal_strength"] = value.strip()
                case "device":
                    device, station_id = utils_ftn.parse_device(value.strip())
                    readings["device"] = device
                    readings["station_id"] = station_id
                case "sensor":
                    protocol, model, measurement = utils_ftn.pass_sensor(value.strip())
                    readings["sensor_protocol"] = protocol
                    readings["sensor_model"] = model
                    readings["measurement"] = measurement
                case _:
                    return

        console.log(readings)
        
        # add random station ids
        station_ids = [f"station{i}" for i in range(1, 6)]
        rand_staion_id = random.choice(station_ids)
        readings["station_id"] = rand_staion_id
        # console.debug(f"Readings: {json.dumps(readings, indent=4)}")

        # TODO: request to store readings using the table_name
        # res = requests.get("http://database_api:8000/api/readings/")
        # res.raise_for_status()
        # console.log(res.json())

        file_name = "dummy_station_data.json"
        stations = self.__load_dummy_data(file_name)
        # console.debug(f"Stations: {json.dumps(stations, indent=4)}")

        # TODO: request to store stations using the table_name        
        # res = requests.get("http://database_api:8000/stations")
        # console.log(res.json())

    def __load_dummy_data(self, file_name):
        base_dir = os.path.dirname(__file__)
        file_path = os.path.join(base_dir, file_name)
        with open(file_path, "r") as f:
            return json.load(f)
    
    def __listen_and_store_readings(self):
        client = mqtt.Client()
        client.on_connect = self._on_connect
        client.on_message = self._on_message

        # TODO: Use env variable
        client.connect(self.ip, self.port, 60)
        client.loop_forever()
