import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime, timezone
import requests
import os
import yaml
from typing import Dict, Any
import uuid
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s]: %(message)s')
logger = logging.getLogger(__name__)

# Configuration
CONFIG_FILE = "/cloud/config.yaml"

# Load and validate configuration
try:
    with open(CONFIG_FILE, 'r') as f:
        config = yaml.safe_load(f)
except Exception as e:
    logger.error(f"Failed to load {CONFIG_FILE}: {e}")
    exit(1)

# Validate required fields
required_fields = {
    'mqtt': ['host2', 'port', 'msg_topic'],
    'thingsboard': ['api_url', 'username', 'password', 'dashboard_name', 'default_device_type']
}
for section, fields in required_fields.items():
    if section not in config:
        logger.error(f"Missing section '{section}' in {CONFIG_FILE}")
        exit(1)
    for field in fields:
        if field not in config[section]:
            logger.error(f"Missing field '{field}' in section '{section}' of {CONFIG_FILE}")
            exit(1)

# Configuration parameters
MQTT_BROKER = config['mqtt']['host2']
MQTT_PORT = int(config['mqtt']['port'])
MQTT_TOPIC = config['mqtt']['msg_topic']
THINGSBOARD_API_URL = config['thingsboard']['api_url']
THINGSBOARD_USERNAME = config['thingsboard']['username']
THINGSBOARD_PASSWORD = config['thingsboard']['password']
DASHBOARD_NAME = config['thingsboard']['dashboard_name']
DEFAULT_DEVICE_TYPE = config['thingsboard']['default_device_type']
HEADERS = {'Content-Type': 'application/json'}

def get_current_timestamp():
    """Return current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()

def get_current_timestamp_ms():
    """Return current timestamp in milliseconds for ThingsBoard telemetry."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)

