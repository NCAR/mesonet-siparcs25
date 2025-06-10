import datetime
import time
import json
import logging
import paho.mqtt.client as mqtt
from threading import Lock
from datetime import datetime, timezone
class MQTTClient:
    def __init__(self, config, stations, pis, stations_lock, pending_stations, assignment_network, socketio):
        self.config = config
        self.stations = stations
        self.pis = pis
        self.stations_lock = stations_lock
        self.pending_stations = pending_stations
        self.assignment_network = assignment_network
        self.socketio = socketio
        self.logger = logging.getLogger(__name__)
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.connected = False


    def connect(self,config):
        try:
            self.logger.debug(f"Connecting to MQTT broker {config['mqtt']['broker_ip']}:{config['mqtt']['broker_port']}")
            self.client.connect(
                config['mqtt']['broker_ip'],
                port=int(config['mqtt']['broker_port']),
                keepalive=60
            )
            self.client.loop_start()
            return True
        except Exception as e:
            self.logger.error(f"MQTT connection failed: {e}")
            self.connected = False
            return False

    def reconnect(self):
        if not self.client.is_connected():
            self.logger.info("Reconnecting to MQTT broker")
            self.client.reconnect()

    def on_connect(self, client, userdata, flags, rc):
        self.logger.info(f"Connected to MQTT with code {rc}")
        client.subscribe(self.config['mqtt']['msg_topic'])
        self.connected = True
    
    def publish_assignment(self, edge_id, station_id, status):
        if not self.connected:
            self.logger.warning(f"Cannot publish assignment for {station_id} to {edge_id}: MQTT not connected")
            return
        topic_template = self.config.get('mqtt', {}).get('edge_topic_template', 'edge/{edge_id}/assignments')
        topic = topic_template.format(edge_id=edge_id)
        message = json.dumps({
            'station_id': station_id,
            'status': status,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        try:
            self.client.publish(topic, message, qos=1)
            self.logger.info(f"Published assignment to {topic}: {message}")
        except Exception as e:
            self.logger.error(f"Failed to publish assignment to {topic}: {e}")


    def on_message(self, client, userdata, msg):
        try:
            self.logger.debug(f"Raw MQTT message received on topic {msg.topic}")
            payload = msg.payload.decode('utf-8')
            packet_data = json.loads(payload)
            self.logger.info(
                f"Received MQTT message on topic '{msg.topic}' at {datetime.now(timezone.utc).isoformat()}:\n"
                f"Payload: {json.dumps(packet_data, indent=2)}"
            )

            station_id = packet_data.get('station_id')
            if not isinstance(station_id, str) or not station_id:
                self.logger.warning(f"Invalid or missing station_id in packet")
                return

            edge_id = packet_data.get('edge_id')
            if not edge_id :
                self.logger.warning(f"Missing edge_id in packet for station {station_id}")
                return

            rssi = packet_data.get('rssi')
            timestamp = packet_data.get('timestamp') or datetime.now(timezone.utc).isoformat()
            sensor = packet_data.get('sensor')
            measurement = packet_data.get('measurement')
            data = packet_data.get('data')

            normalized_data = {}
            sensor_prefix = sensor[:5] if sensor else 'unkno'
            has_gps = False
            if isinstance(data, (int, float, str)):
                normalized_data[f"{measurement}({sensor_prefix})"] = data
            elif isinstance(data, dict) and len(data) == 3 and 'latitude' in data and 'longitude' in data:
                try:
                    normalized_data['latitude'] = float(data['latitude'])
                    normalized_data['longitude'] = float(data['longitude'])
                    has_gps = True
                    self.logger.debug(f"GPS data received for station {station_id}: {normalized_data['latitude']}, {normalized_data['longitude']}")
                    if 'gps_fix' in packet_data:
                        normalized_data['gps_fix'] = bool(packet_data['gps_fix'])
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"Invalid latitude/longitude format in packet: {e}")
                    return
            elif isinstance(data, dict):
                for key, value in data.items():
                    normalized_data[f"{key}({sensor_prefix})"] = value
            else:
                self.logger.warning(f"Invalid data format in packet")
                return

            station_update = {
                'station_id': station_id,
                'edge_id': edge_id,
                'rssi': rssi,
                'last_update': time.time(),
                'timestamp': timestamp,
            }
            station_update.update(normalized_data)

            with self.stations_lock:
                if edge_id:
                    self.pis[edge_id] = {'last_update': time.time()}
                    if edge_id not in self.assignment_network.edges:
                        self.assignment_network.on_edge_join(edge_id)
                        self.logger.info(f"Added new edge server (PI): {edge_id}")

                is_new_station = station_id not in self.stations
                if is_new_station:
                    self.pending_stations[station_id] = time.time()
                    self.stations[station_id] = {'seen_by': {}}
                    self.logger.info(f"Added new station: {station_id}")

                if edge_id and rssi is not None:
                    self.stations[station_id]['seen_by'][edge_id] = rssi

                self.stations[station_id].update(station_update)
                self.logger.debug(f"Updated station {station_id}: {self.stations[station_id]}")

                if station_id in self.pending_stations:
                    creation_time = self.pending_stations[station_id]
                    if time.time() - creation_time >= 5:
                        if self.stations[station_id]['seen_by']:
                            self.assignment_network.on_station_join(station_id, self.stations[station_id]['seen_by'])
                            assignments = self.assignment_network.get_assignments()
                            self.stations[station_id]['assigned_edge'] = assignments.get(station_id)
                            self.logger.debug(f"Assigned edge {self.stations[station_id]['assigned_edge']} to station {station_id} after delay")
                        del self.pending_stations[station_id]
                else:
                    if self.stations[station_id]['seen_by']:
                        self.assignment_network.on_station_join(station_id, self.stations[station_id]['seen_by'])
                        assignments = self.assignment_network.get_assignments()
                        self.stations[station_id]['assigned_edge'] = assignments.get(station_id)
                        self.logger.debug(f"Updated assignment for station {station_id}: {self.stations[station_id]['assigned_edge']}")

                if 'latitude' in self.stations[station_id] and 'longitude' in self.stations[station_id]:
                    self.socketio.emit('station_update', {
                        'station_id': station_id,
                        'data': dict(self.stations[station_id])
                    })
                    self.logger.debug(f"Emitted station_update for {station_id} with GPS")
                elif has_gps:
                    self.socketio.emit('station_update', {
                        'station_id': station_id,
                        'data': dict(self.stations[station_id])
                    })
                    self.logger.debug(f"Emitted station_update for {station_id} due to new GPS")

        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
        
 