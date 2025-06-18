
import yamlimport time
import logging
from flask import Flask, render_template, jsonify,send_from_directory
from flask_socketio import SocketIO
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = 'map_secret'
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins=["*","http://10.219.130.204:5001", "http://localhost:5001"])
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

# Load config
with open('config.yml', 'r') as f:
    config = yaml.safe_load(f)

MAIN_SERVER_URL = f"http://{config['web']['host']}:{config['web']['port']}"



@app.route('/')
def index():
    return send_from_directory('templates', 'map.html')

@app.route('/api/stations')
def get_stations():
    try:
        start = time.time()  # Ensure time is imported
        response = requests.get(f'{MAIN_SERVER_URL}/api/stations')
        response.raise_for_status()
        delta_time = time.time() - start
        return jsonify(response.json())
    except Exception as e:
        app.logger.error(f"Error fetching stations: {e}")
        return jsonify({'stations': {}}), 500

@app.route('/api/config')
def get_config():
    return jsonify({'map_web': config.get('map_web', {})})

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')

@socketio.on('connect')
def handle_connect():
    try:
        response = requests.get(f'{MAIN_SERVER_URL}/api/stations')
        socketio.emit('initial_data', response.json())
        app.logger.info('Map client connected')
    except Exception as e:
        app.logger.error(f"Error sending initial data: {e}")

