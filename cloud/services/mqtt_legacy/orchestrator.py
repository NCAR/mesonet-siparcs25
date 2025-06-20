import paho.mqtt.client as mqtt
from logger import CustomLogger
from readings import ReadingService
from stations import StationService

console = CustomLogger()

class OrchestrateData:
    def __init__(self, db_uri, topics, ip, port=1883, admin_data=None):
        self.topics = topics
        self.ip = ip
        self.port = port
        self.admin_data = admin_data
        self.reading_service = ReadingService(db_uri)
        console.debug(f"ReadingService initialized with db_uri: {db_uri}")
        self.station_service = StationService(db_uri)
        console.debug(f"StationService initialized with db_uri: {db_uri}")
        self.station_service.add_default_stations()
        console.debug("Stations added successfully.")
        
        # Start listening for readings
        self.listen_and_store_readings()

    def _on_connect(self, client, _, __, rc):
        console.log("Connected with result code " + str(rc))
        console.debug(f"Topics to subscribe: {self.topics}")
        console.debug(f"MQTT broker IP: {self.ip}, Port: {self.port}")
        console.debug("Starting to listen for readings...")

        for topic in self.topics:
            client.subscribe(topic)

    def _on_message(self, _, __, msg):
        decoded = msg.payload.decode()
        decoded = decoded.strip().split('\n')

        stations = self.station_service.get_stations()
        if not stations:
            console.error("No stations found. Cannot process readings.")
            return
                
        # Check if the station_id from the reading exists in the stations table
        station_id = self.reading_service.get_station_id(decoded)
        if not any(station.get("station_id") == station_id for station in stations):
            console.debug(f"Station ID {station_id} not found in the stations table. Adding it now.")
            self.station_service.add_new_station(station_id, self.admin_data)
        else:
            console.debug(f"Station ID {station_id} found in the stations table. Proceeding with reading.")

        # TODO: Add latitude and longitude to the readings from the station table
        
        self.reading_service.parse_reading(decoded)
        posted_reading = self.reading_service.create_reading()
        console.debug(f"Reading posted: id={posted_reading.get('station_id')}")
    
    def listen_and_store_readings(self):
        client = mqtt.Client()
        client.on_connect = self._on_connect
        client.on_message = self._on_message

        # TODO: Use env variable
        client.connect(self.ip, self.port, 60)
        client.loop_forever()
