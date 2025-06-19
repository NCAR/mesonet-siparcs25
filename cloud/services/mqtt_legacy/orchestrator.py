import paho.mqtt.client as mqtt
from logger import CustomLogger
from utils import utils_ftn

console = CustomLogger()

class OrchestrateData:
    def __init__(self, db_uri, topics, ip, port=1883):
        self.topics = topics
        self.ip = ip
        self.port = port
        self.db_uri = db_uri

        self.__listen_and_store_readings()

    # TODO: Move to the ReadingService class
    def __parse_readings(self, decoded_data):
        readings = {}
        for data in decoded_data:
            key, value = data.split(':', 1)
        
            match key.strip():
                case "m":
                    readings["reading_value"] = float(value.strip())
                case "rssi":
                    readings["signal_strength"] = float(value.strip())
                case "device":
                    device, station_id = utils_ftn.parse_device(value.strip())
                    readings["device"] = device
                    readings["station_id"] = station_id
                case "sensor":
                    protocol, model, measurement = utils_ftn.pass_sensor(value.strip())
                    readings["sensor_protocol"] = protocol
                    readings["sensor_model"] = model
                    readings["measurement"] = measurement
                case _:
                    continue
        return readings

    def _on_connect(self, client, _, __, rc):
        console.log("Connected with result code " + str(rc))

        for topic in self.topics:
            client.subscribe(topic)

    def _on_message(self, _, __, msg):
        decoded = msg.payload.decode()
        decoded = decoded.strip().split('\n')

        # TODO: add ReadingService to handle reading crud operations

        # TODO: when it recieves a new station_id, add it to the stations table first

        # TODO: Add latitude and longitude to the readings from the station table
        
        readings = self.__parse_readings(decoded)
        # console.debug(json.dumps(readings, indent=4))
        path = f"{self.db_uri}/api/readings"
        posted_readings = utils_ftn.insert(path, readings)
        console.debug(f"Reading posted: id={posted_readings.get('station_id')}")
    
    def __listen_and_store_readings(self):
        client = mqtt.Client()
        client.on_connect = self._on_connect
        client.on_message = self._on_message

        # TODO: Use env variable
        client.connect(self.ip, self.port, 60)
        client.loop_forever()
