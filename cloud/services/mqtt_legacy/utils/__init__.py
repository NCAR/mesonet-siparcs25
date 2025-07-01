from datetime import datetime
import httpx

sensor_measurements_map = {
    "rg15": "Acc Rain",
    "si7021": "Humidity",
    "tmp1117": "Temperature",
    "ltr390": "UV Light",
    "pmsa003i": "Air Quality",
    "bme680": "Temperature",
}
headers = {"Content-Type": "application/json"}

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

        return sensor_protocol, sensor_model, measurement.lower()
    
    @staticmethod
    def parse_unix_time(unix_time, time_zone="local"):
        if time_zone == "utc":
            return datetime.fromtimestamp(int(unix_time), tz=datetime.timezone.utc)
        else:
            return datetime.fromtimestamp(int(unix_time))
    
    @staticmethod
    async def insert(path: str, data):
        path = path if path.endswith('/') else path + '/'
        async with httpx.AsyncClient() as client:
            res = await client.post(
                path,
                json=data,
                headers=headers
            )

            if not (200 <= res.status_code < 300):
                return res.raise_for_status()
            return res.json()
        
    @staticmethod
    async def get_all(path: str):
        path = path if path.endswith('/') else path + '/'
        async with httpx.AsyncClient() as client:
            res = await client.get(path, headers=headers)

            if not (200 <= res.status_code < 300):
                res.raise_for_status()
            return res.json()
 
utils_ftn = Utils
