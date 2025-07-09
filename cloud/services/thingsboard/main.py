import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import json
import time
from datetime import datetime, timezone
import requests
import os
import yaml
from typing import Dict, Any
import uuid

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
    'thingsboard': ['api_url', 'username', 'password', 'dashboard_name', 'default_device_type']
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
        self.password = username
        self.dashboard_name = dashboard_name
        self.default_device_type = default_device_type
        self.client = None
        self.jwt_token = None
        self.device_tokens = {}  # Cache for device access tokens: {station_id: {'device_id': str, 'access_token': str}}
        self.connected = False
        self.initialize_client()
        self.test_api_connection()
        self.initialize_dashboard()

    def initialize_client(self):
        """Initialize MQTT client."""
        self.client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"tb_gateway_{uuid.uuid4()}")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def test_api_connection(self):
        """Test connection to ThingsBoard API."""
        try:
            response = requests.get(f"{self.api_url}/api/health", timeout=5)
            if response.status_code == 200:
                print(f"[info]: Connected to ThingsBoard API at {self.api_url}")
            else:
                print(f"[warn]: ThingsBoard API health check failed: {response.status_code} {response.text}")
        except requests.RequestException as e:
            print(f"[error]: Failed to connect to ThingsBoard API: {e}")
            exit(1)

    def get_jwt_token(self):
        """Authenticates with ThingsBoard and returns a JWT token."""
        if self.jwt_token:
            return self.jwt_token
        auth_url = f"{self.api_url}/api/auth/login"
        auth_data = {'username': self.username, 'password': self.password}
        try:
            response = requests.post(auth_url, json=auth_data, headers=HEADERS, timeout=5)
            response.raise_for_status()
            self.jwt_token = response.json()['token']
            print("[info]: Successfully authenticated and obtained JWT token.")
            return self.jwt_token
        except requests.exceptions.RequestException as e:
            print(f"[error]: Error authenticating with ThingsBoard: {e}")
            return None

    def make_request_with_token_refresh(self, url: str, headers: dict, method: str = 'GET', json_data: dict = None, retries: int = 1):
        """Make HTTP request with token refresh on 401 errors."""
        try:
            headers = headers.copy()
            headers['X-Authorization'] = f'Bearer {self.get_jwt_token()}'
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=5)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=json_data, timeout=5)
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=headers, json=json_data, timeout=5)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=5)
            else:
                print(f"[error]: Unsupported HTTP method: {method}")
                return None

            if response.status_code == 401 and retries > 0:
                print("[info]: Token expired. Fetching a new one.")
                self.jwt_token = None
                token = self.get_jwt_token()
                if token:
                    headers['X-Authorization'] = f'Bearer {token}'
                    return self.make_request_with_token_refresh(url, headers, method, json_data, retries - 1)
                return None

            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"[error]: Error during {method} request to {url}: {e}")
            return None

    def get_dashboard_by_name(self, dashboard_name: str):
        """Retrieve dashboard by name."""
        url = f"{self.api_url}/api/tenant/dashboards?page=0&pageSize=1&textSearch={dashboard_name}&sortProperty=name&sortOrder=asc"
        response = self.make_request_with_token_refresh(url, HEADERS, method='GET')
        if response:
            data = response.json()
            if data and data['data'] and data['data'][0]['name'] == dashboard_name:
                print(f"[info]: Dashboard '{dashboard_name}' found with ID: {data['data'][0]['id']['id']}")
                return data['data'][0]
            print(f"[info]: Dashboard '{dashboard_name}' not found.")
        return None

    def create_dashboard_if_not_exists(self):
        """Create dashboard if it doesn't exist."""
        existing_dashboard = self.get_dashboard_by_name(self.dashboard_name)
        if existing_dashboard:
            return existing_dashboard['id']['id']

        url = f"{self.api_url}/api/dashboard"
        dashboard_data = {
            "name": self.dashboard_name,
            "title": self.dashboard_name,
            "configuration": {
                "description": f"Dashboard for {self.dashboard_name}"
            }
        }
        response = self.make_request_with_token_refresh(url, HEADERS, method='POST', json_data=dashboard_data, retries=2)
        if response:
            dashboard = response.json()
            print(f"[info]: Dashboard '{self.dashboard_name}' created with ID: {dashboard['id']['id']}")
            return dashboard['id']['id']
        return None

    def add_dynamic_map_widget(self, dashboard_id: str):
        """Add or update dynamic map widget to dashboard."""
        headers = HEADERS.copy()
        get_dashboard_url = f"{self.api_url}/api/dashboard/{dashboard_id}"
        try:
            response = self.make_request_with_token_refresh(get_dashboard_url, headers, method='GET')
            dashboard = response.json()
        except requests.exceptions.RequestException as e:
            print(f"[error]: Error getting dashboard details for ID {dashboard_id}: {e}")
            return None

        dashboard_configuration = dashboard.get("configuration", {})
        layouts = dashboard_configuration.get("layouts", {"main": {"widgets": {}, "gridLayout": {"columns": 24, "margin": 10, "outerMargin": True}, "rows": 0}})
        dashboard_configuration["layouts"] = layouts

        map_widget_id = str(uuid.uuid4())
        map_widget_name = "Dynamic GPS Stations Map"
        widgets_in_config = dashboard_configuration.get("widgets", {})
        for widget_uid, widget_conf in widgets_in_config.items():
            if widget_conf.get("name") == map_widget_name:
                map_widget_id = widget_uid
                print(f"[info]: Found existing map widget '{map_widget_name}' with ID: {map_widget_id}. Updating it.")
                break

        group_alias_id = str(uuid.uuid4())
        group_alias_name = "All GPS Stations"
        entity_aliases = dashboard_configuration.get("entityAliases", {})
        for alias_uid, alias_conf in entity_aliases.items():
            if alias_conf.get("alias") == group_alias_name and alias_conf.get("filter", {}).get("type") == "deviceType":
                group_alias_id = alias_uid
                print(f"[info]: Found existing entity alias '{group_alias_name}' with ID: {group_alias_id}. Reusing.")
                break

        entity_aliases[group_alias_id] = {
            "id": group_alias_id,
            "alias": group_alias_name,
            "type": "entityType",
            "filter": {
                "type": "entityType",
                "resolveMultiple": True,
                "entityType": "DEVICE",
                "deviceType": self.default_device_type
            }
        }
        dashboard_configuration["entityAliases"] = entity_aliases

        map_widget_config = {
            "name": map_widget_name,
            "sizeX": 8,
            "sizeY": 6,
            "row": 0,
            "col": 0,
            "config": {
                "title": "Active GPS Stations",
                "showTitle": True,
                "mapProvider": "OPENSTREETMAP",
                "mapZoom": 8,
                "mapCenterLatitude": 39.7392,
                "mapCenterLongitude": -104.9903,
                "showPoints": True,
                "pointColor": "#2196f3",
                "pointShape": "marker",
                "pointIcon": "mdi-map-marker",
                "pointIconSize": 24,
                "showLabel": True
            },
            "type": "latest",
            "bundleAlias": "maps",
            "widgetTypeAlias": "openStreetMap",
            "useDashboardTimewindow": True
        }
        dashboard_configuration["widgets"] = dashboard_configuration.get("widgets", {})
        dashboard_configuration["widgets"][map_widget_id] = map_widget_config

        layouts["main"]["widgets"][map_widget_id] = {
            "sizeX": map_widget_config["sizeX"],
            "sizeY": map_widget_config["sizeY"],
            "row": map_widget_config["row"],
            "col": map_widget_config["col"]
        }
        dashboard_configuration["layouts"] = layouts

        update_dashboard_url = f"{self.api_url}/api/dashboard"
        try:
            response = self.make_request_with_token_refresh(update_dashboard_url, headers, method='POST', json_data=dashboard)
            print(f"[info]: Map widget '{map_widget_config['name']}' added/updated successfully to dashboard {dashboard_id}!")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[error]: Error updating dashboard {dashboard_id}: {e}")
            return None

    def initialize_dashboard(self):
        """Initialize dashboard and add map widget."""
        dashboard_id = self.create_dashboard_if_not_exists()
        if not dashboard_id:
            print("[critical]: Unable to create or retrieve dashboard. Continuing without dashboard.")
            return
        self.add_dynamic_map_widget(dashboard_id)

    def get_device_by_name(self, device_name: str):
        """Retrieve device by name from ThingsBoard."""
        url = f"{self.api_url}/api/tenant/devices?page=0&pageSize=1&textSearch={device_name}&sortProperty=name&sortOrder=asc"
        response = self.make_request_with_token_refresh(url, HEADERS, method='GET')
        if response:
            data = response.json()
            if data and data['data'] and data['data'][0]['name'] == device_name:
                return data['data'][0]
        return None

    def get_device_access_token(self, device_id: str):
        """Retrieve the access token for a device."""
        url = f"{self.api_url}/api/device/{device_id}/credentials"
        response = self.make_request_with_token_refresh(url, HEADERS, method='GET')
        if response and response.status_code == 200:
            credentials = response.json()
            if credentials.get('credentialsType') == 'ACCESS_TOKEN':
                return credentials.get('credentialsId')
        print(f"[error]: Failed to retrieve access token for device ID {device_id}")
        return None

    def create_device_if_not_exists(self, station_id: str):
        """Create device if it doesn't exist and cache its access token."""
        device_name = station_id
        # Check cache first
        if station_id in self.device_tokens:
            return self.device_tokens[station_id]['device_id']

        existing_device = self.get_device_by_name(device_name)
        if existing_device:
            device_id = existing_device['id']['id']
            access_token = self.get_device_access_token(device_id)
            if access_token:
                self.device_tokens[station_id] = {'device_id': device_id, 'access_token': access_token}
                return device_id
            return None

        device_data = {
            "name": device_name,
            "type": self.default_device_type,
            "label": f"Station {station_id}",
        }
        url = f"{self.api_url}/api/device"
        response = self.make_request_with_token_refresh(url, HEADERS, method='POST', json_data=device_data)
        if response:
            new_device = response.json()
            device_id = new_device['id']['id']
            access_token = self.get_device_access_token(device_id)
            if access_token:
                self.device_tokens[station_id] = {'device_id': device_id, 'access_token': access_token}
                print(f"[info]: Successfully created device '{device_name}' with ID: {device_id}")
                return device_id
        return None

    def set_attributes(self, station_id: str, attributes: dict):
        """Send attributes to ThingsBoard SHARED_SCOPE."""
        headers = HEADERS.copy()
        if station_id not in self.device_tokens:
            device_id = self.create_device_if_not_exists(station_id)
            if not device_id:
                print(f"[error]: Device not found for Station_{station_id}. Attributes not sent.")
                return
        device_id = self.device_tokens[station_id]['device_id']
        attributes_url = f'{self.api_url}/api/plugins/telemetry/DEVICE/{device_id}/SHARED_SCOPE'
        response = self.make_request_with_token_refresh(attributes_url, headers, method='POST', json_data=attributes)
        if response and response.status_code == 200:
            print(f"[info]: Successfully set attributes for Station_{station_id}: {attributes}")
        else:
            print(f"[error]: Failed to set attributes for Station_{station_id}: {response.text if response else 'No response'}")

    def set_telemetry(self, station_id: str, telemetry_data: dict, timestamp_ms: int):
        """Send time-series telemetry to ThingsBoard."""
        if station_id not in self.device_tokens:
            device_id = self.create_device_if_not_exists(station_id)
            if not device_id:
                print(f"[error]: Device not found for Station_{station_id}. Telemetry not sent.")
                return
        access_token = self.device_tokens[station_id]['access_token']
        telemetry_url = f'{self.api_url}/api/v1/{access_token}/telemetry'
        payload = {
            "ts": timestamp_ms,
            "values": telemetry_data
        }
        try:
            response = requests.post(telemetry_url, json=payload, headers=HEADERS, timeout=5)
            if response.status_code == 200:
                print(f"[info]: Successfully sent telemetry for Station_{station_id}: {payload}")
            else:
                print(f"[error]: Failed to send telemetry for Station_{station_id}: {response.text}")
        except requests.RequestException as e:
            print(f"[error]: Error sending telemetry for Station_{station_id}: {e}")

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Handle MQTT connection."""
        if reason_code == 0:
            print(f"[info]: Connected to MQTT broker with code {reason_code}")
            self.connected = True
            self.client.subscribe(MQTT_TOPIC, qos=1)
            print(f"[info]: Subscribed to {MQTT_TOPIC}")
        else:
            print(f"[warn]: Connection failed: {reason_code}")

    def on_message(self, client, userdata, message):
        """Handle incoming MQTT messages."""
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
            data['timestamp'] = timestamp

            if data.get('type') == 'station_info':
                self.handle_station_info(station_id, data, timestamp)
            else:
                self.handle_reading(station_id, data, timestamp)

        except json.JSONDecodeError as e:
            print(f"[error]: Failed to decode MQTT payload: {e}")
        except Exception as e:
            print(f"[error]: Failed to process message: {e}")

    def handle_station_info(self, station_id: str, station_data: Dict[str, Any], timestamp: str):
        """Handle station_info messages."""
        # Prepare attributes (not time-series data)
        attributes = {
            "firstname": station_data.get('firstname', ''),
            "lastname": station_data.get('lastname', ''),
            "email": station_data.get('email', ''),
            "organization": station_data.get('organization', ''),
            "target_id": station_data.get('to_edge_id', ''),
            "timestamp": timestamp
        }
        self.set_attributes(station_id, attributes)

        # Prepare telemetry (latitude, longitude as time-series)
        telemetry_data = {
            "latitude": float(station_data.get('latitude', 0)),
            "longitude": float(station_data.get('longitude', 0))
        }
        timestamp_ms = get_current_timestamp_ms()
        self.set_telemetry(station_id, telemetry_data, timestamp_ms)
        print(f"[info]: Processed station_info for {station_id}")

    def handle_reading(self, station_id: str, data: Dict[str, Any], timestamp: str):
        """Handle sensor reading messages."""
        # Create or update device in ThingsBoard
        device_id = self.create_device_if_not_exists(station_id)
        if not device_id:
            print(f"[error]: Could not ensure device '{station_id}' existscas in ThingsBoard. Skipping.")
            return

        # Prepare telemetry data
        timestamp_ms = get_current_timestamp_ms()
        telemetry_data = {}
        measurement = data.get('measurement')
        sensor = data.get('sensor')

        if measurement in ['latitude', 'longitude']:
            telemetry_data[measurement] = float(data.get('data', 0))
        elif sensor and measurement:
            # Flatten sensor data: e.g., "bme680_temperature" instead of nested {bme680: {temperature: value}}
            telemetry_key = f"{sensor}_{measurement}"
            telemetry_data[telemetry_key] = float(data.get('data', 0))
        else:
            print(f"[warn]: Unrecognized message format for station {station_id}")
            return

        # Add metadata as attributes (not time-series)
        attributes = {
            "timestamp": timestamp,
            "target_id": data.get('to_edge_id', ''),
            "rssi": str(data.get('rssi', '')) if data.get('rssi') else ''
        }
        self.set_attributes(station_id, attributes)

        # Send telemetry
        self.set_telemetry(station_id, telemetry_data, timestamp_ms)

    def start_mqtt_client(self):
        """Start MQTT client."""
        try:
            print(f"[info]: Connecting to MQTT broker at {self.broker}:{self.port}")
            self.client.connect(self.broker, port=self.port, keepalive=60)
            self.client.loop_start()
            print("[info]: MQTT Client started")
        except Exception as e:
            print(f"[error]: Failed to connect to MQTT broker: {e}")
            exit(1)

    def start(self):
        """Start the gateway."""
        print("[info]: Starting ThingsBoard MQTT Gateway...")
        self.start_mqtt_client()
        print("[info]: Gateway is running. Waiting for MQTT messages...")
        try:
            while True:
                time.sleep(1)  # Keep the main thread alive
        except KeyboardInterrupt:
            print("[info]: KeyboardInterrupt detected. Shutting down...")
            self.client.loop_stop()
            self.client.disconnect()
            print("[info]: MQTT client stopped.")

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