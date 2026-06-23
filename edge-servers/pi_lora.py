import board
import busio
import digitalio
from digitalio import DigitalInOut
import adafruit_rfm9x
import adafruit_ssd1306
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import json
import time
import random
from datetime import datetime, timezone
from threading import Lock, Thread
import psutil
import math

def get_pi_serial():
    """Retrieve the Raspberry Pi's unique serial number from /proc/cpuinfo."""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    return line.split(':')[1].strip()
        print("[warn]: No serial number found in /proc/cpuinfo")
        return None
    except Exception as e:
        print(f"[warn]: Failed to read serial number: {e}")
        return None

def initialize_led(i2c):
    """Initialize the SSD1306 OLED display over I2C."""
    try:
        reset_pin = DigitalInOut(board.D4)
        display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c, reset=reset_pin)
        display.fill(0)
        display.show()
        print("[info]: SSD1306 OLED display initialized")
        return display
    except Exception as e:
        print(f"[error]: Failed to initialize LED display: {e}")
        return None

def initialize_radio(freq=915.0, power=23):
    """Initialize the RFM9x LoRa radio with specified frequency and power."""
    try:
        CS = digitalio.DigitalInOut(board.CE1)
        RESET = digitalio.DigitalInOut(board.D25)
        spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
        rfm9x = adafruit_rfm9x.RFM9x(spi, CS, RESET, freq)
        rfm9x.tx_power = power

        # rfm9x.spreading_factor = 7
        rfm9x.spreading_factor = 11 # avoid collision with Nathan's

        rfm9x.low_datarate_optimize = True
        
        rfm9x.signal_bandwidth = 125000
        rfm9x.coding_rate = 5
        print(f"[info]: Radio initialized - Frequency: {freq} MHz, Spreading Factor: {rfm9x.spreading_factor}, "
              f"Bandwidth: {rfm9x.signal_bandwidth} Hz, Coding Rate: {rfm9x.coding_rate}/8, Tx Power: {power} dBm")
        return rfm9x
    except Exception as e:
        print(f"[error]: Failed to initialize radio: {e}")
        return None

