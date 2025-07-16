import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import json
import time
from datetime import datetime, timezone
import requests
import redis
import yaml
from typing import Dict, Any
from threading import Lock, Thread

# Configuration
CONFIG_FILE = "/cloud/config.yaml"

# Load and validate configuration
try:
    with open(CONFIG_FILE, 'r') as f:
        config = yaml.safe_load(f)
except Exception as e:
    print(f"[error]: Failed to load {CONFIG_FILE}: {e}")
    exit(1)

# Validate required fields
required_fields = {
    'mqtt': ['host', 'port', 'msg_topic'],
    'database_api': ['base_url'],
    'redis': ['host', 'port'],
    'station': ['active_station_timeout', 'batch_interval'],
    'model_service': ['base_url']
}
for section, fields in required_fields.items():
    if section not in config:
        print(f"[error]: Missing section '{section}' in {CONFIG_FILE}")
        exit(1)
    for field in fields:
        if field not in config[section]:
            print(f"[error]: Missing field '{field}' in section '{section}' of {CONFIG_FILE}")
            exit(1)

# Configuration parameters
MQTT_BROKER = config['mqtt']['host']
MQTT_PORT = config['mqtt']['port']
MQTT_TOPIC = config['mqtt']['msg_topic']
API_BASE_URL = config['database_api']['base_url']
REDIS_HOST = config['redis']['host']
REDIS_PORT = config['redis']['port']
ACTIVE_STATION_TIMEOUT = config['station']['active_station_timeout']
BATCH_INTERVAL = config['station']['batch_interval']
MODEL_SERVICE_URL = config['model_service']['base_url']
MODEL_SERVICE_MODEL_NAME = config['model_service']['model_name']
MODEL_ENDPOINT = f"{MODEL_SERVICE_URL}/predict"
STATION_ENDPOINT = f"{API_BASE_URL}/api/stations"
READING_ENDPOINT = f"{API_BASE_URL}/api/readings/"

def get_current_timestamp():
    return datetime.now(timezone.utc).isoformat()

