import json
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1884

INPUT_TOPIC = "sensors/#"
LEGACY_TOPIC = "ncar/iotwx/co/boulder/rp2040_test"

batch_timestamps = {}
BATCH_WINDOW_SECONDS = 5


def get_batch_timestamp(station_id, sensor):
    now = time.time()
    key = (station_id, sensor)

    if key in batch_timestamps:
        epoch, last_seen = batch_timestamps[key]
        if now - last_seen <= BATCH_WINDOW_SECONDS:
            batch_timestamps[key] = (epoch, now)
            return epoch

    epoch = int(now)
    batch_timestamps[key] = (epoch, now)
    return epoch


def to_legacy_payload(msg):
    station_id = msg.get("station_id")
    sensor = msg.get("sensor", "unknown")
    measurement = msg.get("measurement", "unknown")
    protocol = msg.get("sensor_protocol", "unknown")
    value = msg.get("reading_value")

    if not station_id or value is None:
        return None

    timestamp = msg.get("timestamp")

    if timestamp:
        try:
            epoch = int(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp())
        except Exception:
            epoch = get_batch_timestamp(station_id, sensor)
    else:
        epoch = get_batch_timestamp(station_id, sensor)

    return (
        f"device: adafruit/rp2040/{station_id}\n"
        f"sensor: lora/{protocol}/{sensor}/{measurement}\n"
        f"m: {value}\n"
        f"t: {epoch}"
    )


def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"[bridge] Connected to MQTT broker with code {reason_code}")
    client.subscribe(INPUT_TOPIC)
    print(f"[bridge] Subscribed to {INPUT_TOPIC}")


def on_message(client, userdata, message):
    raw = message.payload.decode("utf-8")

    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return

    if msg.get("type") != "sensor_data":
        return

    legacy_payload = to_legacy_payload(msg)
    if legacy_payload is None:
        return

    client.publish(LEGACY_TOPIC, legacy_payload, qos=1)

    print(f"\n[bridge] JSON input on {message.topic}:")
    print(raw)
    print(f"[bridge] Legacy output on {LEGACY_TOPIC}:")
    print(legacy_payload)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="legacy_bridge")
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)
client.loop_forever()