class MQTTClientWrapper:
    def __init__(self, config):
        """Initialize MQTT client with configuration parameters."""
        self.broker = config.get('mqtt', {}).get('broker_ip', 'localhost')
        self.port = config.get('mqtt', {}).get('broker_port', 1883)
        self.edge_id = get_pi_serial() or config.get('radio', {}).get('edge_id', 'default_pi')
        self.msg_topic_template = config.get('mqtt', {}).get('msg_topic_template', 'iotwx/{station_id}')
        self.pong_duration = config.get('radio', {}).get('pong_duration', 3.0)
        self.pong_initial_delay_max = config.get('radio', {}).get('pong_initial_delay_max', 0.5)
        self.overload_threshold = config.get('radio', {}).get('overload_threshold', 0.85)
        self.station_midpoint = config.get('radio', {}).get('pi_station_midpoint', 5)
        self.station_steepness = config.get('radio', {}).get('pi_station_steepness', 1)
        self.cpu_weight = config.get('radio', {}).get('pi_cpu_weight', 0.4)
        self.mem_weight = config.get('radio', {}).get('pi_mem_weight', 0.3)
        self.station_weight = config.get('radio', {}).get('pi_station_weight', 0.3)
        self.client = None
        self.connected = False
        self.last_connection_attempt = 0
        self.connection_interval = 30
        self.radio = None
        self.radio_lock = Lock()
        self.load = 0.0
        self.last_load_update = 0
        self.station_count = 0
        self.initialize_client()

    def initialize_client(self):
        """Set up the MQTT client with callbacks."""
        try:
            self.client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"pi_{self.edge_id}")
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            print("[info]: MQTT client initialized")
        except Exception as e:
            print(f"[error]: Failed to initialize MQTT client: {e}")

    def set_radio(self, radio):
        """Assign the LoRa radio object."""
        self.radio = radio
        print("[info]: Radio assigned to MQTT client")

    def update_load(self):
        """Calculate Pi's load based on CPU, memory, and number of unique stations."""
        if time.time() - self.last_load_update >= 30:
            try:
                cpu = psutil.cpu_percent() / 100.0
                mem = psutil.virtual_memory().percent / 100.0
                station_load = 1.0 / (1.0 + math.exp(-self.station_steepness * (self.station_count - self.station_midpoint)))
                self.load = self.cpu_weight * cpu + self.mem_weight * mem + self.station_weight * station_load
                self.last_load_update = time.time()
                print(f"[info]: Pi load: {self.load:.2f} (CPU: {cpu:.2f}, Mem: {mem:.2f}, "
                      f"Stations: {self.station_count}, Station Load: {station_load:.2f})")
            except Exception as e:
                print(f"[error]: Failed to update load: {e}")
                self.load = 0.0

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Handle MQTT connection events."""
        if reason_code == 0:
            print(f"[info]: Connected to MQTT broker at {self.broker}:{self.port}")
            self.connected = True
        else:
            print(f"[warn]: MQTT connection failed with code {reason_code}")
            self.connected = False

    def on_disconnect(self, client, userdata, *args, **kwargs):
        """Handle MQTT disconnection events."""
        print("[info]: Disconnected from MQTT broker")
        self.connected = False

    def connect(self):
        """Attempt to connect to the MQTT broker if not connected."""
        current_time = time.time()
        if not self.connected and (current_time - self.last_connection_attempt >= self.connection_interval):
            try:
                print(f"[info]: Attempting to connect to {self.broker}:{self.port}")
                self.client.connect(self.broker, self.port, 120)
                self.last_connection_attempt = current_time
            except Exception as e:
                print(f"[error]: Failed to connect to broker: {e}")
                self.last_connection_attempt = current_time

    def publish(self, topic, payload):
        """Publish a message to the MQTT broker."""
        if not self.connected:
            print(f"[warn]: Dropping message for topic {topic} - not connected to MQTT broker")
            return False
        try:
            result = self.client.publish(topic, payload, qos=1)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                print(f"[error]: Failed to publish to {topic}, error: rc={result.rc}")
                return False
            print(f"[info]: Published to {topic}: {payload}")
            return True
        except Exception as e:
            print(f"[error]: Publish failed to {topic}: {e}")
            return False

    def loop(self):
        """Start the MQTT client's background processing loop."""
        try:
            self.client.loop_start()
            print("[info]: MQTT client loop started")
        except Exception as e:
            print(f"[error]: Failed to start MQTT loop: {e}")

    def send_pongs(self, station_id, edge_id, load, rssi):
        """Send pongs to a station for configured duration in a separate thread if MQTT is connected."""
        if not self.connected:
            print(f"[info]: Not sending pongs to {station_id} - MQTT not connected")
            return
        
        initial_delay = random.uniform(0, self.pong_initial_delay_max)
        print(f"[info]: Delaying pong response to {station_id} by {initial_delay:.3f} seconds")
        time.sleep(initial_delay)
        
        pong = {
            'sid': edge_id,
            't': 'B',
            'ty': '1',
            'l': load,
            'rssi': rssi,
            'rc': 0,
            'tar': station_id  # ← was 'to', must match station firmware
        }
        start_time = time.time()
        pong_count = 0
        while time.time() - start_time < self.pong_duration:
            with self.radio_lock:
                if self.radio:
                    try:
                        self.radio.send(bytes(json.dumps(pong), 'utf-8'))
                        pong_count += 1
                        print(f"[info]: Sent pong {pong_count} to {station_id}: {pong}")
                    except Exception as e:
                        print(f"[error]: Failed to send pong {pong_count+1} to {station_id}: {e}")
            time.sleep(0.01)
        print(f"[info]: Sent {pong_count} pongs to {station_id} over {self.pong_duration} seconds")

