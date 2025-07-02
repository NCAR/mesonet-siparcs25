import json
from utils import utils_ftn, request
from logger import CustomLogger

class ReadingService:
    def __init__(self, logger: CustomLogger, bd_url: str):
        self.console = logger
        self.db_uri = f"{bd_url}/api/readings/"
        self.reading = {}

    def get_station_id(self, decoded_data):
        station_id = None
        for data in decoded_data:
            key, value = data.split(':', 1)
            if key.strip() == "device":
                _, station_id = utils_ftn.parse_device(value.strip())
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
        return self.reading

    async def create_reading(self):
        return await request.insert(self.db_uri, self.reading)

    def add_location_to_reading(self, station_id, stations):
        for station in stations:
            if station.get("station_id") == station_id:
                self.reading["latitude"] = station.get("latitude")
                self.reading["longitude"] = station.get("longitude")
                break
        return self.reading

    def is_mesonet_station(self, decoded_reading):
        try:
            reading = json.loads(decoded_reading[0])
            return reading.get("type") in ("sensor_data", "station_info")
        except (ValueError, TypeError):
            return False
