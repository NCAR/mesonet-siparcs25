from asyncio_mqtt import Client, MqttError
from utils.config import Config
from logger import CustomLogger
from reading import ReadingService
from station import StationService

class OrchestrateData:
    def __init__(self, logger: CustomLogger, config: Config):
        self.console = logger
        self.topics = config.mqtt["topics"]
        self.host = config.mqtt["host"]
        self.port = config.mqtt["port"]
        self.db_uri = config.database_api["base_url"]
        self.admin_data = config.metabase["admin_data"]
        self.reading_service = ReadingService(logger, config)
        self.station_service = StationService(logger, config)

    async def initialize(self):
        self.console.log("Initializing default stations...")
        await self.station_service.add_default_stations()

    async def listen_and_store_readings(self):
        try:
            async with Client(self.host, self.port) as client:
                async with client.messages() as messages:
                    for topic in self.topics:
                        await client.subscribe(topic)
                        self.console.debug(f"Subscribed to topic: {topic}")

                    async for msg in messages:
                        await self.on_message(msg)
        except MqttError as e:
            self.console.error(f"MQTT error: {e}")

    async def on_message(self, msg):
        decoded = msg.payload.decode().strip().split('\n')

        stations = await self.station_service.get_stations()
        if not stations:
            self.console.error("No stations found. Cannot process readings.")
            return

        station_id = self.reading_service.get_station_id(decoded)
        if not any(station.get("station_id") == station_id for station in stations):
            self.console.warning(f"Station ID {station_id} not found in the stations table. Adding it now.")
            await self.station_service.add_new_station(station_id, self.admin_data)
        else:
            self.console.log(f"Station ID {station_id} found. Proceeding with reading.")

        self.reading_service.add_location_to_reading(station_id, stations)
        self.reading_service.parse_reading(decoded)
        posted_reading = await self.reading_service.create_reading()
        self.console.log(f"Reading posted: id={posted_reading.get('station_id')}")
