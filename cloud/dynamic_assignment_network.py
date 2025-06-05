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
    url = f"{config['thingsboard']['api_url']}/api/tenant/dashboards?page=0&pageSize=1&textSearch={dashboard_name}"
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
    """Creates a device in ThingsBoard if it doesn't already exist and returns its access token."""
    device_name = station_id
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
    
    response = make_request_with_token_refresh(
        create_device_url, 
        headers, 
        method='POST', 
        json_data=device_data
    )
    
    if response:
        new_device = response.json()
        device_id = new_device['id']['id']
        print(f"[info]: Successfully created device '{device_name}' with ID: {device_id}")
        
        # Generate and set access token for the device
        credentials_url = f"{config['thingsboard']['api_url']}/api/device/{device_id}/credentials"
        credentials_data = {
            "credentialsType": "ACCESS_TOKEN",
            "credentialsId": f"station_{station_id}_token"  # Or generate a random one
        }
        
        credentials_response = make_request_with_token_refresh(
            credentials_url,
            headers,
            method='POST',
            json_data=credentials_data
        )
        
        if credentials_response:
            print(f"[info]: Successfully set access token for device '{device_name}'")
            return device_id
    
    return None

def set_telemetry(station_id, telemetry_data, token):
    """Set telemetry for a device using the device's access token."""
    # Get the device's access token (different from the JWT token)
    headers = {'X-Authorization': f'Bearer {token}'}
    existing_device = get_device_by_name(station_id, token)
    
    if not existing_device:
        print(f"[error]: Device not found for Station_{station_id}. Telemetry not sent.")
        return False
    
    # Get the device's credentials to find its access token
    device_id = existing_device['id']['id']
    credentials_url = f"{config['thingsboard']['api_url']}/api/device/{device_id}/credentials"
    credentials_response = make_request_with_token_refresh(credentials_url, headers, method='GET')
    
    if not credentials_response:
        print(f"[error]: Failed to get credentials for device {station_id}")
        return False
    
    device_credentials = credentials_response.json()
    access_token = device_credentials.get('credentialsId')  # This is the device's access token
    
    if not access_token:
        print(f"[error]: No access token found for device {station_id}")
        return False
    
    # Now send telemetry using the device's access token
    telemetry_url = f"{config['thingsboard']['api_url']}/api/v1/{access_token}/telemetry"
    
    try:
        # Structure telemetry data properly
        payload = {
            "ts": int(time.time() * 1000),  # Current timestamp in milliseconds
            "values": telemetry_data
        }
        
        response = requests.post(
            telemetry_url,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(payload)
        )
        
        if response.status_code == 200:
            print(f"[info]: Successfully sent telemetry for Station_{station_id}")
            return True
        else:
            print(f"[error]: Failed to send telemetry for Station_{station_id}: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[error]: Exception while sending telemetry for Station_{station_id}: {str(e)}")
        return False
# Function to send station data to ThingsBoard (update telemetry)
def send_station_data_to_thingsboard(station_id):
    """Send the station's latitude, longitude, and measurements to ThingsBoard as telemetry."""
    station = stations.get(station_id)
    if not station:
        print(f"[warn]: Station {station_id} not found for telemetry.")
        return
    
    # Prepare telemetry data
    telemetry_data = {
        "latitude": station["latitude"],
        "longitude": station["longitude"],
        "gps_fixed": station["gps_fixed"]
    }
    
    # Add measurements as individual telemetry values
    for measurement_name, measurement_value in station["measurements"].items():
        telemetry_data[measurement_name] = measurement_value
    
    token = get_jwt_token()
    if not token:
        print(f"[error]: Unable to get a valid token to set telemetry for Station_{station_id}.")
        return

    # Send the telemetry - THIS WAS MISSING IN YOUR CODE
    success = set_telemetry(station_id, telemetry_data, token)
    if success:
        print(f"[info]: Telemetry successfully sent for station {station_id}")
    else:
        print(f"[error]: Failed to send telemetry for station {station_id}")

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
    Adds or updates a dynamic map widget to display devices with GPS coordinates.
    Returns the updated dashboard if successful, None otherwise.
    """
    headers = {
        "X-Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. Fetch existing dashboard
    try:
        response = requests.get(
            f"{config['thingsboard']['api_url']}/api/dashboard/{dashboard_id}", 
            headers=headers
        )
        response.raise_for_status()
        dashboard = response.json()
        dashboard_config = dashboard.setdefault("configuration", {})
    except Exception as e:
        print(f"[error] Failed to get dashboard: {str(e)}")
        return None

    # 2. Initialize required dashboard structures
    dashboard_config.setdefault("widgets", {})
    dashboard_config.setdefault("entityAliases", {})
    dashboard_config.setdefault("timewindow", {
        "displayValue": "",
        "selectedTab": 0,
        "realtime": {
            "realtimeType": 1,
            "interval": 10000,
            "timewindowMs": 300000
        }
    })

    # 3. Configure main layout if missing
    layouts = dashboard_config.setdefault("layouts", {
        "main": {
            "widgets": {},
            "gridLayout": {
                "columns": 24,
                "margin": 10,
                "outerMargin": True
            },
            "rows": 0
        }
    })

    # 4. Find or create device group alias
    alias_name = "GPS_Device_Group"
    device_type = config['thingsboard']['default_device_type']
    
    # Check for existing alias
    alias_id = next(
        (alias_id for alias_id, alias in dashboard_config["entityAliases"].items()
         if alias.get("alias") == alias_name and
         alias.get("filter", {}).get("deviceType") == device_type),
        None
    )

    # Create new alias if needed
    if not alias_id:
        alias_id = str(uuid.uuid4())
        dashboard_config["entityAliases"][alias_id] = {
            "id": alias_id,
            "alias": alias_name,
            "filter": {
                "type": "deviceType",
                "deviceType": device_type,
                "resolveMultiple": True
            }
        }

    # 5. Configure map widget
    widget_id = str(uuid.uuid4())
    widget_config = {
        "type": "latest",
        "sizeX": 12,
        "sizeY": 8,
        "row": 0,
        "col": 0,
        "config": {
            "title": "GPS Stations",
            "showTitle": True,
            "entityAliasId": alias_id,
            "latitudeKeyName": "latitude",
            "longitudeKeyName": "longitude",
            "showLabel": True,
            "labelKeyName": "name",
            "mapProvider": "OPENSTREETMAP",
            "defaultZoomLevel": 8,
            "pointColor": "#2196f3",
            "showPoints": True,
            "showTooltip": True,
            "tooltipPattern": "Station ${entityName}\nLat: ${latitude}\nLon: ${longitude}"
        },
        "bundleAlias": "maps",
        "widgetTypeAlias": "openStreetMap"
    }

    # 6. Update dashboard configuration
    dashboard_config["widgets"][widget_id] = widget_config
    layouts["main"]["widgets"][widget_id] = {
        "sizeX": widget_config["sizeX"],
        "sizeY": widget_config["sizeY"],
        "row": widget_config["row"],
        "col": widget_config["col"]
    }

    # 7. Save updated dashboard
    try:
        response = requests.post(
            f"{config['thingsboard']['api_url']}/api/dashboard",
            headers=headers,
            json=dashboard
        )
        response.raise_for_status()
        print("[success] Dashboard updated with map widget")
        return response.json()
    except Exception as e:
        print(f"[error] Failed to update dashboard: {str(e)}")
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
