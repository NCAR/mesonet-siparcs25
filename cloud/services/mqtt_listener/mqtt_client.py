import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import json
import time
from datetime import datetime
import requests
from typing import Dict, Any
from threading import Lock

# Configuration
MQTT_BROKER = "iotwx.ucar.edu"
MQTT_PORT = 1883
MQTT_TOPIC = "sensors/#"  # Subscribe to all sensor topics
API_BASE_URL = "http://database_api:8000"  # Adjust to your FastAPI server URL
STATION_ENDPOINT = f"{API_BASE_URL}/api/stations"
READING_ENDPOINT = f"{API_BASE_URL}/api/readings"

class MQTTDatabaseUpdater:
    def __init__(self, broker: str, port: int, api_base_url: str):
        self.broker = broker
        self.port = port
        self.api_base_url = api_base_url
        self.client = None
        self.connected = False
        self.last_connection_attempt = 0
        self.connection_interval = 30
        self.stations_lock = Lock()
        self.initialize_client()

    def initialize_client(self):
        self.client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="db_updater")
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            print(f"[info]: Connected to MQTT broker with code {reason_code}")
            self.connected = True
            self.client.subscribe(MQTT_TOPIC, qos=1)
            print(f"[info]: Subscribed to {MQTT_TOPIC}")
        else:
            print(f"[warn]: Connection failed: {reason_code}")
            self.connected = False

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        print(f"[warn]: Disconnected from MQTT broker, reason_code={reason_code}")
        self.connected = False

    def on_message(self, client, userdata, message):
        try:
            payload = message.payload.decode('utf-8')
            data = json.loads(payload)
            print(f"[info]: Received message on {message.topic}: {data}")

            station_id = data.get('station_id')
            if not station_id:
                print("[warn]: Missing station_id in message")
                return

            # Ignore keep_alive and disconnect messages
            if data.get('type') in ['keep_alive', 'disconnect']:
                print(f"[info]: Ignored {data.get('type')} message from {station_id}")
                return

            # Handle station_info messages
            if data.get('measurement') == 'station_info':
                self.handle_station_info(station_id, data)
            # Handle sensor readings
            else:
                self.handle_reading(station_id, data)

        except Exception as e:
            print(f"[error]: Failed to process message: {e}")

    def handle_station_info(self, station_id: str, data: Dict[str, Any]):
        # Prepare station data for StationCreate schema
        station_data = data.get('data', {})
        station_payload = {
            "station_id": station_id,
            "status": station_data.get('status', 'active'),  # Default to 'active'
            "longitude": float(station_data.get('longitude', 0.0)),
            "latitude": float(station_data.get('latitude', 0.0)),
            "firstname": station_data.get('firstname', ''),
            "lastname": station_data.get('lastname', ''),
            "email": station_data.get('email', '')
        }

        # Check if station exists
        try:
            response = requests.get(f"{STATION_ENDPOINT}/{station_id}")
            if response.status_code == 200:
                # Update existing station
                response = requests.put(f"{STATION_ENDPOINT}/{station_id}", json=station_payload)
                if response.status_code == 200:
                    print(f"[info]: Updated station {station_id}")
                else:
                    print(f"[error]: Failed to update station {station_id}: {response.text}")
            elif response.status_code == 404:
                # Create new station
                response = requests.post(STATION_ENDPOINT, json=station_payload)
                if response.status_code == 200:
                    print(f"[info]: Created new station {station_id}")
                else:
                    print(f"[error]: Failed to create station {station_id}: {response.text}")
            else:
                print(f"[error]: Error checking station {station_id}: {response.text}")
        except requests.RequestException as e:
            print(f"[error]: Failed to communicate with API for station {station_id}: {e}")

    def handle_reading(self, station_id: str, data: Dict[str, Any]):
        # Prepare reading data for ReadingCreate schema
        reading_data = data.get('data', {})
        # Handle different data formats
        if isinstance(reading_data, (int, float)):
            reading_value = float(reading_data)
            latitude = 0.0
            longitude = 0.0
        elif isinstance(reading_data, list) and len(reading_data) == 2:
            reading_value = 0.0  # GPS data, no reading value
            latitude = float(reading_data[0])
            longitude = float(reading_data[1])
        elif isinstance(reading_data, dict):
            reading_value = float(reading_data.get('value', 0.0))  # Adjust key if needed
            latitude = float(reading_data.get('latitude', 0.0))
            longitude = float(reading_data.get('longitude', 0.0))
        else:
            print(f"[warn]: Invalid data format for reading: {reading_data}")
            return

        reading_payload = {
            "station_id": station_id,
            "edge_id": data.get('to_edge_id',''),  # Use to_edge_id or edge_id
            "measurement": data.get('measurement', ''),
            "reading_value": reading_value,
            "sensor_model": data.get('sensor', 'unknown'),
            "latitude": latitude,
            "longitude": longitude
        }

        # Create new reading
        try:
            response = requests.post(READING_ENDPOINT, json=reading_payload)
            if response.status_code == 200:
                print(f"[info]: Created reading for station {station_id}, measurement {reading_payload['measurement']}")
            else:
                print(f"[error]: Failed to create reading for {station_id}: {response.text}")
        except requests.RequestException as e:
            print(f"[error]: Failed to communicate with API for reading {station_id}: {e}")

    def connect(self):
        current_time = time.time()
        if not self.connected and (current_time - self.last_connection_attempt >= self.connection_interval):
            try:
                print(f"[info]: Attempting to connect to {self.broker}:{self.port}")
                self.client.connect(self.broker, self.port, 120)
                self.last_connection_attempt = current_time
            except Exception as e:
                print(f"[error]: Failed to connect to broker: {e}")
                self.last_connection_attempt = current_time

    def start(self):
        self.client.loop_start()
        while True:
            if not self.connected:
                self.connect()
            time.sleep(1)

def main():
    updater = MQTTDatabaseUpdater(MQTT_BROKER, MQTT_PORT, API_BASE_URL)
    updater.start()

if __name__ == "__main__":
    main()