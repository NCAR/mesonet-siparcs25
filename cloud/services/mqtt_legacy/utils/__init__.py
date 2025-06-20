from datetime import datetime
import requests
from logger import CustomLogger

console = CustomLogger()

sensor_measurements_map = {
    "rg15": "Acc Rain",
    "si7021": "Relative Humidity",
    "tmp1117": "Temperature",
    "ltr390": "UV Light",
    "pmsa003i": "Air Quality",
    "bme680": "Temperature"
}

class Utils:
    @staticmethod
    def parse_device(device_str):
        try:
            parts = device_str.rsplit('/', 1)
            device = parts[0]
            station_id = parts[1]
            return device, station_id
        except (IndexError, AttributeError):
            raise ValueError("Device string must be in the format 'platform/chip/station_id'")

    @staticmethod
    def pass_sensor(sensor_str):
        parts = sensor_str.strip().split('/')
        if len(parts) == 4:
            # Format: platform/protocol/model/measurement
            sensor_protocol = '/'.join(parts[0:2])  # protocol/model
            sensor_model = parts[2]
            measurement_key = parts[3]
        elif len(parts) == 3:
            # Format: protocol/model/measurement
            sensor_protocol = parts[0]
            sensor_model = parts[1]
            measurement_key = parts[2]
        else:
            raise ValueError("Sensor string must be in format 'protocol/model/measurement' or 'platform/protocol/model/measurement'")

        measurement = sensor_measurements_map.get(sensor_model)
        if not measurement:
            # if not part of the map, use the provided key
            measurement = measurement_key

        return sensor_protocol, sensor_model, measurement
    
    @staticmethod
    def parse_unix_time(unix_time, time_zone="local"):
        if time_zone == "utc":
            return datetime.fromtimestamp(int(unix_time), tz=datetime.timezone.utc)
        else:
            return datetime.fromtimestamp(int(unix_time))
        
    @staticmethod
    def insert(path, data):
        res = requests.post(
            path,
            json=data,
            headers={"Content-Type": "application/json"}
        )
        res.raise_for_status()
        return res.json()
    
    @staticmethod
    def get_all(path):
        res = requests.get(path)
        res.raise_for_status()
        return res.json()
        
utils_ftn = Utils
