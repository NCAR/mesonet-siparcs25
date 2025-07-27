from utils import utils_ftn, request, Config
from logger import CustomLogger
from batch import Batch
from llm_model import LLMModel
from redis_c import RedisClient

class ReadingService:
    def __init__(self, logger: CustomLogger, config: Config):
        self.console = logger
        self.db_url = config.database_api['base_url']
        self.db_uri = f"{self.db_url}/api/readings/"
        self.reading = {}

        llm_model = LLMModel(
            logger=logger,
            model_names=[config.model_service["model_name"]],
            model_service_base_url=config.model_service["base_url"]
        )

        redis_client = RedisClient(logger, config.redis["host"], config.redis["port"])

        self.reading_batch = Batch(logger,
            model=llm_model,
            redis_client=redis_client,
            batch_interval=config.station["batch_interval"],
            db_url=self.db_url
        )

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
                    self.reading["rssi"] = float(value.strip())
                case "device":
                    device, station_id = utils_ftn.parse_device(value.strip())
                    self.reading["station_id"] = station_id
                case "sensor":
                    protocol, model, measurement = utils_ftn.pass_sensor(value.strip())
                    self.reading["sensor_protocol"] = protocol
                    self.reading["sensor_model"] = model
                    self.reading["measurement"] = measurement
                case "t":
                    self.reading["timestamp"] = utils_ftn.parse_unix_time(value.strip())
                case _:
                    continue

            self.reading["edge_id"] = "ncar_edge"
        return self.reading

    async def create_reading(self):
        if not self.reading.get("station_id"):
            self.console.error("Station ID is required for creating a reading.")
            return {}
        
        # Update the batch buffer with the reading
        await self.reading_batch.set_readings_buffer(self.reading)

        return await request.insert(self.db_uri, self.reading)

    def add_location_to_reading(self, station_id, stations):
        for station in stations:
            if station.get("station_id") == station_id:
                self.reading["latitude"] = station.get("latitude")
                self.reading["longitude"] = station.get("longitude")
                break
        return self.reading
    
    def add_altitude_to_reading(self, station_id, stations):
        for station in stations:
            if station.get("station_id") == station_id:
                self.reading["altitude"] = station.get("altitude", 0.0)
                break
        return self.reading
