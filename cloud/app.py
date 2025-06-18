from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from collections import defaultdict
from threading import Lock
import logging
import time
import os
import yaml
from network import DynamicAssignmentNetwork
from cloud.services.mqtt_listener.mqtt_client import MQTTClient

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load configuration
with open('config.yml', 'r') as f:
    config = yaml.safe_load(f)

# Global variables
stations = defaultdict(dict)
pis = {}
stations_lock = Lock()
pending_stations = {}
app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = os.urandom(24)
allowed_origins = [
    "*",
    "http://localhost:5000",
    f"http://{config['web']['host']}:{config['web']['port']}"
] + os.getenv("ALLOWED_ORIGINS", "").split(",")
allowed_origins = [origin for origin in allowed_origins if origin]
logger.info(f"Allowed CORS origins: {allowed_origins}")
socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='gevent', logger=True, engineio_logger=True)

# Initialize assignment network
assignment_network = DynamicAssignmentNetwork(
    mqtt_client=None,
    config=config,
    hysteresis=config.get('assignment', {}).get('hysteresis', 0.1),
    rssi_min=config.get('assignment', {}).get('rssi_min', -120),
    rssi_max=config.get('assignment', {}).get('rssi_max', -30)
)

# Initialize MQTT client
mqtt_client = MQTTClient(config, stations, pis, stations_lock, pending_stations, assignment_network, socketio)
assignment_network.mqtt_client = mqtt_client
logger.info("Starting MQTT client")
mqtt_client.connect(config)


# Periodic cleanup
last_cleanup = time.time()

def cleanup_stations():
    global last_cleanup
    current_time = time.time()
    if current_time - last_cleanup >= 1:
        mqtt_client.reconnect()
        timeout = config['mqtt'].get('assignment_timeout', 60)
        with stations_lock:
            stations_to_remove = [
                k for k, v in stations.items()
                if current_time - v.get('last_update', 0) > timeout
            ]
            for k in stations_to_remove:
                assignment_network.on_station_leave(k)
                del stations[k]
                pending_stations.pop(k, None)
                socketio.emit('station_remove', {'station_id': k})
                logger.info(f"Removed inactive station: {k}")

            pis_to_remove = [
                k for k, v in pis.items()
                if current_time - v.get('last_update', 0) > timeout
            ]
            for k in pis_to_remove:
                assignment_network.on_edge_leave(k)
                del pis[k]
                logger.info(f"Removed inactive PI (edge): {k}")
        last_cleanup = current_time

@app.before_request
def before_request():
    cleanup_stations()

@app.route('/')
def index():
    return 'Dynamic Assignment Network'

@app.route('/api/stations')
def get_stations():
    with stations_lock:
        return {
            'stations': stations,
            'timestamp': time.time()
        }
    
@app.route('/api/config')
def get_config():
    return jsonify({'web': config.get('web', {})})

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


    