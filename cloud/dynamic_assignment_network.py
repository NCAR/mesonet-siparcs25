import json
import os
import requests
import paho.mqtt.client as mqtt
import time
import uuid  # For generating unique IDs
import yaml  # For loading the config file

# Load configuration settings from config.yml
def load_config():
    config_file = os.getenv("CONFIG_FILE_PATH", "config.yml")  # Use the env var for config file path
    
    # Check if config file exists
    if not os.path.isfile(config_file):
        print(f"[error]: Configuration file '{config_file}' not found. Please ensure the file is present.")
        config_file = '/Users/adadelek/Documents/Lora-Mesonet/cloud/config.yml'
    
    # Load the config from the file
    try:
        with open(config_file, "r") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"[error]: Error reading the YAML configuration file: {e}")
        return None

# Global variables
config = load_config()  # Load config from YAML file
HEADERS = {'Content-Type': 'application/json'}
stations = {}

# Global JWT token
jwt_token = None

# --- ThingsBoard API Interaction ---

def get_jwt_token():
    """Authenticates with ThingsBoard and returns a JWT token."""
    global jwt_token
    if jwt_token:
        return jwt_token  # Return cached token if available
    
    auth_url = f"{config['thingsboard']['api_url']}/api/auth/login"
    auth_data = {
        'username': config['thingsboard']['username'],
        'password': config['thingsboard']['password']
    }
    try:
        response = requests.post(auth_url, json=auth_data, headers=HEADERS)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        jwt_token = response.json()['token']
        print("[info]: Successfully authenticated and obtained JWT token.")
        return jwt_token
    except requests.exceptions.RequestException as e:
        print(f"[error]: Error authenticating with ThingsBoard: {e}")
        return None

def make_request_with_token_refresh(url, headers, method='GET', json_data=None, retries=1):
    """Make an HTTP request with token refresh capability.
    
    Args:
        url: The URL to request
        headers: Dictionary of headers to include
        method: HTTP method ('GET', 'POST', 'PUT', 'DELETE')
        json_data: Data to send in the request body (for POST/PUT)
        retries: Number of retry attempts if token is expired
        
    Returns:
        Response object or None if request failed
    """
    try:
        # Make the initial request
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, json=json_data)
        elif method.upper() == 'PUT':
            response = requests.put(url, headers=headers, json=json_data)
        elif method.upper() == 'DELETE':
            response = requests.delete(url, headers=headers)
        else:
            print(f"[error]: Unsupported HTTP method: {method}")
            return None

        # Check for expired token (401) and retry if possible
        if response.status_code == 401 and retries > 0:
            print("[info]: Token expired. Fetching a new one.")
            # Refresh the token if expired
            token = get_jwt_token()
            if token:
                headers['X-Authorization'] = f'Bearer {token}'
                # Retry the request with new token
                return make_request_with_token_refresh(url, headers, method, json_data, retries - 1)
            else:
                print("[error]: Failed to refresh token")
                return None

        response.raise_for_status()  # Raise error for other bad responses (4xx or 5xx)
        return response
        
    except requests.exceptions.RequestException as e:
        print(f"[error]: Error during {method} request to {url}: {e}")
        return None
def get_dashboard_by_name(dashboard_name, token):
    """Retrieves a dashboard by its name."""
    url = f"{config['thingsboard']['api_url']}/api/tenant/dashboards?page=0&pageSize=1&textSearch={dashboard_name}&sortProperty=name&sortOrder=asc"
    headers = {'X-Authorization': f'Bearer {token}'}
    response = make_request_with_token_refresh(url, headers, method='GET')
    if response:
        data = response.json()
        if data and data['data'] and data['data'][0]['name'] == dashboard_name:
            print(f"[info]: Dashboard '{dashboard_name}' found with ID: {data['data'][0]['id']['id']}")
            return data['data'][0]
        print(f"[info]: Dashboard '{dashboard_name}' not found.")
    return None

