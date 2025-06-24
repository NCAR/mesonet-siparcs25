from utils import utils_ftn
from logger import CustomLogger
import json

class ReadingService:
    def __init__(self, logger: CustomLogger, bd_uri: str):
        self.console = logger
        self.console.debug(f"Initializing ReadingService with database URI: {bd_uri}")
        self.db_uri = bd_uri
        self.reading = {}

    def get_station_id(self, decoded_data):
        """
        Retrieves the station ID from the reading data.
        """
        station_id = None
        for data in decoded_data:
            key, value = data.split(':', 1)

            if key.strip() == "device":
                _, station_id = utils_ftn.parse_device(value.strip())
                station_id = station_id
                break
        if not station_id:
            raise ValueError(f"Station ID not found in the reading data {decoded_data}.")
        return station_id

    def parse_reading(self, decoded_data):
        for data in decoded_data:
            key, value = data.split(':', 1)

            match key.strip():
                case "m":
                    self.reading["reading_value"] = float(value.strip())
                case "rssi":
                    self.reading["signal_strength"] = float(value.strip())
                case "device":
                    device, station_id = utils_ftn.parse_device(value.strip())
                    self.reading["device"] = device
                    self.reading["station_id"] = station_id
                case "sensor":
                    protocol, model, measurement = utils_ftn.pass_sensor(value.strip())
                    self.reading["sensor_protocol"] = protocol
                    self.reading["sensor_model"] = model
                    self.reading["measurement"] = measurement
                case _:
                    continue
    
    def create_reading(self):
        path = f"{self.db_uri}/api/readings"
        posted_readings = utils_ftn.insert(path, self.reading)
        return posted_readings
    
    def add_location_to_reading(self, station_id, stations):
        """
        Adds latitude and longitude to the reading from the station table.
        """
        for station in stations:
            if station.get("station_id") == station_id:
                self.reading["latitude"] = station.get("latitude")
                self.reading["longitude"] = station.get("longitude")
                break
        return self.reading
    
    def is_mesonet_station(self, decoded_reading):
        """
        Checks if the station the reading belongs to is a mesonet station.
        """
        try:
            reading = json.loads(decoded_reading[0])
            return reading.get("type") == "sensor_data" or reading.get("type") == "station_info"
        except (ValueError, TypeError):
            return False