def map_packet_fields(packet_data):
    """Map shortened Arduino packet fields to full names for MQTT publishing."""
    field_map = {
        'sid': 'station_id',
        'de': 'device',
        't': 'type',
        'ty': 'device_type',
        'l': 'load',
        'rssi': 'ping_rssi',
        'rc': 'relay_count',
        'to': 'target_id',
        'r': 'allow_relay',
        's': 'sensor',
        'm': 'measurement',
        'd': 'reading_value',
        'ts': 'timestamp',
        'fn': 'firstname',
        'ln': 'lastname',
        'e': 'email',
        'o': 'organization',
        'lat': 'latitude',
        'lon': 'longitude',
        'C02': 'co2_concentration',
        'rh': 'relative_humidity',
        'tmp': 'temperature',
        'pre': 'pressure',
        'uvs': 'uv_light',
        'als': 'ambient_light',
        'pm0': 'pm10_standard',
        'pm1': 'pm25_standard',
        'pm2': 'pm100_standard',
        'pm3': 'pm10_env',
        'pm4': 'pm25_env',
        'pm5': 'pm100_env',
        'pm6': 'partcount_03um',
        'pm7': 'partcount_05um',
        'pm8': 'partcount_10um',
        'pm9': 'partcount_25um',
        'pm10': 'partcount_50um',
        'pm11': 'partcount_100um',
        'ra': 'rainfall_accumulated(24h)',
        're': 'rainfall_event',
        'rt': 'rainfall_total',
        'ri': 'rain_intensity',
        'gr': 'gas_resistance',
        'al': 'altitude',
        'p': 'sensor_protocol',
        'se': 'serial',
        'i2': 'i2c'
    }
    type_map = {
        'A': 'ping',
        'B': 'pong',
        'E': 'station_info',
        'F': 'sensor_data'
    }
    mapped_packet = {}
    for short_field, value in packet_data.items():
        full_field = field_map.get(short_field, short_field)
        full_value = field_map.get(value, value)
        if full_field == 'type':
            mapped_packet[full_field] = type_map.get(value, value)
        else:
            mapped_packet[full_field] = full_value
    return mapped_packet

# --- Legacy format publishing ---
LEGACY_BATCH_WINDOW = 5  # seconds: packets from same sensor within window share one timestamp
_legacy_batch_timestamps = {}  # (station_id, sensor) -> (epoch, last_seen)

def get_batch_timestamp(station_id, sensor):
    """Return a shared epoch timestamp for packets arriving in the same reading burst."""
    now = time.time()
    key = (station_id, sensor)
    if key in _legacy_batch_timestamps:
        epoch, last_seen = _legacy_batch_timestamps[key]
        if now - last_seen <= LEGACY_BATCH_WINDOW:
            _legacy_batch_timestamps[key] = (epoch, now)
            return epoch
    epoch = int(now)
    _legacy_batch_timestamps[key] = (epoch, now)
    return epoch

def publish_legacy_format(mqtt_client, lora_msg, legacy_topic):
    """Publish a sensor reading in the legacy ESP32 flat text format."""
    station_id = lora_msg.get('station_id')
    sensor = lora_msg.get('sensor', 'unknown')
    measurement = lora_msg.get('measurement', 'unknown')
    protocol = lora_msg.get('sensor_protocol', 'unknown')
    value = lora_msg.get('reading_value')

    # Prefer GPS timestamp from the station if present, else batch-stamp at Pi
    ts = lora_msg.get('timestamp')
    try:
        epoch = int(datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp())
    except Exception:
        epoch = get_batch_timestamp(station_id, sensor)

    payload = (
        f"\ndevice: adafruit/rp2040/{station_id}\n"
        f"sensor: lora/{protocol}/{sensor}/{measurement}\n"
        f"m: {value}\n"
        f"t: {epoch}\n"
    )
    mqtt_client.publish(legacy_topic, payload)