class ThingsBoardMQTTGateway:
    def __init__(self, broker: str, port: int, api_url: str, username: str, password: str, dashboard_name: str, default_device_type: str):
        self.broker = broker
        self.port = port
        self.api_url = api_url
        self.username = username
        self.password = password
        self.dashboard_name = dashboard_name
        self.default_device_type = default_device_type
        self.client = None
        self.jwt_token = None
        self.device_tokens = {}  # Cache for device access tokens: {station_id: {'device_id': str, 'access_token': str}}
        self.connected = False
        self.initialize_client()
        self.initialize_dashboard()

    def initialize_client(self):
        """Initialize MQTT client."""
        self.client = mqtt.Client(client_id=f"tb_gateway_{uuid.uuid4()}")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        logger.info("MQTT client initialized")

    def get_jwt_token(self, retries: int = 3, backoff: int = 5):
        """Authenticates with ThingsBoard and returns a JWT token with retries."""
        if self.jwt_token:
            return self.jwt_token
        auth_url = f"{self.api_url}/api/auth/login"
        auth_data = {'username': self.username, 'password': self.password}
        for attempt in range(retries):
            try:
                response = requests.post(auth_url, json=auth_data, headers=HEADERS, timeout=10)
                response.raise_for_status()
                self.jwt_token = response.json()['token']
                logger.info("Successfully authenticated and obtained JWT token")
                return self.jwt_token
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error authenticating with ThingsBoard (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(backoff)
            except requests.exceptions.RequestException as e:
                logger.error(f"Error authenticating with ThingsBoard: {e}")
                return None
        logger.error("Failed to authenticate with ThingsBoard after all retries")
        return None

    def make_request_with_token_refresh(self, url: str, headers: dict, method: str = 'GET', json_data: dict = None, retries: int = 3, backoff: int = 5):
        """Make HTTP request with token refresh and connection retries."""
        headers = headers.copy()
        for attempt in range(retries):
            try:
                headers['X-Authorization'] = f'Bearer {self.get_jwt_token()}'
                if not headers['X-Authorization']:
                    logger.error("No valid JWT token available")
                    return None
                if method.upper() == 'GET':
                    response = requests.get(url, headers=headers, timeout=10)
                elif method.upper() == 'POST':
                    response = requests.post(url, headers=headers, json=json_data, timeout=10)
                elif method.upper() == 'PUT':
                    response = requests.put(url, headers=headers, json=json_data, timeout=10)
                elif method.upper() == 'DELETE':
                    response = requests.delete(url, headers=headers, timeout=10)
                else:
                    logger.error(f"Unsupported HTTP method: {method}")
                    return None

                if response.status_code == 401 and retries > 0:
                    logger.info("Token expired. Fetching a new one.")
                    self.jwt_token = None
                    return self.make_request_with_token_refresh(url, headers, method, json_data, retries - 1)
                
                response.raise_for_status()
                return response
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error during {method} request to {url} (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(backoff)
            except requests.exceptions.RequestException as e:
                logger.error(f"Error during {method} request to {url}: {e}")
                return None
        logger.error(f"Failed to complete {method} request to {url} after all retries")
        return None

    def get_dashboard_by_name(self, dashboard_name: str):
        """Retrieve dashboard by name."""
        url = f"{self.api_url}/api/tenant/dashboards?pageSize=100&textSearch={dashboard_name}"
        logger.info(f"Attempting to retrieve dashboard '{dashboard_name}' from {url}")
        response = self.make_request_with_token_refresh(url, HEADERS, method='GET')
        if response:
            data = response.json()
            logger.debug(f"Dashboard search response: {json.dumps(data, indent=2)}")
            for dashboard in data.get('data', []):
                if dashboard.get('title') == dashboard_name:
                    logger.info(f"Dashboard '{dashboard_name}' found with ID: {dashboard['id']['id']}")
                    return dashboard
            logger.info(f"Dashboard '{dashboard_name}' not found.")
        else:
            logger.error(f"Failed to retrieve dashboards from {url}")
        return None

    def create_dashboard_if_not_exists(self):
        """Create dashboard if it doesn't exist."""
        existing_dashboard = self.get_dashboard_by_name(self.dashboard_name)
        if existing_dashboard:
            logger.info(f"Using existing dashboard '{self.dashboard_name}' with ID: {existing_dashboard['id']['id']}")
            return existing_dashboard['id']['id']

        url = f"{self.api_url}/api/dashboard"
        dashboard_data = {
            "title": self.dashboard_name,
            "name": self.dashboard_name,
            "configuration": {
                "description": f"Dashboard for {self.dashboard_name}",
            }
        }
        logger.info(f"Creating new dashboard '{self.dashboard_name}' at {url}")
        logger.debug(f"Dashboard creation payload: {json.dumps(dashboard_data, indent=2)}")
        response = self.make_request_with_token_refresh(url, HEADERS, method='POST', json_data=dashboard_data, retries=3)
        if response:
            dashboard = response.json()
            logger.info(f"Dashboard '{self.dashboard_name}' created with ID: {dashboard['id']['id']}")
            return dashboard['id']['id']
        logger.error(f"Failed to create dashboard '{self.dashboard_name}'")
        return None

    def add_dynamic_map_widget(self, dashboard_id: str):
        """Add or update dynamic map widget to dashboard."""
        headers = HEADERS.copy()
        get_dashboard_url = f"{self.api_url}/api/dashboard/{dashboard_id}"
        logger.info(f"Retrieving dashboard {dashboard_id} to add/update map widget")
        try:
            response = self.make_request_with_token_refresh(get_dashboard_url, headers, method='GET')
            if response:
                dashboard = response.json()
            else:
                logger.error(f"Failed to retrieve dashboard {dashboard_id}: No response")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting dashboard details for ID {dashboard_id}: {e}")
            return None

        dashboard['configuration'] = dashboard.get('configuration', {})
        widgets = dashboard['configuration'].get('widgets', {})
        states = dashboard['configuration'].get('states', {'default': {'layouts': {}, 'name': 'Default'}})
        layouts = states['default'].get('layouts', {})

        map_widget_id = str(uuid.uuid4())
        map_widget_name = "Dynamic GPS Stations Map"
        for widget_id, widget_conf in widgets.items():
            if widget_conf.get('title') == map_widget_name:
                map_widget_id = widget_id
                logger.info(f"Found existing map widget '{map_widget_name}' with ID: {map_widget_id}. Updating it.")
                break

        entity_alias_id = str(uuid.uuid4())
        map_widget_config = {
            "type": "timeseries",
            "isSystemType": False,
            "bundleAlias": "maps",
            "typeAlias": "openstreet_map",  # Use lowercase for compatibility
            "title": map_widget_name,
            "sizeX": 8,
            "sizeY": 6,
            "row": 0,
            "col": 0,
            "config": {
                "datasources": [{
                    "type": "entity",
                    "entityAliasId": entity_alias_id,
                    "dataKeys": [
                        {
                            "name": "latitude",
                            "type": "value",
                            "label": "Latitude",
                            "settings": {}
                        },
                        {
                            "name": "longitude",
                            "type": "value",
                            "label": "Longitude",
                            "settings": {}
                        }
                    ]
                }],
                "entityAliases": {
                    entity_alias_id: {
                        "id": entity_alias_id,
                        "alias": "All GPS Stations",
                        "filter": {
                            "type": "deviceType",
                            "deviceType": self.default_device_type,
                            "resolveMultiple": True
                        }
                    }
                },
                "showTitle": True,
                "mapProvider": "OPENSTREETMAP",
                "defaultZoom": 8,
                "centerPosition": {
                    "latitude": 39.7392,
                    "longitude": -104.9903
                },
                "timewindow": {
                    "interval": 60000,
                    "fixedWindow": False
                }
            }
        }
        widgets[map_widget_id] = map_widget_config
        layouts[map_widget_id] = {
            "sizeX": map_widget_config["sizeX"],
            "sizeY": map_widget_config["sizeY"],
            "row": map_widget_config["row"],
            "col": map_widget_config["col"]
        }
        dashboard['configuration']['widgets'] = widgets
        dashboard['configuration']['states'] = states

        update_dashboard_url = f"{self.api_url}/api/dashboard"
        logger.info(f"Updating dashboard {dashboard_id} with map widget")
        logger.debug(f"Dashboard update payload: {json.dumps(dashboard, indent=2)}")
        try:
            response = self.make_request_with_token_refresh(update_dashboard_url, headers, method='POST', json_data=dashboard)
            if response:
                logger.info(f"Map widget '{map_widget_config['title']}' added/updated successfully to dashboard {dashboard_id}")
                return response.json()
            else:
                logger.error(f"Failed to update dashboard {dashboard_id}: No response")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating dashboard {dashboard_id}: {e}")
            return None

    def initialize_dashboard(self):
        """Initialize dashboard and add map widget."""
        dashboard_id = self.create_dashboard_if_not_exists()
        if not dashboard_id:
            logger.error("Unable to create or retrieve dashboard. Continuing without dashboard.")
            return
        #self.add_dynamic_map_widget(dashboard_id)
        logger.info("Dashboard initialization completed")

    def get_device_by_name(self, device_name: str):
        """Retrieve device by name from ThingsBoard."""
        url = f"{self.api_url}/api/tenant/devices?pageSize=10&textSearch={device_name}"
        response = self.make_request_with_token_refresh(url, HEADERS, method='GET')
        if response:
            data = response.json()
            for device in data.get('data', []):
                if device['name'] == device_name:
                    logger.info(f"Device '{device_name}' found with ID: {device['id']['id']}")
                    return device
        logger.info(f"Device '{device_name}' not found.")
        return None

    def get_device_access_token(self, device_id: str):
        """Retrieve the access token for a device."""
        url = f"{self.api_url}/api/device/{device_id}/credentials"
        response = self.make_request_with_token_refresh(url, HEADERS, method='GET')
        if response and response.status_code == 200:
            credentials = response.json()
            if credentials.get('credentialsType') == 'ACCESS_TOKEN':
                return credentials.get('credentialsId')
        logger.error(f"Failed to retrieve access token for device ID {device_id}")
        return None

    def create_device_if_not_exists(self, station_id: str):
        """Create device if it doesn't exist and cache its access token."""
        device_name = station_id
        if station_id in self.device_tokens:
            logger.info(f"Using cached device ID for {station_id}")
            return self.device_tokens[station_id]['device_id']

        existing_device = self.get_device_by_name(device_name)
        if existing_device:
            device_id = existing_device['id']['id']
            access_token = self.get_device_access_token(device_id)
            if access_token:
                self.device_tokens[station_id] = {'device_id': device_id, 'access_token': access_token}
                logger.info(f"Device '{device_name}' found with ID: {device_id}")
                return device_id
            return None

        device_data = {
            "name": device_name,
            "type": self.default_device_type,
            "label": f"Station {station_id}"
        }
        url = f"{self.api_url}/api/device"
        response = self.make_request_with_token_refresh(url, HEADERS, method='POST', json_data=device_data)
        if response:
            new_device = response.json()
            device_id = new_device['id']['id']
            access_token = self.get_device_access_token(device_id)
            if access_token:
                self.device_tokens[station_id] = {'device_id': device_id, 'access_token': access_token}
                logger.info(f"Successfully created device '{device_name}' with ID: {device_id}")
                return device_id
        logger.error(f"Failed to create device '{device_name}'")
        return None

    def set_attributes(self, station_id: str, attributes: dict):
        """Send attributes to ThingsBoard SHARED_SCOPE."""
        headers = HEADERS.copy()
        if station_id not in self.device_tokens:
            device_id = self.create_device_if_not_exists(station_id)
            if not device_id:
                logger.error(f"Device not found for Station_{station_id}. Attributes not sent.")
                return
        device_id = self.device_tokens[station_id]['device_id']
        attributes_url = f'{self.api_url}/api/plugins/telemetry/DEVICE/{device_id}/SHARED_SCOPE'
        response = self.make_request_with_token_refresh(attributes_url, headers, method='POST', json_data=attributes)
        if response and response.status_code == 200:
            logger.info(f"Successfully set attributes for Station_{station_id}: {attributes}")
        else:
            logger.error(f"Failed to set attributes for Station_{station_id}: {response.text if response else 'No response'}")

    def set_telemetry(self, station_id: str, telemetry_data: dict, timestamp_ms: int):
        """Send time-series telemetry to ThingsBoard."""
        if station_id not in self.device_tokens:
            device_id = self.create_device_if_not_exists(station_id)
            if not device_id:
                logger.error(f"Device not found for Station_{station_id}. Telemetry not sent.")
                return
        access_token = self.device_tokens[station_id]['access_token']
        telemetry_url = f'{self.api_url}/api/v1/{access_token}/telemetry'
        payload = {
            "ts": timestamp_ms,
            "values": telemetry_data
        }
        try:
            response = requests.post(telemetry_url, json=payload, headers=HEADERS, timeout=10)
            if response.status_code == 200:
                logger.info(f"Successfully sent telemetry for Station_{station_id}: {payload}")
            else:
                logger.error(f"Failed to send telemetry for Station_{station_id}: {response.text}")
        except requests.RequestException as e:
            logger.error(f"Error sending telemetry for Station_{station_id}: {e}")

    def on_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection."""
        if rc == 0:
            logger.info(f"Connected to MQTT broker with code {rc}")
            self.connected = True
            self.client.subscribe(MQTT_TOPIC, qos=1)
            logger.info(f"Subscribed to {MQTT_TOPIC}")
        else:
            logger.warning(f"Connection failed: {rc}")

    def on_message(self, client, userdata, message):
        """Handle incoming MQTT messages."""
        try:
            payload = message.payload.decode('utf-8')
            data = json.loads(payload)
            logger.info(f"Received message on {message.topic}: {data}")

            station_id = data.get('station_id')
            if not station_id:
                logger.warning("Missing station_id in message")
                return

            if data.get('type') in ['keep_alive', 'disconnect']:
                logger.info(f"Ignored {data.get('type')} message from {station_id}")
                return

            timestamp = get_current_timestamp()
            data['timestamp'] = timestamp

            if data.get('type') == 'station_info':
                self.handle_station_info(station_id, data, timestamp)
            else:
                self.handle_reading(station_id, data, timestamp)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode MQTT payload: {e}")
        except Exception as e:
            logger.error(f"Failed to process message: {e}")

    def handle_station_info(self, station_id: str, station_data: Dict[str, Any], timestamp: str):
        """Handle station_info messages."""
        attributes = {
            "firstname": station_data.get('firstname', ''),
            "lastname": station_data.get('lastname', ''),
            "email": station_data.get('email', ''),
            "organization": station_data.get('organization', ''),
            "target_id": station_data.get('to_edge_id', ''),
            "timestamp": timestamp
        }
        self.set_attributes(station_id, attributes)

        telemetry_data = {
            "latitude": float(station_data.get('latitude', 0)),
            "longitude": float(station_data.get('longitude', 0))
        }
        timestamp_ms = get_current_timestamp_ms()
        self.set_telemetry(station_id, telemetry_data, timestamp_ms)
        logger.info(f"Processed station_info for {station_id}")

    def handle_reading(self, station_id: str, data: Dict[str, Any], timestamp: str):
        """Handle sensor reading messages."""
        device_id = self.create_device_if_not_exists(station_id)
        if not device_id:
            logger.error(f"Could not ensure device '{station_id}' exists in ThingsBoard. Skipping.")
            return

        timestamp_ms = get_current_timestamp_ms()
        telemetry_data = {}
        measurement = data.get('measurement')
        sensor = data.get('sensor')

        if measurement in ['latitude', 'longitude']:
            telemetry_data[measurement] = float(data.get('reading_value', 0))
        elif sensor and measurement:
            telemetry_key = f"{sensor}_{measurement}"
            telemetry_data[telemetry_key] = float(data.get('reading_value', 0))
        else:
            logger.warning(f"Unrecognized message format for station {station_id}")
            return

        attributes = {
            "timestamp": timestamp,
            "target_id": data.get('to_edge_id', ''),
            "rssi": str(data.get('rssi', '')) if data.get('rssi') else ''
        }
        self.set_attributes(station_id, attributes)
        self.set_telemetry(station_id, telemetry_data, timestamp_ms)

    def start_mqtt_client(self):
        """Start MQTT client."""
        try:
            logger.info(f"Connecting to MQTT broker at {self.broker}:{self.port}")
            self.client.connect(self.broker, port=self.port, keepalive=60)
            self.client.loop_start()
            logger.info("MQTT Client started")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            exit(1)

    def start(self):
        """Start the gateway."""
        logger.info("Starting ThingsBoard MQTT Gateway...")
        self.start_mqtt_client()
        logger.info("Gateway is running. Waiting for MQTT messages...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt detected. Shutting down...")
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT client stopped.")

def main():
    gateway = ThingsBoardMQTTGateway(
        MQTT_BROKER,
        MQTT_PORT,
        THINGSBOARD_API_URL,
        THINGSBOARD_USERNAME,
        THINGSBOARD_PASSWORD,
        DASHBOARD_NAME,
        DEFAULT_DEVICE_TYPE
    )
    gateway.start()

if __name__ == "__main__":
    main()