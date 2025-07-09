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
from datetime import datetime, timezone
from threading import Lock
import psutil
import math

# Global constants
PONG_COUNT = 3  # Number of pong responses per ping
PONG_DELAY = 1.0  # Seconds between pong responses

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
        reset_pin = DigitalInOut(board.D4)  # Reset pin for display
        display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c, reset=reset_pin)
        display.fill(0)  # Clear display
        display.show()
        print("[info]: SSD1306 OLED display initialized")
        return display
    except Exception as e:
        print(f"[error]: Failed to initialize LED display: {e}")
        return None

def initialize_radio(freq=915.0, power=23):
    """Initialize the RFM9x LoRa radio with specified frequency and power."""
    try:
        CS = digitalio.DigitalInOut(board.CE1)  # Chip select pin
        RESET = digitalio.DigitalInOut(board.D25)  # Reset pin
        spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)  # SPI interface
        rfm9x = adafruit_rfm9x.RFM9x(spi, CS, RESET, freq)
        rfm9x.tx_power = power  # Transmit power (dBm)
        rfm9x.spreading_factor = 7  # SF7, matches Arduino's Bw125Cr45Sf128
        rfm9x.signal_bandwidth = 125000  # 125 kHz bandwidth
        rfm9x.coding_rate = 5  # 4/5 coding rate
        print(f"[info]: Radio initialized - Frequency: {freq} MHz, Spreading Factor: {rfm9x.spreading_factor}, "
              f"Bandwidth: {rfm9x.signal_bandwidth} Hz, Coding Rate: {rfm9x.coding_rate}/8, Tx Power: {power} dBm")
        return rfm9x
    except Exception as e:
        print(f"[error]: Failed to initialize radio: {e}")
        return None

class MQTTClientWrapper:
    def __init__(self, config):
        """Initialize MQTT client with configuration parameters."""
        # MQTT configuration
        self.broker = config.get('mqtt', {}).get('broker_ip', 'localhost')  # MQTT broker IP
        self.port = config.get('mqtt', {}).get('broker_port', 1883)  # MQTT broker port
        self.edge_id = get_pi_serial() or config.get('radio', {}).get('edge_id', 'default_pi')  # Pi's unique ID
        self.msg_topic_template = config.get('mqtt', {}).get('msg_topic_template', 'iotwx/{station_id}')  # MQTT topic format
        # Radio load parameters
        self.overload_threshold = config.get('radio', {}).get('overload_threshold', 0.85)  # Max load before refusing pongs
        self.station_midpoint = config.get('radio', {}).get('pi_station_midpoint', 5)  # Midpoint for station load sigmoid
        self.station_steepness = config.get('radio', {}).get('pi_station_steepness', 1)  # Steepness for station load sigmoid
        self.cpu_weight = config.get('radio', {}).get('pi_cpu_weight', 0.4)  # Weight for CPU load
        self.mem_weight = config.get('radio', {}).get('pi_mem_weight', 0.3)  # Weight for memory load
        self.station_weight = config.get('radio', {}).get('pi_station_weight', 0.3)  # Weight for station count load
        self.keep_alive_interval = config.get('radio', {}).get('keep_alive_interval', 30000) / 1000  # Keep-alive interval (seconds)
        # State variables
        self.client = None
        self.connected = False
        self.last_connection_attempt = 0
        self.connection_interval = 30  # Seconds between connection attempts
        self.radio = None
        self.assigned_stations = set()  # Set of stations assigned to this Pi
        self.stations_lock = Lock()  # Thread-safe lock for assigned_stations
        self.load = 0.0  # Current Pi load
        self.last_load_update = 0  # Timestamp of last load update
        self.last_keep_alive = 0  # Timestamp of last keep-alive
        self.station_info_timestamps = {}  # Tracks station info receipt times
        self.gps_timestamps = {}  # Tracks GPS data receipt times
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
        """Calculate Pi's load based on CPU, memory, and assigned stations."""
        if time.time() - self.last_load_update >= 30:
            try:
                cpu = psutil.cpu_percent() / 100.0  # CPU usage (0.0 to 1.0)
                mem = psutil.virtual_memory().percent / 100.0  # Memory usage (0.0 to 1.0)
                with self.stations_lock:
                    station_count = len(self.assigned_stations)  # Number of assigned stations
                # Sigmoid function for station load
                station_load = 1.0 / (1.0 + math.exp(-self.station_steepness * (station_count - self.station_midpoint)))
                # Weighted sum of loads
                self.load = self.cpu_weight * cpu + self.mem_weight * mem + self.station_weight * station_load
                self.last_load_update = time.time()
                print(f"[info]: Pi load: {self.load:.2f} (CPU: {cpu:.2f}, Mem: {mem:.2f}, "
                      f"Stations: {station_count}, Station Load: {station_load:.2f})")
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

    def send_keep_alive(self):
        """Send keep-alive packets to assigned stations."""
        if time.time() - self.last_keep_alive >= self.keep_alive_interval:
            with self.stations_lock:
                stations = list(self.assigned_stations)
            for station_id in stations:
                # LoRa keep-alive packet (using shortened field names for Arduino compatibility)
                lora_keep_alive = {
                    'sid': self.edge_id,      # Station ID: Pi's unique ID (serial or config)
                    't': 'C',                 # Type: 'C' for keep_alive
                    'to': station_id          # Target ID: Station to receive keep-alive
                }
                if self.radio:
                    try:
                        self.radio.send(bytes(json.dumps(lora_keep_alive), 'utf-8'))
                        print(f"[info]: Sent keep-alive to {station_id}: {lora_keep_alive}")
                    except Exception as e:
                        print(f"[error]: Failed to send keep-alive to {station_id}: {e}")
                else:
                    print(f"[warn]: Radio not initialized, cannot send keep-alive to {station_id}")
            self.last_keep_alive = time.time()