def create_dashboard_if_not_exists(token):
    """Create a dashboard in ThingsBoard if it doesn't already exist."""
    dashboard_name = config['thingsboard']['dashboard_name']
    existing_dashboard = get_dashboard_by_name(dashboard_name, token)

    if existing_dashboard:
        return existing_dashboard['id']['id']

    url = f"{config['thingsboard']['api_url']}/api/dashboard"
    headers = {
        'X-Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    dashboard_data = {
        "name": dashboard_name,
        "title": dashboard_name,
        "configuration": {
            "description": f"Dashboard for {dashboard_name}",
            "widgets": {},
            "states": {},
            "entityAliases": {},
            "timewindow": {
                "displayValue": "",
                "selectedTab": 0,
                "realtime": {
                    "realtimeType": 1,
                    "interval": 10000,  # Update every 10 seconds instead of 1 second
                    "timewindowMs": 300000  # 5-minute window to show recent data
                }
            }
        }
    }
    
    response = make_request_with_token_refresh(
        url, 
        headers, 
        method='POST', 
        json_data=dashboard_data,
        retries=2
    )
    
    if response:
        dashboard = response.json()
        print(f"[info]: Dashboard '{dashboard_name}' created with ID: {dashboard['id']['id']}")
        return dashboard['id']['id']
    return None

def get_device_by_name(device_name, token):
    """Retrieves a device by its name."""
    headers = {'X-Authorization': f'Bearer {token}'}
    url = f"{config['thingsboard']['api_url']}/api/tenant/devices?page=0&pageSize=1&textSearch={device_name}&sortProperty=name&sortOrder=asc"
    response = make_request_with_token_refresh(url, headers, method='GET')
    if response:
        data = response.json()
        if data and data['data'] and data['data'][0]['name'] == device_name:
            return data['data'][0]
    return None

