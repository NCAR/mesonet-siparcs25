import os
import paho.mqtt.client as mqtt
from flask import Flask, render_template
from flask_socketio import SocketIO
import time
import yaml
from collections import defaultdict
from datetime import datetime, timezone
import json
from threading import Lock
import logging
from flask import request

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load configuration
def load_config():
    config_file = os.getenv("CONFIG_FILE_PATH", "config.yml")
    if not os.path.isfile(config_file):
        logger.error(f"Config file '{config_file}' not found.")
        raise RuntimeError(f"Config file '{config_file}' not found.")
    
    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        logger.debug(f"Config loaded: {config}")
        return config
    except Exception as e:
        logger.error(f"Error reading config: {e}")
        raise RuntimeError(f"Error reading config: {e}")

config = load_config()
if not config or 'mqtt' not in config or 'web' not in config:
    logger.error("Invalid configuration or missing required sections (mqtt, web)")
    raise RuntimeError("Invalid configuration")

# Global variables
stations = defaultdict(dict)
stations_lock = Lock()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
allowed_origins = [
    "*",
    "http://localhost:5000",
    "http://10.219.130.204:5000"
] + os.getenv("ALLOWED_ORIGINS", "").split(",")
allowed_origins = [origin for origin in allowed_origins if origin]
logger.info(f"Allowed CORS origins: {allowed_origins}")
socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='eventlet', logger=True, engineio_logger=True)

# Initialize MQTT client
class MQTTClient:
    def __init__(self):
        self.client = mqtt.Client(protocol=mqtt.MQTTv311, clean_session=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.connected = False
        
    def connect(self):
        try:
            logger.debug(f"Connecting to MQTT broker {config['mqtt']['broker_ip']}:{config['mqtt']['broker_port']}")
            self.client.connect(
                config['mqtt']['broker_ip'],
                port=int(config['mqtt']['broker_port']),
                keepalive=60
            )
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            self.connected = False
            return False
    
    def reconnect(self):
        if not self.connected:
            logger.warning("Attempting MQTT reconnection...")
            return self.connect()
        return True
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"Connected to MQTT broker at {config['mqtt']['broker_ip']}:{config['mqtt']['broker_port']}")
            self.connected = True
            client.subscribe(config['mqtt']['msg_topic'], qos=1)
            logger.info(f"Subscribed to topic: {config['mqtt']['msg_topic']}")
        else:
            logger.error(f"Connection failed with code {rc}")
            self.connected = False
    
    def on_disconnect(self, client, userdata, rc):
        logger.warning(f"Disconnected from MQTT broker with code {rc}")
        self.connected = False
    
    def on_message(self, client, userdata, msg):
        try:
            logger.debug(f"Raw MQTT message received on topic {msg.topic}")
            try:
                payload = msg.payload.decode('utf-8')
            except UnicodeDecodeError as e:
                logger.error(f"Failed to decode MQTT payload: {e}")
                return
            
            try:
                packet_data = json.loads(payload)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in MQTT payload: {e}")
                return
                
            logger.info(
                f"Received MQTT message on topic '{msg.topic}' at {datetime.now(timezone.utc).isoformat()}:\n"
                f"Payload: {json.dumps(packet_data, indent=2)}"
            )
            
            station_id = packet_data.get('station_id')
            if not isinstance(station_id, str) or not station_id:
                logger.warning(f"Invalid or missing station_id in packet")
                return

            edge_id = packet_data.get('edge_id')
            timestamp = packet_data.get('timestamp')
            if not timestamp:
                logger.warning(f"Missing timestamp in packet, using current time")
                timestamp = datetime.now(timezone.utc).isoformat()
                
            sensor = packet_data.get('sensor')
            measurement = packet_data.get('measurement')
            data = packet_data.get('data')
            rssi = packet_data.get('rssi')

            normalized_data = {}
            sensor_prefix = sensor[:5] if sensor else 'unkno'
            has_gps = False
            if isinstance(data, (int, float, str)):
                normalized_data[f"{measurement}({sensor_prefix})"] = data
            elif isinstance(data, dict) and len(data) == 3:
                try:
                    normalized_data['latitude'] = data['latitude']
                    normalized_data['longitude'] = data['longitude']
                    has_gps = True
                    logger.debug(f"GPS data received for station {station_id}: {normalized_data['latitude']}, {normalized_data['longitude']}")
                    if 'gps_fix' in packet_data:
                        normalized_data['gps_fix'] = bool(packet_data['gps_fix'])
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid latitude/longitude format in packet: {e}")
                    return
            elif isinstance(data, dict):
                for key, value in data.items():
                    normalized_data[f"{key}({sensor_prefix})"] = value
            else:
                logger.warning(f"Invalid data format in packet")
                return

            station_update = {
                'station_id': station_id,
                'edge_id': edge_id,
                'rssi': rssi,
                'last_update': time.time(),
                'timestamp': timestamp,

            }
            station_update.update(normalized_data)
            
            with stations_lock:
                old_station = dict(stations[station_id])
                stations[station_id].update(station_update)
                logger.debug(f"Updated station {station_id}: {stations[station_id]}")
                
                # Only emit update if station has GPS data
                if 'latitude' in stations[station_id] and 'longitude' in stations[station_id]:
                    socketio.emit('station_update', {
                        'station_id': station_id,
                        'data': dict(stations[station_id])
                    })
                    logger.debug(f"Emitted station_update for {station_id} with GPS")
                elif has_gps:
                    # Emit if this message contains GPS, even if previously no GPS
                    socketio.emit('station_update', {
                        'station_id': station_id,
                        'data': dict(stations[station_id])
                    })
                    logger.debug(f"Emitted station_update for {station_id} due to new GPS")
                else:
                    logger.debug(f"Skipped emitting station_update for {station_id}: no GPS data")
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")

mqtt_client = MQTTClient()

# Periodic cleanup and MQTT reconnection
last_cleanup = time.time()
def cleanup_stations():
    global last_cleanup
    current_time = time.time()
    if current_time - last_cleanup >= 1:
        mqtt_client.reconnect()
        timeout = config['mqtt'].get('assignment_timeout', 60)
        with stations_lock:
            to_remove = [k for k, v in stations.items() 
                        if current_time - v.get('last_update', 0) > timeout]
            for k in to_remove:
                del stations[k]
                socketio.emit('station_remove', {'station_id': k})
                logger.info(f"Removed stale station: {k}")
        last_cleanup = current_time

@app.before_request
def before_request():
    cleanup_stations()

@app.route('/')
def index():
    return render_template('map.html')

@app.route('/api/stations')
def get_stations():
    with stations_lock:
        # Only return stations with GPS data
        return {
            'stations': stations,
            'timestamp': time.time()
        }

@socketio.on('connect')
def handle_connect():
    logger.info('Client connected')
    with stations_lock:
        socketio.emit('initial_data', {
            'stations': stations
        }, to=request.sid)
    logger.debug(f"Sent initial_data to client {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected')

# Start MQTT client
logger.info("Starting MQTT client")
mqtt_client.connect()