def main():
    """Main function to initialize and run the LoRa-to-MQTT gateway."""
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        print("[info]: I2C initialized")
    except Exception as e:
        print(f"[error]: Failed to initialize I2C: {e}")
        return

    try:
        with open("pi_config.json") as f:
            config = json.load(f)
        print("[info]: Loaded pi_config.json")
    except Exception as e:
        print(f"[error]: Failed to load pi_config.json: {e}")
        return

    legacy_topic = config.get('mqtt', {}).get('legacy_topic', 'ncar/iotwx/co/boulder/rp2040_test')

    edge_id = get_pi_serial() or config.get('radio', {}).get('edge_id', 'default_pi')
    print(f"[info]: Using edge_id: {edge_id}")

    mqtt_client = MQTTClientWrapper(config)
    mqtt_client.loop()
    mqtt_client.connect()

    display = initialize_led(i2c)
    if not display:
        print("[warn]: LED display initialization failed, continuing without display")

    radio = initialize_radio()
    if not radio:
        print("[error]: Radio initialization failed, exiting")
        if display:
            display.fill(0)
            display.show()
        return

    mqtt_client.set_radio(radio)
    if display:
        display.fill(0)
        display.show()
        time.sleep(0.5)
        display.fill(0)
        display.show()

    print("[info]: Waiting for LoRa packets...")

    recent_stations = set()
    last_debug_log = 0
    while True:
        if not mqtt_client.connected:
            mqtt_client.connect()

        current_time = time.time()
        if current_time - last_debug_log >= 10:
            print(f"[debug]: Main loop running, MQTT connected: {mqtt_client.connected}, Station count: {mqtt_client.station_count}")
            last_debug_log = current_time

        packet = radio.receive(timeout=config.get('radio', {}).get('rcv_timeout', 0.5))
        if packet is not None:
            try:
                msg = packet.decode('utf-8')
                packet_data = json.loads(msg)

                if packet_data.get('sys') == 'demo':
                    continue

                print(f"[info]: Received LoRa packet: {msg}")

                station_id = packet_data.get('sid')
                if not isinstance(station_id, str) or not station_id:
                    print(f"[warn]: Invalid or missing sid in packet: {msg}")
                    continue

                if packet_data.get('t') == 'A':
                    mqtt_client.update_load()
                    if mqtt_client.load > mqtt_client.overload_threshold:
                        print(f"[warn]: Load too high ({mqtt_client.load:.2f}), refusing pong response")
                        continue
                    if mqtt_client.connected:
                        pong_thread = Thread(
                            target=mqtt_client.send_pongs,
                            args=(station_id, edge_id, mqtt_client.load, radio.last_rssi if hasattr(radio, 'last_rssi') else 0),
                            daemon=True
                        )
                        pong_thread.start()
                    else:
                        print(f"[info]: Not sending pongs to {station_id} - MQTT not connected")
                    continue

                if packet_data.get('t') in ['B', 'C', 'D']:
                    print(f"[info]: Ignored {packet_data.get('t')} packet from {station_id}")
                    continue

                to_edge_id = packet_data.get('to')
                if to_edge_id and to_edge_id != edge_id and station_id in recent_stations and to_edge_id not in recent_stations:
                    print(f"[info]: Packet from {station_id} addressed to {to_edge_id}, removing from recent stations")
                    recent_stations.discard(station_id)
                    mqtt_client.station_count = len(recent_stations)
                    continue
                if to_edge_id and to_edge_id != edge_id:
                    print(f"[info]: Ignored packet from {station_id} addressed to {to_edge_id}")
                    continue

                recent_stations.add(station_id)
                mqtt_client.station_count = len(recent_stations)

                lora_msg = map_packet_fields(packet_data)
                lora_msg['rssi'] = radio.last_rssi if hasattr(radio, 'last_rssi') else 0
                if 'timestamp' not in lora_msg or not lora_msg['timestamp']:
                    if lora_msg.get('type') == 'sensor_data':
                        epoch = get_batch_timestamp(station_id, lora_msg.get('sensor', 'unknown'))
                        lora_msg['timestamp'] = datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
                    else:
                        lora_msg['timestamp'] = datetime.now(timezone.utc).isoformat()

                # msg_topic = mqtt_client.msg_topic_template.format(station_id=station_id)
                # if mqtt_client.publish(msg_topic, json.dumps(lora_msg)):
                #     print(f"[info]: Forwarded message for {station_id} to {msg_topic}: {lora_msg}")
                # else:
                #     print(f"[error]: Failed to forward message for {station_id} to {msg_topic}")

                if lora_msg.get('type') == 'sensor_data':
                    publish_legacy_format(mqtt_client, lora_msg, legacy_topic)
                
            except Exception as e:
                print(f"[error]: Error processing packet: {e}")
        
        

if __name__ == "__main__":
    main()