def create_device_if_not_exists(station_id, device_type=None):
    """Creates a device in ThingsBoard if it doesn't already exist."""
    device_name = station_id  # Using station_id as device name in ThingsBoard
    token = get_jwt_token()
    if not token:
        print("[error]: No JWT token available to create device.")
        return None

    existing_device = get_device_by_name(device_name, token)

    if existing_device:
        return existing_device['id']['id']

    device_type_to_use = device_type if device_type else config['thingsboard']['default_device_type']
    device_data = {
        "name": device_name,
        "type": device_type_to_use,
        "label": f"Station {station_id}",
    }

    headers = {
        'X-Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    create_device_url = f"{config['thingsboard']['api_url']}/api/device"
    response = make_request_with_token_refresh(create_device_url, headers)
    if response:
        new_device = response.json()
        print(f"[info]: Successfully created device '{device_name}' with ID: {new_device['id']['id']}")
        return new_device['id']['id']
    return None

def set_telemetry(station_id, telemetry_data, token):
    """Set telemetry for a device."""
    headers = {'X-Authorization': f'Bearer {token}'}
    existing_device = get_device_by_name(station_id, token)

    if existing_device:
        device_id = existing_device['id']['id']    
        telemetry_url = f'{config["thingsboard"]["api_url"]}/api/plugins/telemetry/DEVICE/{device_id}/SHARED_SCOPE'
        response = requests.post(
            telemetry_url,
            headers=headers,
            json=telemetry_data
        )
        
        if response.status_code == 200:
            print(f"[info]: Successfully set telemetry for Station_{station_id}: {telemetry_data}")
        else:
            print(f"[error]: Failed to set telemetry for Station_{station_id}: {response.text}")
    else:
        print(f"[error]: Device not found for Station_{station_id}. Telemetry not sent.")

# Function to send station data to ThingsBoard (update telemetry)
def send_station_data_to_thingsboard(station_id):
    """Send the station's latitude, longitude, and measurements to ThingsBoard as telemetry."""
    station = stations.get(station_id)
    if station:
        telemetry_data = {
            "latitude": station["latitude"],
            "longitude": station["longitude"],
            "gps_fixed": station["gps_fixed"],
            "measurements": station["measurements"]
        }

        token = get_jwt_token()
        if token:
            set_telemetry(station_id, telemetry_data, token)
        else:
            print(f"[error]: Unable to get a valid token to set telemetry for Station_{station_id}.")
    else:
        print(f"[warn]: Station {station_id} not found for telemetry.")

# MQTT client setup
def on_connect(client, userdata, flags, rc):
    """Connect to MQTT broker and subscribe to the topic."""
    if rc == 0:
        print("[info]: Connected to MQTT broker")
        client.subscribe(config['mqtt']['msg_topic'])
    else:
        print(f"[error]: Failed to connect to MQTT broker, code: {rc}")

# MQTT on_message callback
def on_message(client, userdata, msg):
    """Handle incoming MQTT messages and update station data."""
    global stations
    try:
        payload = json.loads(msg.payload.decode())
        print(f"Received message: {payload}")
        
        station_id = payload.get('station_id')
        if not station_id:
            print("[error]: Missing station_id in payload")
            return
        
        device_tb_id = create_device_if_not_exists(station_id, config['thingsboard']['default_device_type'])
        if not device_tb_id:
            print(f"[error]: Could not ensure device '{station_id}' exists in ThingsBoard. Skipping telemetry.")
            return

        # Initialize station data if it's new
        if station_id not in stations:
            stations[station_id] = {"latitude": None, "longitude": None, "gps_fixed": None, "measurements": {}, "thingsboard_id": device_tb_id}
        stations[station_id]["thingsboard_id"] = device_tb_id

        # Handle GPS data
        if payload.get('measurement') == "gps" and isinstance(payload.get('data'), dict):
            gps_data = payload.get('data')
            if len(gps_data) == 3:
                latitude, longitude, gps_fix = gps_data.values()
                stations[station_id]["latitude"] = latitude
                stations[station_id]["longitude"] = longitude
                stations[station_id]["gps_fixed"] = gps_fix
                send_station_data_to_thingsboard(station_id)

        # Handle other measurements
        if payload.get('measurement') and payload.get('sensor'):
            measurement = payload.get('measurement')
            data = payload.get('data')
            stations[station_id]["measurements"][measurement] = data

    except Exception as e:
        print(f"Error processing message: {e}")

def start_mqtt_client():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    # Set your MQTT broker details here
    broker = config['mqtt']['broker_ip']
    port = int(config['mqtt']['broker_port'])
    client.connect(broker, port=port, keepalive=60)

    client.loop_start()
    print("[info]: MQTT Client started")
def add_dynamic_map_widget(dashboard_id, token):
    """
    Adds or updates a dynamic map widget to a ThingsBoard dashboard.
    This map will display all devices of a specific type (e.g., 'GPS_Station').
    """
    headers = {
        "X-Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. Get the current dashboard details to obtain its layout
    get_dashboard_url = f"{config['thingsboard']['api_url']}/api/dashboard/{dashboard_id}"
    try:
        response = requests.get(get_dashboard_url, headers=headers)
        response.raise_for_status()
        dashboard = response.json()
    except requests.exceptions.RequestException as e:
        print(f"[error]: Error getting dashboard details for ID {dashboard_id} during widget setup: {e}")
        return None  # Return None if dashboard fetch fails

    dashboard_configuration = dashboard.get("configuration")  # Get configuration, it might be None if not set
    if dashboard_configuration is None:
        print(f"[warn]: Dashboard {dashboard_id} has no 'configuration' block. Initializing an empty one.")
        dashboard_configuration = {}
        dashboard["configuration"] = dashboard_configuration  # Ensure it's added back to the dashboard object

    layouts = dashboard_configuration.get("layouts", {})
    if not layouts:
        print("[info]: No existing layouts found, initializing 'main' layout.")
        layouts = {
            "main": {
                "widgets": {},
                "gridLayout": {
                    "columns": 24,  # Default ThingsBoard grid columns
                    "margin": 10,
                    "outerMargin": True
                },
                "rows": 0  # Will be dynamically adjusted
            }
        }
        dashboard_configuration["layouts"] = layouts

    map_widget_id = str(uuid.uuid4())  # Generate a unique widget ID
    map_widget_name = "Dynamic GPS Stations Map"

    # 2. Find if a widget with the same name already exists
    existing_map_widget_id = None
    widgets_in_config = dashboard_configuration.get("widgets", {})
    for widget_uid, widget_conf in widgets_in_config.items():
        if widget_conf.get("name") == map_widget_name:
            existing_map_widget_id = widget_uid
            map_widget_id = existing_map_widget_id  # Use the existing widget ID
            print(f"[info]: Found existing map widget '{map_widget_name}' with ID: {existing_map_widget_id}. Updating it.")
            break

    # 3. Define the Entity Alias for the Group of Devices
    group_alias_id = str(uuid.uuid4())  # Unique ID for the alias
    group_alias_name = "All GPS Stations"  # Name visible in ThingsBoard UI

    entity_aliases = dashboard_configuration.get("entityAliases", {})
    for alias_uid, alias_conf in entity_aliases.items():
        if alias_conf.get("alias") == group_alias_name and \
           alias_conf.get("filter", {}).get("type") == "deviceType" and \
           alias_conf.get("filter", {}).get("deviceType") == config['thingsboard']['default_device_type']:
            group_alias_id = alias_uid
            print(f"[info]: Found existing entity alias '{group_alias_name}' with ID: {group_alias_id}. Reusing.")
            break
    else:
        print(f"[info]: Creating new entity alias '{group_alias_name}' with ID: {group_alias_id}.")

    entity_aliases[group_alias_id] = {
        "id": group_alias_id,
        "alias": group_alias_name,
        "type": "entityType",
        "filter": {
            "type": "entityType",
            "resolveMultiple": True,  # Crucial for dynamic groups
            "entityType": "DEVICE",
            "deviceType": config['thingsboard']['default_device_type']
        }
    }
    dashboard_configuration["entityAliases"] = entity_aliases

    # 4. Define the map widget configuration
    map_widget_config = {
        "name": map_widget_name,
        "sizeX": 8,  # Width
        "sizeY": 6,  # Height
        "row": 0,    # Position
        "col": 0,
        "config": {
            "title": "Active GPS Stations",
            "showTitle": True,
            "backgroundColor": "#fff",
            "color": "rgba(0, 0, 0, 0.87)",
            "padding": "8px",
            "autoscale": True,
            "showLegend": False,
            "mapProvider": "OPENSTREETMAP",
            "mapUrl": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            "mapZoom": 8,
            "defaultZoomLevel": 8,
            "mapCenterLatitude": 39.7392,  # Example: Denver, CO latitude
            "mapCenterLongitude": -104.9903,  # Example: Denver, CO longitude
            "showAttribution": True,
            "showPoints": True,
            "pointColor": "#2196f3",
            "pointShape": "marker",
            "pointIcon": "mdi-map-marker",
            "pointIconSize": 24,
            "showLabel": True,
            "labelColor": "rgba(0,0,0,.87)"
        },
        "type": "latest",  # For latest telemetry
        "bundleAlias": "maps",
        "widgetTypeAlias": "openStreetMap",
        "rpcAlias": False,
        "useDashboardTimewindow": True,
        "showTitle": True,
        "dropShadow": True,
        "borderRadius": "8px"
    }

    if "widgets" not in dashboard_configuration:
        dashboard_configuration["widgets"] = {}
    dashboard_configuration["widgets"][map_widget_id] = map_widget_config

    # 5. Update the dashboard layout to include the new widget (or update existing)
    # Ensure the 'main' layout exists or initialize it
    if "main" not in layouts:
        layouts["main"] = {
            "widgets": {},
            "gridLayout": {
                "columns": 24,  # Default ThingsBoard grid columns
                "margin": 10,
                "outerMargin": True
            },
            "rows": 0
        }

    # Ensure widgets dictionary within the specific layout exists
    if "widgets" not in layouts["main"]:
        layouts["main"]["widgets"] = {}

    layouts["main"]["widgets"][map_widget_id] = {
        "sizeX": map_widget_config["sizeX"],
        "sizeY": map_widget_config["sizeY"],
        "row": map_widget_config["row"],
        "col": map_widget_config["col"]
    }
    dashboard_configuration["layouts"] = layouts  # Assign updated layouts back

    # 6. Update the dashboard on ThingsBoard
    update_dashboard_url = f"{config['thingsboard']['api_url']}/api/dashboard"
    try:
        response = requests.post(update_dashboard_url, headers=headers, data=json.dumps(dashboard))
        response.raise_for_status()
        print(f"[info]: Map widget '{map_widget_config['name']}' {'updated' if existing_map_widget_id else 'added'} successfully to dashboard {dashboard_id}!")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[error]: Error updating dashboard {dashboard_id}: {e}")
        return None
    
# Main function to orchestrate everything
def main():
    print("[info]: Starting ThingsBoard MQTT Gateway...")
    token = get_jwt_token()
    if not token:
        print("[critical]: Initial authentication failed. Exiting.")
        return

    dashboard_id = create_dashboard_if_not_exists(token)
    if not dashboard_id:
        print("[critical]: Unable to create or retrieve dashboard. Exiting.")
        return

    widget_response = add_dynamic_map_widget(dashboard_id, token)
    if not widget_response:
        print("[critical]: Unable to add or update map widget. Continuing without map setup.")

    start_mqtt_client()

    print("[info]: Gateway is running. Waiting for MQTT messages...")
    try:
        while True:
            time.sleep(1)  # Keep the main thread alive
    except KeyboardInterrupt:
        print("[info]: KeyboardInterrupt detected. Shutting down...")
    finally:
        print("[info]: Shutting down MQTT client.")

if __name__ == "__main__":
    main()
