from asyncio_mqtt import Client, MqttError
from logger import CustomLogger
from reading import ReadingService
from station import StationService

class OrchestrateData:
    def __init__(self, logger: CustomLogger, db_uri: str, mb_url: str, topics: list[str], ip: str, port=1883, admin_data=None):
        self.console = logger
        self.topics = topics
        self.ip = ip
        self.port = port
        self.admin_data = admin_data
        self.reading_service = ReadingService(logger, db_uri)
        self.station_service = StationService(logger, db_uri, mb_url)

    async def initialize(self):
        self.console.log("Initializing default stations...")
        await self.station_service.add_default_stations()

    async def listen_and_store_readings(self):
        try:
            async with Client(self.ip, self.port) as client:
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