class MQTTDatabaseUpdater:
    def __init__(self, broker: str, port: int, api_base_url: str, redis_host: str, redis_port: int, active_station_timeout: int, batch_interval: int, model_service_url: str):
        self.broker = broker
        self.port = port
        self.api_base_url = api_base_url
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.active_station_timeout = active_station_timeout
        self.batch_interval = batch_interval
        self.model_service_url = model_service_url
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.client = None
        self.connected = False
        self.last_connection_attempt = 0
        self.connection_interval = 30
        self.stations_lock = Lock()
        self.sensor_buffer = {}
        self.buffer_lock = Lock()
        self.initialize_client()
        self.test_redis_connection()
        self.test_api_connections()
        self.batch_thread = Thread(target=self.process_batch, daemon=True)
        self.batch_thread.start()

    def test_redis_connection(self):
        try:
            self.redis_client.ping()
            print(f"[info]: Connected to Redis at {self.redis_host}:{self.redis_port}")
        except redis.ConnectionError as e:
            print(f"[error]: Failed to connect to Redis: {e}")
            exit(1)

    def test_api_connections(self):
        try:
            response = requests.get(f"{self.api_base_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"[info]: Connected to database API at {self.api_base_url}")
            else:
                print(f"[warn]: Database API health check failed: {response.status_code} {response.text}")
        except requests.RequestException as e:
            print(f"[error]: Failed to connect to database API: {e}")
            exit(1)
        try:
            response = requests.get(f"{self.model_service_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"[info]: Connected to model service at {self.model_service_url}")
            else:
                print(f"[warn]: Model service health check failed: {response.status_code} {response.text}")
        except requests.RequestException as e:
            print(f"[error]: Failed to connect to model service: {e}")
            exit(1)

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

    def query_model_service(self, station_id: str, sensor_data: Dict[str, Any], model_name: str) -> str:
        payload = {
            "model": model_name,
            "data": json.dumps(sensor_data)
        }
        try:
            response = requests.post(MODEL_ENDPOINT, json=payload, headers={"Content-Type": "application/json"}, timeout=200)
            if response.status_code == 200:
                print(f"[info]: Successfully queried {model_name} for station {station_id}")
                return response.json().get("result", "")
            else:
                print(f"[error]: Failed to query {model_name} for station {station_id}: {response.text}")
                return ""
        except requests.RequestException as e:
            print(f"[error]: Failed to communicate with model_service for {model_name}: {e}")
            return ""

    def merge_sensor_data(self, existing_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
        merged_data = existing_data.copy()
        if "data" not in merged_data:
            merged_data["data"] = {}
        for sensor, measurements in new_data["data"].items():
            if sensor not in merged_data["data"]:
                merged_data["data"][sensor] = {}
            merged_data["data"][sensor].update(measurements)
        return merged_data

    def merge_metadata(self, existing_metadata: Dict[str, Any], new_metadata: Dict[str, Any]) -> Dict[str, Any]:
        merged_metadata = existing_metadata.copy()
        merged_metadata.update(new_metadata)
        return merged_metadata

    def process_batch(self):
        while True:
            time.sleep(self.batch_interval)
            with self.buffer_lock:
                if not self.sensor_buffer:
                    continue
                print(f"[info]: Processing batch for {len(self.sensor_buffer)} stations")
                stations_to_remove = []
                current_time = datetime.now(timezone.utc)
                for station_id, station_data in list(self.sensor_buffer.items()):
                    redis_key = f"station:{station_id}"
                    try:
                        # Check if station is inactive based on last_active timestamp
                        last_active_str = station_data["metadata"].get("last_active")
                        if last_active_str:
                            try:
                                last_active = datetime.fromisoformat(last_active_str)
                                time_diff = (current_time - last_active).total_seconds()
                                if time_diff > self.active_station_timeout:
                                    stations_to_remove.append(station_id)
                                    print(f"[info]: Station {station_id} inactive for {time_diff}s, marking for removal from buffer")
                                    continue
                            except ValueError:
                                print(f"[warn]: Invalid last_active timestamp for station {station_id}: {last_active_str}")

                        sensor_data = {"data": station_data["data"]}
                        existing_redis_data = self.redis_client.hget(redis_key, "data") or "{}"
                        existing_sensor_data = json.loads(existing_redis_data)
                        existing_redis_metadata = self.redis_client.hget(redis_key, "metadata") or "{}"
                        existing_metadata = json.loads(existing_redis_metadata)

                        merged_sensor_data = self.merge_sensor_data(existing_sensor_data, sensor_data)
                        merged_metadata = self.merge_metadata(existing_metadata, station_data["metadata"])
                        model_names = [MODEL_SERVICE_MODEL_NAME]
                        model_summaries = {}
                        if merged_sensor_data:
                            for model_name in model_names:
                                summary = self.query_model_service(station_id, {**merged_sensor_data, "timestamp": get_current_timestamp()}, model_name)
                                if summary:
                                    model_summaries[model_name] = summary
                        # Update buffer with merged data to keep it up-to-date
                        self.sensor_buffer[station_id]["data"] = merged_sensor_data["data"]
                        self.sensor_buffer[station_id]["metadata"] = merged_metadata
                        redis_station_data = {
                            'data': json.dumps(merged_sensor_data),
                            'metadata': json.dumps(merged_metadata),
                            'model_summaries': json.dumps(model_summaries),
                            'latitude': str(merged_metadata.get('latitude', '39.9784')),
                            'longitude': str(merged_metadata.get('longitude', '-105.2749')),
                            'altitude': str(merged_metadata.get('altitude', '1624.0'))
                        }
                        self.redis_client.hset(redis_key, mapping=redis_station_data)
                        self.redis_client.expire(redis_key, self.active_station_timeout)
                        print(f"[info]: Updated Redis for station {station_id}: data={merged_sensor_data}, metadata={merged_metadata}, model_summaries={model_summaries}")

                    except (redis.RedisError, json.JSONDecodeError) as e:
                        print(f"[error]: Failed to update Redis for station {station_id}: {e}")
                        # Keep buffer data intact to maintain up-to-date info

                # Remove stations not in Redis or inactive from buffer
                for station_id in stations_to_remove:
                    del self.sensor_buffer[station_id]
                    print(f"[info]: Removed station {station_id} from buffer")
                    
    def on_message(self, client, userdata, message):
        try:
            payload = message.payload.decode('utf-8')
            data = json.loads(payload)
            print(f"[info]: Received message on {message.topic}: {data}")

            station_id = data.get('station_id')
            if not station_id:
                print("[warn]: Missing station_id in message")
                return

            if data.get('type') in ['keep_alive', 'disconnect']:
                print(f"[info]: Ignored {data.get('type')} message from {station_id}")
                return

            timestamp = get_current_timestamp()
            if data.get('type') == 'station_info':
                self.handle_station_info(station_id, data, timestamp)
            else:
                self.handle_reading(station_id, data, timestamp)

        except json.JSONDecodeError as e:
            print(f"[error]: Failed to decode MQTT payload: {e}")
        except Exception as e:
            print(f"[error]: Failed to process message for sensor {data.get('sensor', 'unknown')}: {type(e).__name__}: {str(e)}")

    def handle_station_info(self, station_id: str, station_data: Dict[str, Any], timestamp: str):
        # Convert last_active to ISO8601 datetime string
        # Convert timestamp to ISO8601 and use for last_active and created_at
        ts_raw = station_data.get('timestamp', timestamp)
        ts_iso = ts_raw
        if isinstance(ts_raw, (int, float)):
            ts_st = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            ts_iso = ts_st.isoformat()
        station_data['last_active'] = ts_iso
        station_data['created_at'] = ts_iso
        # Remove fields not in Station schema
        station_data.pop('timestamp', None)
        station_data.pop('type', None)
        station_data.pop('target_id', None)
        station_data.pop('allow_relay', None)
        print(f"[info]: Processing station_info for {station_id}")
        print(station_data)

        try:
            response = requests.get(f"{STATION_ENDPOINT}/{station_id}", timeout=5)
            if response.status_code == 200:
                response = requests.put(f"{STATION_ENDPOINT}/{station_id}", json=station_data, headers={"Content-Type": "application/json"}, timeout=5)
                if response.status_code == 200:
                    print(f"[info]: Updated station {station_id} in Postgres")
                else:
                    print(f"[error]: Failed to update station {station_id} in Postgres: {response.status_code} {response.text}")
            elif response.status_code == 404:
                response = requests.post(STATION_ENDPOINT, json=station_data, headers={"Content-Type": "application/json"}, timeout=5)
                if response.status_code == 200:
                    print(f"[info]: Created station {station_id} in Postgres")
                else:
                    print(f"[error]: Failed to create station {station_id} in Postgres: {response.status_code} {response.text}")
            else:
                print(f"[error]: Error checking station {station_id} in Postgres: {response.status_code} {response.text}")
        except requests.RequestException as e:
            print(f"[error]: Failed to communicate with Postgres for station {station_id}: {e}")

        try:
            redis_key = f"station:{station_id}"
            redis_station_data = {
                'metadata': json.dumps(station_data),
                'latitude': str(station_data.get('latitude', '39.9784')),
                'longitude': str(station_data.get('longitude', '-105.2749')),
                'altitude': str(station_data.get('altitude', '1624.0')),
            }
            self.redis_client.hset(redis_key, mapping=redis_station_data)
            self.redis_client.expire(redis_key, self.active_station_timeout)
            print(f"[info]: Updated station {station_id} in Redis: {redis_station_data}")
        except redis.RedisError as e:
            print(f"[error]: Failed to update Redis for station {station_id}: {e}")

    def handle_reading(self, station_id: str, data: Dict[str, Any], timestamp: str):
        reading_value = str(data.get('reading_value', ''))
        measurement = data.get('measurement', '')
        sensor = data.get('sensor', 'unknown')
        ts_raw = data.get('timestamp', timestamp)
        ts_iso = ts_raw
        if isinstance(ts_raw, (int, float)):
            ts_st = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            ts_iso = ts_st.isoformat()
        
        with self.buffer_lock:
            # Check and create keys if they don't exist
            if station_id not in self.sensor_buffer:
                self.sensor_buffer[station_id] = {"data": {}, "metadata": {}}
            if "data" not in self.sensor_buffer[station_id]:
                self.sensor_buffer[station_id]["data"] = {}
            if sensor not in self.sensor_buffer[station_id]["data"] and measurement not in ['latitude', 'longitude', 'altitude']:
                self.sensor_buffer[station_id]["data"][sensor] = {}
            if "metadata" not in self.sensor_buffer[station_id]:
                self.sensor_buffer[station_id]["metadata"] = {}

            if measurement not in ['latitude', 'longitude', 'altitude']:
                self.sensor_buffer[station_id]["data"][sensor][measurement] = reading_value
                self.sensor_buffer[station_id]["metadata"]['last_active'] = ts_iso
                if data.get('target_id'):
                    self.sensor_buffer[station_id]["metadata"]['target_id'] = data.get('target_id')
                if data.get('rssi'):
                    self.sensor_buffer[station_id]["metadata"]['rssi'] = str(data.get('rssi'))
            else:
                if measurement == 'latitude':
                    self.sensor_buffer[station_id]["metadata"]['latitude'] = reading_value
                elif measurement == 'altitude':
                    self.sensor_buffer[station_id]["metadata"]['altitude'] = reading_value
                else:
                    self.sensor_buffer[station_id]["metadata"]['longitude'] = reading_value
                self.sensor_buffer[station_id]["metadata"]['last_active'] = ts_iso
                if data.get('target_id'):
                    self.sensor_buffer[station_id]["metadata"]['target_id'] = data.get('target_id')
                if data.get('rssi'):
                    self.sensor_buffer[station_id]["metadata"]['rssi'] = str(data.get('rssi'))

        if measurement not in ['latitude', 'longitude', 'altitude']:
            latitude = self.sensor_buffer[station_id]["metadata"].get('latitude', None)
            longitude = self.sensor_buffer[station_id]["metadata"].get('longitude', None)
            altitude = self.sensor_buffer[station_id]["metadata"].get('altitude', None)
            if not latitude or not longitude or not altitude:
                print(f"[warn]: Missing lat/lon/alt for station {station_id}, cannot create reading")
                return
            reading_payload = {
                "station_id": station_id,
                "edge_id": data.get('target_id', ''),
                "measurement": measurement,
                "reading_value": reading_value,
                "sensor_model": sensor,
                "sensor_protocol": data.get('sensor_protocol', 'unknown'),
                "latitude": latitude,
                "longitude": longitude,
                "altitude": altitude,
                "timestamp": ts_iso,
                "rssi": data.get('rssi', 0)
            }

            try:
                response = requests.post(READING_ENDPOINT, json=reading_payload, headers={"Content-Type": "application/json"}, timeout=5)
                if response.status_code == 200:
                    print(f"[info]: Created reading for station {station_id}, measurement {measurement} in Postgres")
                else:
                    print(f"[error]: Failed to create reading for {station_id} in Postgres: {response.status_code} {response.text}")
                response = requests.put(f"{STATION_ENDPOINT}/{station_id}", json={"last_active": data.get("timestamp", timestamp)}, headers={"Content-Type": "application/json"}, timeout=5)
                if response.status_code == 200:
                    print(f"[info]: Updated station {station_id} last_active in Postgres")
                else:
                    print(f"[error]: Failed to update station {station_id} last_active in Postgres: {response.status_code} {response.text}")
 
            except requests.RequestException as e:
                print(f"[error]: Failed to communicate with Postgres for reading {station_id}: {e}")
            
        else:  
            try:
                station_payload = {
                    "station_id": station_id,
                    **self.sensor_buffer[station_id]["metadata"],
                }
                station_payload['last_active'] = data.get("timestamp", timestamp)
                station_payload.pop('timestamp', None)
                station_payload.pop('target_id', None)
                station_payload.pop('type', None)
                station_payload.pop('allow_relay', None)
                response = requests.put(f"{STATION_ENDPOINT}/{station_id}", json=station_payload, headers={"Content-Type": "application/json"}, timeout=5)
                if response.status_code == 200:
                    print(f"[info]: Updated station {station_id} latitude/longitude in Postgres")
                else:
                    print(f"[error]: Failed to update station {station_id} latitude/longitude in Postgres: {response.status_code} {response.text}")
            except requests.RequestException as e:
                print(f"[error]: Failed to communicate with Postgres for station {station_id}: {e}")

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
    updater = MQTTDatabaseUpdater(
        MQTT_BROKER,
        MQTT_PORT,
        API_BASE_URL,
        REDIS_HOST,
        REDIS_PORT,
        ACTIVE_STATION_TIMEOUT,
        BATCH_INTERVAL,
        MODEL_SERVICE_URL
    )
    updater.start()

if __name__ == "__main__":
    main()