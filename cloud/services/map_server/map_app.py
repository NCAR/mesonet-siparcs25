import yaml
import time
import logging
import json
from flask import Flask, render_template, jsonify, send_from_directory
from flask_socketio import SocketIO
import redis
from redis.exceptions import RedisError

app = Flask(__name__)
app.config['SECRET_KEY'] = 'map_secret'
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins=["*", "http://localhost:5001"])
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

# Load config
with open('/cloud/config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Redis connection
REDIS_CONFIG = config.get('redis', {'host': 'localhost', 'port': 6379})
redis_client = redis.Redis(
    host=REDIS_CONFIG['host'],
    port=REDIS_CONFIG['port'],
    decode_responses=True
)

# Test Redis connection
try:
    redis_client.ping()
    app.logger.info("Connected to Redis")
except RedisError as e:
    app.logger.error(f"Failed to connect to Redis: {e}")
    raise RuntimeError("Redis connection failed")

@app.route('/')
def index():
    return send_from_directory('templates', 'map.html')

@app.route('/api/stations')
def get_stations():
    try:
        start = time.time()
        # Fetch all station keys
        station_keys = sorted(redis_client.keys('station:*'))
        stations = {}
        if station_keys:
            # Use pipeline for efficient retrieval
            pipe = redis_client.pipeline()
            for key in station_keys:
                pipe.hgetall(key)
            station_data_list = pipe.execute()
            for key, station_data in zip(station_keys, station_data_list):
                station_id = key.split(':', 1)[1]
                # Include all fields from the hash
                stations[station_id] = station_data
        delta_time = time.time() - start
        app.logger.debug(f"Fetched {len(stations)} stations from Redis in {delta_time:.3f}s")
        return jsonify({'stations': stations})
    except RedisError as e:
        app.logger.error(f"Error fetching stations from Redis: {e}")
        return jsonify({'stations': {}}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")
        return jsonify({'stations': {}}), 500

@app.route('/api/config')
def get_config():
    return jsonify({'map': config.get('map', {})})

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')

@socketio.on('connect')
def handle_connect():
    try:
        # Fetch all station keys
        station_keys = sorted(redis_client.keys('stations:*'))
        stations = {}
        if station_keys:
            # Use pipeline for efficient retrieval
            pipe = redis_client.pipeline()
            for key in station_keys:
                pipe.hgetall(key)
            station_data_list = pipe.execute()
            for key, station_data in zip(station_keys, station_data_list):
                station_id = key.split(':', 1)[1]
                # Include all fields from the hash
                stations[station_id] = station_data
        socketio.emit('initial_data', {'stations': stations})
        app.logger.info("Map client connected")
    except RedisError as e:
        app.logger.error(f"Failed to send initial data from Redis: {e}")
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5001)