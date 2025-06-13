import paho.mqtt.client as mqtt
from app.services.logger import CustomLogger
import psycopg2
import random

console = CustomLogger()

class OrchestrateData:
    def __init__(self, connection_string, table_name, topics, ip, port=1883):
        self.conn = psycopg2.connect(connection_string)
        self.topics = topics
        self.ip = ip
        self.port = port
        self.cursor = self.conn.cursor()
        self.table_name = table_name

        self.__listen_and_store_readings()

    def __create_table(self):
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id SERIAL PRIMARY KEY,
                station_id VARCHAR(100),
                device VARCHAR(255),
                sensor VARCHAR(255),
                temperature VARCHAR(255),
                humidity VARCHAR(255),
                air_quality VARCHAR(255),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def __insert_reading(self, data):
        self.cursor.execute(
            f"INSERT INTO {self.table_name} (station_id, device, sensor, temperature, humidity, air_quality) VALUES (%s, %s, %s, %s, %s, %s)",
            (data.get("station_id"), data.get("device"), data.get("sensor"), data.get("t"), data.get("m"), data.get("rssi"))
        )
        self.conn.commit()

    def _on_connect(self, client, _, __, rc):
        console.log("Connected with result code " + str(rc))

        for topic in self.topics:
            client.subscribe(topic)

    def _on_message(self, _, __, msg):
        console.log(f"Message received: {msg.payload}")

        decoded = msg.payload.decode()
        lines = decoded.strip().split('\n')
        readings = {}
        for line in lines:
            key, value = line.split(':', 1)
            readings[key.strip()] = value.strip()
        
        # add random station ids
        station_ids = [f"station{i}" for i in range(1, 6)]
        rand_staion_id = random.choice(station_ids)
        readings["station_id"] = rand_staion_id
        # console.debug(readings)

        self.__create_table()
        self.__insert_reading(readings)

    def __listen_and_store_readings(self):
        client = mqtt.Client()
        client.on_connect = self._on_connect
        client.on_message = self._on_message

        # TODO: Use env variable
        client.connect(self.ip, self.port, 60)
        client.loop_forever()
