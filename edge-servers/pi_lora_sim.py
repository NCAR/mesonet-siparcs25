"""
Simulator for pi_lora.py — tests the dual-format publishing logic locally.
Feeds RP2040-style LoRa packets through the SAME functions as pi_lora.py
(map_packet_fields, get_batch_timestamp, publish_legacy_format)
and publishes both formats to the local Docker broker.
"""
import json
import time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

BROKER = "localhost"
PORT = 1884                       # Docker mosquitto (host side)
LEGACY_TOPIC = "ncar/iotwx/co/boulder/rp2040_test"
MSG_TOPIC_TEMPLATE = "sensors/{station_id}"

# ==== COPIED VERBATIM FROM pi_lora.py ====

def map_packet_fields(packet_data):
    field_map = {
        'sid': 'station_id', 'de': 'device', 't': 'type', 'ty': 'device_type',
        'l': 'load', 'rssi': 'ping_rssi', 'rc': 'relay_count', 'to': 'target_id',
        'r': 'allow_relay', 's': 'sensor', 'm': 'measurement', 'd': 'reading_value',
        'ts': 'timestamp', 'fn': 'firstname', 'ln': 'lastname', 'e': 'email',
        'o': 'organization', 'lat': 'latitude', 'lon': 'longitude',
        'C02': 'co2_concentration', 'rh': 'relative_humidity', 'tmp': 'temperature',
        'pre': 'pressure', 'uvs': 'uv_light', 'als': 'ambient_light',
        'pm0': 'pm10_standard', 'pm1': 'pm25_standard', 'pm2': 'pm100_standard',
        'pm3': 'pm10_env', 'pm4': 'pm25_env', 'pm5': 'pm100_env',
        'pm6': 'partcount_03um', 'pm7': 'partcount_05um', 'pm8': 'partcount_10um',
        'pm9': 'partcount_25um', 'pm10': 'partcount_50um', 'pm11': 'partcount_100um',
        'ra': 'rainfall_accumulated(24h)', 're': 'rainfall_event',
        'rt': 'rainfall_total', 'ri': 'rain_intensity', 'gr': 'gas_resistance',
        'al': 'altitude', 'p': 'sensor_protocol', 'se': 'serial', 'i2': 'i2c'
    }
    type_map = {'A': 'ping', 'B': 'pong', 'E': 'station_info', 'F': 'sensor_data'}
    mapped_packet = {}
    for short_field, value in packet_data.items():
        full_field = field_map.get(short_field, short_field)
        full_value = field_map.get(value, value)
        if full_field == 'type':
            mapped_packet[full_field] = type_map.get(value, value)
        else:
            mapped_packet[full_field] = full_value
    return mapped_packet

LEGACY_BATCH_WINDOW = 5
_legacy_batch_timestamps = {}

def get_batch_timestamp(station_id, sensor):
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

def publish_legacy_format(client, lora_msg, legacy_topic):
    station_id = lora_msg.get('station_id')
    sensor = lora_msg.get('sensor', 'unknown')
    measurement = lora_msg.get('measurement', 'unknown')
    protocol = lora_msg.get('sensor_protocol', 'unknown')
    value = lora_msg.get('reading_value')
    ts = lora_msg.get('timestamp')
    try:
        epoch = int(datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp())
    except Exception:
        epoch = get_batch_timestamp(station_id, sensor)
    payload = (
        f"device: adafruit/rp2040/{station_id}\n"
        f"sensor: lora/{protocol}/{sensor}/{measurement}\n"
        f"m: {value}\n"
        f"t: {epoch}"
    )
    client.publish(legacy_topic, payload, qos=1)
    print(f"[sim->legacy] {legacy_topic}:\n{payload}\n")

# ==== SIMULATED RP2040 PACKETS (exact firmware format) ====
# One BME680 burst = 5 packets, like bme680_measure_transmit() sends
SIM_PACKETS = [
    # GPS first (as real station does)
    {"t":"F","sid":"DF643CF0136D5D26","s":"pa1010d","m":"lat","d":40.01,"p":"i2","to":"000000002d28d827"},
    {"t":"F","sid":"DF643CF0136D5D26","s":"pa1010d","m":"lon","d":-105.27,"p":"i2","to":"000000002d28d827"},
    # BME680 burst — should ALL get the same legacy timestamp
    {"t":"F","sid":"DF643CF0136D5D26","s":"bme680","m":"tmp","d":23.45,"p":"i2","to":"000000002d28d827"},
    {"t":"F","sid":"DF643CF0136D5D26","s":"bme680","m":"rh","d":34.2,"p":"i2","to":"000000002d28d827"},
    {"t":"F","sid":"DF643CF0136D5D26","s":"bme680","m":"pre","d":1013.2,"p":"i2","to":"000000002d28d827"},
    {"t":"F","sid":"DF643CF0136D5D26","s":"bme680","m":"gr","d":120.5,"p":"i2","to":"000000002d28d827"},
    {"t":"F","sid":"DF643CF0136D5D26","s":"bme680","m":"al","d":1655.0,"p":"i2","to":"000000002d28d827"},
]

def main():
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="pi_lora_sim")
    client.connect(BROKER, PORT, 60)
    client.loop_start()
    time.sleep(1)
    print(f"[sim]: Connected to {BROKER}:{PORT}, simulating RP2040 packets...\n")

    for packet_data in SIM_PACKETS:
        # ==== same processing as pi_lora.py main loop ====
        station_id = packet_data['sid']
        lora_msg = map_packet_fields(packet_data)
        lora_msg['rssi'] = -49  # simulated RSSI
        if 'timestamp' not in lora_msg or not lora_msg['timestamp']:
            if lora_msg.get('type') == 'sensor_data':
                epoch = get_batch_timestamp(station_id, lora_msg.get('sensor', 'unknown'))
                lora_msg['timestamp'] = datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
            else:
                lora_msg['timestamp'] = datetime.now(timezone.utc).isoformat()

        msg_topic = MSG_TOPIC_TEMPLATE.format(station_id=station_id)
        client.publish(msg_topic, json.dumps(lora_msg), qos=1)
        print(f"[sim->json] {msg_topic}: {json.dumps(lora_msg)}")

        if lora_msg.get('type') == 'sensor_data':
            publish_legacy_format(client, lora_msg, LEGACY_TOPIC)

        time.sleep(0.3)  # mimic LoRa packet spacing within a burst

    time.sleep(2)
    client.loop_stop()
    client.disconnect()
    print("[sim]: Done.")

if __name__ == "__main__":
    main()