def map_packet_fields(packet_data):
    """Map shortened Arduino packet fields to full names for MQTT publishing."""
    # Mapping of shortened field names to full names
    field_map = {
        'sid': 'station_id',        # 16-char hex ID
        't': 'type',                # Packet type (A, B, C, D, S, d)
        'ty': 'device_type',        # Device type (1=Pi, 2=station)
        'l': 'load',                # Station load (0.0 to 1.0)
        'rssi': 'ping_rssi',        # Received signal strength
        'rc': 'relay_count',        # Number of hops to Pi
        'to': 'target_id',          # Target station ID
        'r': 'allow_relay',         # Boolean, allows relaying
        's': 'sensor',              # Sensor name (e.g., bme680)
        'm': 'measurement',         # Measurement type (e.g., temperature)
        'd': 'reading_value',       # Measurement value
        'ts': 'timestamp',          # ISO 8601 timestamp (may be empty)
        'fn': 'firstname',          # First name for station_info
        'ln': 'lastname',           # Last name for station_info
        'e': 'email',               # Email for station_info
        'o': 'organization',        # Organization for station_info
        'lat': 'latitude',          # Latitude for station_info
        'lon': 'longitude',         # Longitude for station_info
        'C02': 'co2 Concentration', # C02 Concentration(ppm)
        'rh': 'relative humidity',  # Relative Humidity(%)
        'tmp': 'temperature',       # Temperature(C)
        'pre': 'pressure',          # Pressure(hPa)
        'gr': 'gas resistance',     # Gas Resistance(KOhms)
        'al': 'altitude',           # altitude(m)
        'uvs': 'uv light',          # UV Light
        'als': 'ambient light',     # Ambient Light
	 # PMSA003I measurements
        'pm0': 'pm10standard',
        'pm1': 'pm25standard',
        'pm2': 'pm100standard',
        'pm3': 'pm10env',
        'pm4': 'pm25env',
        'pm5': 'pm100env',
        'pm6': 'partcount03um',
        'pm7': 'partcount05um',
        'pm8': 'partcount10um',
        'pm9': 'partcount25um',
        'pm10': 'partcount50um',
        'pm11': 'partcount100um',
 }
    # Map type codes to full type names
    type_map = {
        'A': 'ping',
        'B': 'pong',
        'C': 'keep_alive',
        'D': 'disconnect',
        'E': 'station_info',
        'F': 'sensor_data'
    }
    # Create new dictionary with full field names
    mapped_packet = {}
    for short_field, value in packet_data.items():
        full_field = field_map.get(short_field, short_field)  # Fallback to original if not mapped
        value = field_map.get(value,value)
        if full_field == 'type':
            mapped_packet[full_field] = type_map.get(value, value)  # Map type code
        else:
            mapped_packet[full_field] = value
    return mapped_packet

