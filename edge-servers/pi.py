import board
import busio
import digitalio
from digitalio import DigitalInOut
import adafruit_rfm9x
import adafruit_ssd1306
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import json
import yaml
import time
from datetime import datetime

def get_pi_serial():
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    return line.split(':')[1].strip()
        return None
    except Exception as e:
        print(f"[warn]: Failed to read serial number: {e}")
        return None

def initialize_led(i2c):
    reset_pin = DigitalInOut(board.D4)
    display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c, reset=reset_pin)
    display.fill(0)
    display.show()
    return display

def initialize_radio(freq=915, power=23):
    CS = digitalio.DigitalInOut(board.CE1)
    RESET = digitalio.DigitalInOut(board.D25)
    spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
    rfm9x = adafruit_rfm9x.RFM9x(spi, CS, RESET, freq)
    rfm9x.tx_power = power
    print(f"[info]: Radio parameters - Frequency: {freq} MHz, Spreading Factor: {rfm9x.spreading_factor}, Bandwidth: {rfm9x.signal_bandwidth} Hz, Coding Rate: {rfm9x.coding_rate}/8")
    return rfm9x

class MQTTClientWrapper:
    def __init__(self, broker, port, edge_id):
        self.broker = broker
        self.port = port
        self.edge_id = edge_id
        self.client = None
        self.connected = False
        self.last_connection_attempt = 0
        self.connection_interval = 30  # seconds between reconnection attempts
        self.initialize_client()

    def initialize_client(self):
        self.client = mqtt.Client(CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            print(f"[info]: Connected to MQTT broker with code {reason_code}")
            self.connected = True
            client.subscribe(f"assignment/{self.edge_id}")
        else:
            print(f"[warn]: Connection failed, reason_code={reason_code}")
            self.connected = False

    def on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode())
            if message.topic.startswith("assignment"):
                radio.send(bytes(json.dumps(payload), "utf-8"))
                print(f"[info]: Sent assignment to {payload['station_id']}: {payload['assigned_edge']}")
        except Exception as e:
            print(f"[warn]: Failed to process MQTT message: {e}")

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        print(f"[warn]: Disconnected from MQTT broker, reason_code={reason_code}")
        self.connected = False

    def connect(self):
        current_time = time.time()
        if not self.connected and (current_time - self.last_connection_attempt > self.connection_interval):
            try:
                print(f"[info]: Attempting to connect to {self.broker}:{self.port}")
                self.client.connect(self.broker, self.port, 120)
                self.last_connection_attempt = current_time
            except Exception as e:
                print(f"[error]: Failed to connect to broker: {e}")
                self.last_connection_attempt = current_time

    def publish(self, topic, payload):
        if not self.connected:
            print("[warn]: Dropping message - not connected to MQTT broker")
            return False
        
        try:
            result = self.client.publish(topic, payload)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                print(f"[warn]: Publish failed with rc={result.rc}")
                return False
            return True
        except Exception as e:
            print(f"[error]: Publish failed: {e}")
            return False

    def loop(self):
        self.client.loop_start()

def main():
    i2c = busio.I2C(board.SCL, board.SDA)
    try:
        with open("config.yml") as f:
            config = yaml.safe_load(f)
            broker = config['mqtt']['broker_ip']
            port = config['mqtt']['broker_port']
            msg_topic = config['mqtt']['msg_topic']
            rcv_timeout = config['radio']['rcv_timeout']
            config_edge_id = config['radio']['edge_id']
    except Exception as e:
        print(f"[error]: Failed to load config.yml: {e}")
        return

    edge_id = get_pi_serial() or config_edge_id
    print(f"[info]: Using edge_id: {edge_id}")

    mqtt_client = MQTTClientWrapper(broker, port, edge_id)
    mqtt_client.loop()
    mqtt_client.connect()  # Initial connection attempt

    display = initialize_led(i2c)
    try:
        radio = initialize_radio()
        display.fill(0)
        display.show()
        time.sleep(0.5)
        display.fill(0)
        display.show()
    except RuntimeError as error:
        display.fill(0)
        display.show()
        print(f'[error]: RFM9x Error: {error}')
        return

    print("[info]: Waiting for LoRa packets...")
    
    while True:
        # Handle MQTT connection
        if not mqtt_client.connected:
            mqtt_client.connect()
        
        packet = radio.receive(timeout=rcv_timeout)
        if packet is not None:
            try:
                msg = packet.decode('utf-8')
                packet_data = json.loads(msg)
                station_id = packet_data.get('station_id')
                if not isinstance(station_id, str) or not station_id:
                    print(f"[warn]: Invalid or missing station_id in packet: {msg}")
                    continue

                to_edge_id = packet_data.get('to_edge_id')
                timestamp = packet_data.get('timestamp')
                sensor = packet_data.get('sensor')
                measurement = packet_data.get('measurement')
                data = packet_data.get('data')
                gps_fix = packet_data.get('gps_fix')

                if measurement:
                    print(f'{measurement}: {data}')

                if not to_edge_id or to_edge_id == edge_id:
                    normalized_data = {}
                    if isinstance(data, (int, float)):
                        normalized_data[measurement] = data
                    elif isinstance(data, list) and len(data) == 2:
                        normalized_data['latitude'] = data[0]
                        normalized_data['longitude'] = data[1]
                        if gps_fix is not None:
                            normalized_data['gps_fix'] = gps_fix
                    else:
                        print(f"[warn]: Invalid data format in packet: {msg}")
                        continue

                    lora_msg = {
                        'station_id': station_id,
                        'edge_id': edge_id,
                        'rssi': radio.last_rssi,
                        'timestamp': timestamp if timestamp else datetime.utcnow().isoformat(),
                        'sensor': sensor,
                        'measurement': measurement,
                        'data': normalized_data,
                        'to_edge_id': to_edge_id
                    }
                    
                    # Simply try to publish, will drop if not connected
                    mqtt_client.publish(msg_topic, json.dumps(lora_msg))
                    print(f"[info]: Forwarded message for {station_id} to cloud on {msg_topic}")
            except Exception as e:
                print(f"[warn]: Error processing packet: {e}")
        
        time.sleep(0.1)

if __name__ == "__main__":
    main()