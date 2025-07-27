import yaml
import time
import logging
import json
import threading
from flask import Flask, render_template, jsonify, send_from_directory
from flask_socketio import SocketIO
import redis
from redis.exceptions import RedisError
from gevent import monkey


monkey.patch_all()  # must come first to patch standard library for gevent compatibility
app = Flask(__name__)
app.config['SECRET_KEY'] = 'map_secret'
# socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins=["*"])
logging.basicConfig(level=logging.DEBUG)
socketio = SocketIO(app, async_mode='gevent', ping_timeout=30,       # seconds
                    ping_interval=20,logger=True, engineio_logger=True, cors_allowed_origins="*")


# Load config file
with open('/cloud/config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Redis connection
REDIS_CONFIG = config.get('redis', {'host': 'redis', 'port': 6379})
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

# Redis pub/sub listener
def redis_listener():
    pubsub = redis_client.pubsub()
    pubsub.subscribe('station_updates')  # Subscribe to a channel for station updates
    app.logger.info("Subscribed to Redis channel: station_updates")
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            try:
                # Fetch updated station data
                station_keys = sorted(redis_client.keys('station:*'))
                stations = {}
                if station_keys:
                    pipe = redis_client.pipeline()
                    for key in station_keys:
                        pipe.hgetall(key)
                    station_data_list = pipe.execute()
                    for key, station_data in zip(station_keys, station_data_list):
                        station_id = key.split(':', 1)[1]
                        stations[station_id] = station_data
                
                # Broadcast update to all connected clients
                socketio.emit('station_update', {'stations': stations}, namespace='/')
                app.logger.debug(f"Broadcasted update to clients: {len(stations)} stations")
            except RedisError as e:
                app.logger.error(f"Error processing Redis pub/sub message: {e}")
            except Exception as e:
                app.logger.error(f"Unexpected error in redis_listener: {e}")

@app.route('/')
def index():
    return send_from_directory('templates', 'map.html')

@app.route('/api/stations')
def get_stations():
    try:
        start = time.time()
        station_keys = sorted(redis_client.keys('station:*'))
        stations = {}
        if station_keys:
            pipe = redis_client.pipeline()
            for key in station_keys:
                pipe.hgetall(key)
            station_data_list = pipe.execute()
            for key, station_data in zip(station_keys, station_data_list):
                station_id = key.split(':', 1)[1]
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
        station_keys = sorted(redis_client.keys('station:*'))
        stations = {}
        if station_keys:
            pipe = redis_client.pipeline()
            for key in station_keys:
                pipe.hgetall(key)
            station_data_list = pipe.execute()
            for key, station_data in zip(station_keys, station_data_list):
                station_id = key.split(':', 1)[1]
                stations[station_id] = station_data
        socketio.emit('initial_data', {'stations': stations}, namespace='/')
        app.logger.info("Map client connected")
    except RedisError as e:
        app.logger.error(f"Failed to send initial data from Redis: {e}")
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")

if __name__ == '__main__':
    # Start Redis listener in a background thread
    listener_thread = threading.Thread(target=redis_listener, daemon=True)
    listener_thread.start()
    socketio.run(app, host='0.0.0.0', port=5001)