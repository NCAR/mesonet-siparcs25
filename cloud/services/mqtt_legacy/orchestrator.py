import paho.mqtt.client as mqtt
from logger import CustomLogger
import requests
import random
import json
import os
import redis

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
        # console.log(f"Message received: {msg.payload}")

        decoded = msg.payload.decode()
        lines = decoded.strip().split('\n')
        readings = {}
        for line in lines:
            key, value = line.split(':', 1)
            readings[key.strip()] = value.strip()
        
        # add random station ids
        station_ids = [f"station{i}" for i in range(1, 6)]
        rand_staion_id = random.choice(station_ids)
        readings["station_id"] = rand_staion_id
        # console.debug(readings)

        # TODO: request to store readings using the table_name
        # console.log(f"Readings: {json.dumps(readings, indent=4)}")

        file_name = "dummy_station_data.json"
        stations = self.__load_dummy_data(file_name)
        # TODO: request to store stations using the table_name
        # console.log(f"Readings: {json.dumps(readings, indent=4)}")
        # console.debug(stations)
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
