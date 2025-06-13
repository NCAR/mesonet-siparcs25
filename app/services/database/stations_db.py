import json
import os
from logger import CustomLogger
import psycopg2

console = CustomLogger()

class StationsDB:
    def __init__(self, connection_string, table_name):
        self.conn = psycopg2.connect(connection_string)
        self.cursor = self.conn.cursor()
        self.__table_name = table_name

    def __load_dummy_data(self, file_name):
        base_dir = os.path.dirname(__file__)
        file_path = os.path.join(base_dir, file_name)
        with open(file_path, 'r') as f:
            return json.load(f)

    def create_table(self):
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.__table_name} (
                id SERIAL PRIMARY KEY,
                station_id VARCHAR(255) NOT NULL UNIQUE,
                status VARCHAR(255),
                longitude DOUBLE PRECISION,
                latitude DOUBLE PRECISION,
                firstname CHAR(50),
                lastname CHAR(50),
                email VARCHAR(20),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def insert_station(self):
        file_name = "dummy_station_data.json"
        data = self.__load_dummy_data(file_name)
        for record in data:
            self.cursor.execute(
                f"INSERT INTO {self.__table_name} (station_id, status, latitude, longitude, firstname, lastname, email) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (station_id) DO NOTHING",
                (record["station_id"], record.get("status"), record.get("latitude"), record.get("longitude"), record.get("firstname"), record.get("lastname"), record.get("email"))
            )
        self.conn.commit()
        console.log(f"Database: Added data to {self.__table_name} table")
