import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import json
import time
from datetime import datetime, timezone, timedelta
import requests
import redis
import yaml
from typing import Dict, Any
from threading import Lock

# Configuration
CONFIG_FILE = "config.yml"

# Load and validate configuration
try:
    with open(CONFIG_FILE, 'r') as f:
        config = yaml.safe_load(f)
except Exception as e:
    print(f"[error]: Failed to load {CONFIG_FILE}: {e}")
    exit(1)

# Validate required fields
required_fields = {
    'mqtt': ['broker_ip', 'broker_port', 'topic'],
    'database_api': ['base_url'],
    'redis': ['host', 'port'],
    'station': ['active_station_timeout']
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
MQTT_BROKER = config['mqtt']['broker_ip']
MQTT_PORT = config['mqtt']['broker_port']
MQTT_TOPIC = config['mqtt']['topic']
API_BASE_URL = config['database_api']['base_url']
REDIS_HOST = config['redis']['host']
REDIS_PORT = config['redis']['port']
ACTIVE_STATION_TIMEOUT = config['station']['active_station_timeout']

STATION_ENDPOINT = f"{API_BASE_URL}/api/stations"
READING_ENDPOINT = f"{API_BASE_URL}/api/readings"

# Current timestamp for MDT (UTC-6)
def get_current_timestamp():
    mdt_offset = timedelta(hours=-6)
    return datetime.now(timezone(mdt_offset)).isoformat()

class MQTTDatabaseUpdater:
    def __init__(self, broker: str, port: int, api_base_url: str, redis_host: str, redis_port: int, active_station_timeout: int):
        self.broker = broker
        self.port = port
        self.api_base_url = api_base_url
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.active_station_timeout = active_station_timeout
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.client = None
        self.connected = False
        self.last_connection_attempt = 0
        self.connection_interval = 30
        self.stations_lock = Lock()
        self.initialize_client()
        self.test_redis_connection()

    def test_redis_connection(self):
        try:
            self.redis_client.ping()
            print(f"[info]: Connected to Redis at {self.redis_host}:{self.redis_port}")
        except redis.ConnectionError as e:
            print(f"[error]: Failed to connect to Redis: {e}")
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

    def get_redis_coordinates(self, station_id: str) -> tuple[float, float]:
        """Retrieve last seen latitude and longitude from Redis."""
        redis_key = f"station:{station_id}"
        try:
            lat = self.redis_client.hget(redis_key, 'latitude')
            lon = self.redis_client.hget(redis_key, 'longitude')
            return (float(lat) if lat else 0.0, float(lon) if lon else 0.0)
        except redis.RedisError as e:
            print(f"[error]: Failed to get coordinates from Redis for {station_id}: {e}")
            return (0.0, 0.0)

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

            # Use message timestamp or current MDT time
            timestamp = get_current_timestamp()
            data['timestamp'] = timestamp

            # Handle station_info messages
            if data.get('measurement') == 'station_info':
                self.handle_station_info(station_id, data, timestamp)
            # Handle sensor readings (including latitude/longitude)
            else:
                self.handle_reading(station_id, data, timestamp)

        except Exception as e:
            print(f"[error]: Failed to process message: {e}")
    def convert_message_to_db_format(message_payload: str) -> Dict[str, Any]:
        """
        Convert MQTT message to a dictionary with keys in the format <measurement>(<sensor[:5]>) or <field>(<value>).

        Args:
            message_payload: JSON-encoded MQTT message payload.

        Returns:
            Dictionary with key-value pairs in the format {<measurement>(<sensor[:5]>): data} for readings,
            or {<field>(<value>): value} for station_info fields.
            Returns empty dict for invalid messages or ignored types (keep_alive, disconnect).
        """
        try:
            data = json.loads(message_payload)
        except json.JSONDecodeError as e:
            print(f"[error]: Invalid JSON in message: {e}")
            return {}

        station_id = data.get('station_id')
        if not station_id:
            print("[warn]: Missing station_id in message")
            return {}

        # Ignore keep_alive and disconnect messages
        if data.get('type') in ['keep_alive', 'disconnect']:
            print(f"[info]: Ignored {data.get('type')} message from {station_id}")
            return {}

        result = {}

        if data.get('measurement') == 'station_info':
            # Handle station_info: include all fields from data
            station_data = data.get('data', {})
            for field, value in station_data.items():
                key = f"{field}({str(value)[:5].lower()})"
                result[key] = value
        else:
            # Handle readings
            measurement = data.get('measurement', '')
            sensor = data.get('sensor', 'unknown')
            sensor_prefix = sensor[:5].lower()
            key = f"{measurement}({sensor_prefix})"
            value = data.get('data')
            if value is not None:
                result[key] = value

        return result

    def update_station_activity(self, station_id: str, timestamp: str):
        try:
            redis_key = f"station:{station_id}"
            self.redis_client.hset(redis_key, 'last_active', timestamp)
            self.redis_client.expire(redis_key, self.active_station_timeout)
            print(f"[info]: Updated activity for station {station_id} in Redis")
        except redis.RedisError as e:
            print(f"[error]: Failed to update activity for station {station_id} in Redis: {e}")

    def handle_station_info(self, station_id: str, station_data: Dict[str, Any], timestamp: str):
        station_payload = {
            "station_id": station_id,
            "longitude": float(station_data.get('longitude', 0.0)),
            "latitude": float(station_data.get('latitude', 0.0)),
            "firstname": station_data.get('firstname', ''),
            "lastname": station_data.get('lastname', ''),
            "email": station_data.get('email', '')
        }

        # Update Postgres
        try:
            response = requests.get(f"{STATION_ENDPOINT}/{station_id}")
            if response.status_code == 200:
                response = requests.put(f"{STATION_ENDPOINT}/{station_id}", json=station_payload)
                if response.status_code == 200:
                    print(f"[info]: Updated station {station_id} in Postgres")
                else:
                    print(f"[error]: Failed to update station {station_id} in Postgres: {response.text}")
            elif response.status_code == 404:
                response = requests.post(STATION_ENDPOINT, json=station_payload)
                if response.status_code == 200:
                    print(f"[info]: Created station {station_id} in Postgres")
                else:
                    print(f"[error]: Failed to create station {station_id} in Postgres: {response.text}")
            else:
                print(f"[error]: Error checking station {station_id} in Postgres: {response.text}")
        except requests.RequestException as e:
            print(f"[error]: Failed to communicate with Postgres for station {station_id}: {e}")

        # Update Redis metadata
        try:
            redis_key = f"station:{station_id}"
            redis_station_data = self.convert_message_to_db_format(json.dumps(station_data))
            self.redis_client.hset(redis_key, mapping=redis_station_data)
            self.redis_client.expire(redis_key, self.active_station_timeout)
            print(f"[info]: Updated station {station_id} metadata in Redis")
        except redis.RedisError as e:
            print(f"[error]: Failed to update station {station_id} in Redis: {e}")

    def handle_reading(self, station_id: str, data: Dict[str, Any], timestamp: str):
        # Prepare reading data
        reading_value = data.get('data', '')
        measurement = data.get('measurement', '')
        sensor = data.get('sensor', 'unknown')
        edge_id = data.get('to_edge_id', data.get('edge_id', 'pi'))

        # Format measurement for Postgres
        sensor_prefix = sensor[:5].lower()
        formatted_measurement = f"{measurement}({sensor_prefix})"

        # Set latitude/longitude for ReadingCreate
        latitude,longitude = self.get_redis_coordinates(station_id)
        latitude = reading_value if measurement == 'latitude' else latitude
        longitude = reading_value if measurement == 'longitude' else longitude

        # Prepare reading payload using incoming data
        reading_payload = {
            "station_id": station_id,
            "edge_id": edge_id,
            "measurement": measurement,
            "reading_value": reading_value,
            "sensor_model": sensor,
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": timestamp
        }

        # Update Postgres readings
        try:
            response = requests.post(READING_ENDPOINT, json=reading_payload)
            if response.status_code == 200:
                print(f"[info]: Created reading for station {station_id}, measurement {formatted_measurement} in Postgres")
            else:
                print(f"[error]: Failed to create reading for {station_id} in Postgres: {response.text}")
        except requests.RequestException as e:
            print(f"[error]: Failed to communicate with Postgres for reading {station_id}: {e}")

        # Update Redis measurement
        try:
            redis_key = f"station:{station_id}"
            # Format Redis key
            if  measurement in ['latitude', 'longitude']:
                redis_measurement_key = measurement
            else:
                redis_measurement_key = f"{measurement}_{sensor_prefix}"

            redis_station_data = {
                redis_measurement_key: str(reading_value),
                'edge_id': edge_id,
                'last_active': timestamp
            }
            self.redis_client.hset(redis_key, mapping=redis_station_data)
            self.redis_client.expire(redis_key, self.active_station_timeout)
            print(f"[info]: Updated measurement {redis_measurement_key} for station {station_id} in Redis")

            # Update station coordinates in both databases for GPS readings
            if measurement in ['latitude', 'longitude']:
                self.update_station_coordinates(
                    station_id,
                    latitude=reading_value if measurement == 'latitude' else None,
                    longitude=reading_value if measurement == 'longitude' else None
                )

        except redis.RedisError as e:
            print(f"[error]: Failed to update measurement {redis_measurement_key} for {station_id} in Redis: {e}")

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
        ACTIVE_STATION_TIMEOUT
    )
    updater.start()

if __name__ == "__main__":
    main()