def main():
    """Main function to initialize and run the LoRa-to-MQTT gateway."""
    # Initialize I2C for OLED display
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        print("[info]: I2C initialized")
    except Exception as e:
        print(f"[error]: Failed to initialize I2C: {e}")
        return

    # Load configuration
    try:
        with open("pi_config.json") as f:
            config = json.load(f)
        print("[info]: Loaded pi_config.json")
    except Exception as e:
        print(f"[error]: Failed to load pi_config.json: {e}")
        return

    # Get Pi's unique ID
    edge_id = get_pi_serial() or config.get('radio', {}).get('edge_id', 'default_pi')
    print(f"[info]: Using edge_id: {edge_id}")

    # Initialize MQTT client
    mqtt_client = MQTTClientWrapper(config)
    mqtt_client.loop()
    mqtt_client.connect()

    # Initialize OLED display
    display = initialize_led(i2c)
    if not display:
        print("[warn]: LED display initialization failed, continuing without display")

    # Initialize LoRa radio
    radio = initialize_radio()
    if not radio:
        print("[error]: Radio initialization failed, exiting")
        if display:
            display.fill(0)
            display.show()
        return

    # Assign radio to MQTT client
    mqtt_client.set_radio(radio)
    if display:
        display.fill(0)
        display.show()
        time.sleep(0.5)
        display.fill(0)
        display.show()

    print("[info]: Waiting for LoRa packets...")

    while True:
        # Reconnect to MQTT broker if needed
        if not mqtt_client.connected:
            mqtt_client.connect()

        # Send keep-alive packets to stations
        mqtt_client.send_keep_alive()

        # Receive LoRa packets
        packet = radio.receive(timeout=config.get('radio', {}).get('rcv_timeout', 0.5))
        if packet is not None:
            try:
                msg = packet.decode('utf-8')
                packet_data = json.loads(msg)
                print(f"[info]: Received LoRa packet: {msg}")

                # Validate station_id
                station_id = packet_data.get('sid')
                if not isinstance(station_id, str) or not station_id:
                    print(f"[warn]: Invalid or missing sid in packet: {msg}")
                    continue

                # Handle ping packets
                if packet_data.get('t') == 'A':
                    mqtt_client.update_load()
                    if mqtt_client.load > mqtt_client.overload_threshold:
                        print(f"[warn]: Load too high ({mqtt_client.load:.2f}), refusing pong response")
                        continue
                    # Prepare pong packet (using shortened fields)
                    pong = {
                        'sid': edge_id,       # Station ID: Pi's unique ID
                        't': 'B',             # Type: 'B' for pong
                        'ty': '1',            # Device type: '1' for Pi
                        'l': mqtt_client.load, # Load: Pi's current load
                        'rssi': radio.last_rssi if hasattr(radio, 'last_rssi') else 0, # RSSI of ping
                        'rc': 0,              # Relay count: 0 for direct Pi response
                        'to': station_id      # Target ID: Station that sent ping
                    }
                    # Send three pongs with delays
                    for i in range(PONG_COUNT):
                        try:
                            radio.send(bytes(json.dumps(pong), 'utf-8'))
                            print(f"[info]: Sent pong {i+1}/{PONG_COUNT} to {station_id}: {pong}")
                            if i < PONG_COUNT - 1:
                                start_time = time.time()
                                while time.time() - start_time < PONG_DELAY:
                                    # Process packets during pong delay
                                    sub_packet = radio.receive(timeout=0.1)
                                    if sub_packet is not None:
                                        try:
                                            sub_msg = sub_packet.decode('utf-8')
                                            sub_data = json.loads(sub_msg)
                                            sub_station_id = sub_data.get('sid')
                                            if not sub_station_id or not isinstance(sub_station_id, str):
                                                print(f"[warn]: Invalid sid in sub-packet: {sub_msg}")
                                                continue
                                            print(f"[info]: Received packet during pong delay from {sub_station_id}: {sub_msg}")
                                            if sub_data.get('t') in ['C', 'D']:
                                                print(f"[info]: Ignored {sub_data.get('t')} message from {sub_station_id}")
                                                continue
                                            to_edge_id = sub_data.get('to')
                                            if to_edge_id == edge_id:
                                                with mqtt_client.stations_lock:
                                                    if sub_station_id not in mqtt_client.assigned_stations:
                                                        mqtt_client.assigned_stations.add(sub_station_id)
                                                        print(f"[info]: Added station {sub_station_id} to assigned stations")
                                            elif to_edge_id and to_edge_id != edge_id:
                                                print(f"[info]: Dropping message for {sub_station_id} addressed to {to_edge_id}")
                                                continue
                                            # Map fields for MQTT
                                            lora_msg = map_packet_fields(sub_data)
                                            lora_msg['rssi'] = radio.last_rssi if hasattr(radio, 'last_rssi') else 0
                                            if 'timestamp' not in lora_msg or not lora_msg['timestamp']:
                                                lora_msg['timestamp'] = datetime.now(timezone.utc).isoformat()
                                            msg_topic = mqtt_client.msg_topic_template.format(station_id=sub_station_id)
                                            if mqtt_client.publish(msg_topic, json.dumps(lora_msg)):
                                                print(f"[info]: Forwarded message for {sub_station_id} to {msg_topic}: {lora_msg}")
                                            else:
                                                print(f"[error]: Failed to forward message for {sub_station_id} to {msg_topic}")
                                        except Exception as e:
                                            print(f"[error]: Error processing packet during pong delay: {e}")
                        except Exception as e:
                            print(f"[error]: Failed to send pong {i+1}/{PONG_COUNT} to {station_id}: {e}")
                    continue

                # Ignore keep_alive and disconnect messages
                if packet_data.get('t') in ['C', 'D']:
                    type_name = 'keep_alive' if packet_data.get('t') == 'C' else 'disconnect'
                    print(f"[info]: Ignored {type_name} message from {station_id}")
                    continue

                # Update assigned stations if packet is addressed to this Pi
                to_edge_id = packet_data.get('to')
                if to_edge_id == edge_id:
                    with mqtt_client.stations_lock:
                        if station_id not in mqtt_client.assigned_stations:
                            mqtt_client.assigned_stations.add(station_id)
                            print(f"[info]: Added station {station_id} to assigned stations")
                elif to_edge_id and to_edge_id != edge_id:
                    print(f"[info]: Dropping message for {station_id} addressed to {to_edge_id} (not {edge_id})")
                    continue

                # Map fields to full names for MQTT
                lora_msg = map_packet_fields(packet_data)
                # Add RSSI and timestamp if needed
                lora_msg['rssi'] = radio.last_rssi if hasattr(radio, 'last_rssi') else 0
                if 'timestamp' not in lora_msg or not lora_msg['timestamp']:
                    lora_msg['timestamp'] = datetime.now(timezone.utc).isoformat()

                # Publish to MQTT
                msg_topic = mqtt_client.msg_topic_template.format(station_id=station_id)
                if mqtt_client.publish(msg_topic, json.dumps(lora_msg)):
                    print(f"[info]: Forwarded message for {station_id} to {msg_topic}: {lora_msg}")
                else:
                    print(f"[error]: Failed to forward message for {station_id} to {msg_topic}")
            except Exception as e:
                print(f"[error]: Error processing packet: {e}")

        time.sleep(0.1)

if __name__ == "__main__":
    main()