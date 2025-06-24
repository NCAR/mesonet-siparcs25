import paho.mqtt.client as mqtt
from logger import CustomLogger
from readings import ReadingService
from stations import StationService

class OrchestrateData:
    def __init__(self, logger: CustomLogger, db_uri: str, topics: list[str], ip: str, port=1883, admin_data=None):
        self.console = logger
        self.console.debug("Initializing OrchestrateData with MQTT and Reading Services")
        self.topics = topics
        self.ip = ip
        self.port = port
        self.admin_data = admin_data
        self.reading_service = ReadingService(logger, db_uri)
        self.console.debug(f"ReadingService initialized with db_uri: {db_uri}")
        self.station_service = StationService(logger, db_uri)
        self.console.debug(f"StationService initialized with db_uri: {db_uri}")
        self.station_service.add_default_stations()
        self.console.log("Stations added successfully.")
        
        # Start listening for readings
        self.listen_and_store_readings()

    def _on_connect(self, client, _, __, rc):
        self.console.log("Connected with result code " + str(rc))
        self.console.debug(f"Topics to subscribe: {self.topics}")
        self.console.debug(f"MQTT broker IP: {self.ip}, Port: {self.port}")
        self.console.log("Starting to listen for readings...")

        for topic in self.topics:
            client.subscribe(topic)

    def _on_message(self, _, __, msg):
        decoded = msg.payload.decode()
        decoded = decoded.strip().split('\n')
 
        if self.reading_service.is_mesonet_station(decoded):
            return

        stations = self.station_service.get_stations()
        if not stations:
            self.console.error("No stations found. Cannot process readings.")
            return
                
        station_id = self.reading_service.get_station_id(decoded)
        if not any(station.get("station_id") == station_id for station in stations):
            self.console.warning(f"Station ID {station_id} not found in the stations table. Adding it now.")
            self.station_service.add_new_station(station_id, self.admin_data)
        else:
            self.console.log(f"Station ID {station_id} found in the stations table. Proceeding with reading.")

        self.reading_service.add_location_to_reading(station_id, stations)
        
        self.reading_service.parse_reading(decoded)
        posted_reading = self.reading_service.create_reading()
        self.console.log(f"Reading posted: id={posted_reading.get('station_id')}")
    
    def listen_and_store_readings(self):
        client = mqtt.Client()
        client.on_connect = self._on_connect
        client.on_message = self._on_message

        # TODO: Use env variable
        client.connect(self.ip, self.port, 60)
        client.loop_forever()
