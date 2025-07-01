#include <LittleFS.h>
#include <SPI.h>
#include <RH_RF95.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME680.h>
#include <Adafruit_Si7021.h>
#include <Adafruit_TMP117.h>
#include <Adafruit_LTR390.h>
#include <Adafruit_PM25AQI.h>
#include <Adafruit_GPS.h>
#include <SensirionI2cScd4x.h>
#include <ArduinoUniqueID.h>
#include <TinyGPS++.h>
#include <SparkFun_I2C_GPS_Arduino_Library.h>
#include <SparkFun_SCD4x_Arduino_Library.h>
#include <ArduinoJson.h>
#include <pico/stdlib.h>


// Pin definitions
#define RFM95_CS 16
#define RFM95_INT 21
#define RFM95_RST 17
#define RF95_FREQ 915.0
#define SEALEVELPRESSURE_HPA (1013.25)

// macro definitions
// make sure that we use the proper definition of NO_ERROR
#ifdef NO_ERROR
#undef NO_ERROR
#endif
#define NO_ERROR 0

// Hardware objects
RH_RF95 rf95(RFM95_CS, RFM95_INT);
Adafruit_Si7021 si7021;
Adafruit_BME680 bme680;
Adafruit_TMP117 tmp117;
Adafruit_GPS pa1010d(&Wire);
I2CGPS sparkfun_GPS;
Adafruit_LTR390 ltr390;
Adafruit_PM25AQI pm25aqi;
TinyGPSPlus gps;
SCD4x scd40;

// Config parameters
struct Config {
  float overload_threshold;
  float station_relay_midpoint;
  float station_relay_steepness;
  float station_sensor_midpoint;
  float station_sensor_steepness;
  float station_relay_weight;
  float station_sensor_weight;
  float score_rssi_weight;
  float score_load_weight;
  float score_type_weight;
  float score_relay_weight;
  float score_relay_decay;
  uint32_t pong_timeout;
  uint32_t keep_alive_interval;
  uint32_t keep_alive_timeout;
  float latitude;
  float longitude;
  uint32_t station_info_interval;
  bool fixed_deployment;
  uint32_t gps_fixed_interval;
} config;

// State variables
char device_id[17] = {0}; // 16-char hex ID
char target_id[17] = {0};
bool has_pi_path = false;
uint8_t relay_count = 0;
uint8_t target_relay_count = 0;
uint32_t last_broadcast = 0;
uint32_t last_ping = 0;
uint32_t last_keep_alive_sent = 0;
uint32_t last_keep_alive_received = 0;
bool waiting_for_pongs = false;
uint32_t pong_start_time = 0;
uint32_t last_station_info_sent = 0;
uint32_t last_gps_sent = 0;
uint32_t last_ping_attempt = 0;
const uint32_t PING_MIN_INTERVAL = 10000;

// Load tracking
uint8_t active_sensors = 0;
uint8_t active_relays = 0;
uint32_t last_load_update = 0;
float station_load = 0.0;

// Sensor connection flags
bool si7021_connected = false;
bool bme680_connected = false;
bool tmp117_connected = false;
bool ltr390_connected = false;
bool pm25aqi_connected = false;
bool pa1010d_connected = false;
bool gps_connected = false; // PA1010D or SF_XA1110
bool scd40_connected = false;

// GPS state
double latitude;
double longitude;
String gps_timestamp;

// Dependents tracking
struct Dependent {
  char id[17];
};
Dependent dependents[3];
uint8_t dependent_count = 0;

// Pong data structure
struct Pong {
  char id[17];
  char type[3]; // "pi" or "st"
  float load;
  int8_t rssi;
  uint8_t relay_count;
};
Pong pongs[5];
uint8_t pong_count = 0;

void blink_led() {
  Serial.println(F("[debug]: Blinking LED"));
  digitalWrite(LED_BUILTIN, HIGH);
  delay(500);
  digitalWrite(LED_BUILTIN, LOW);
  delay(500);
}

// Load config from LittleFS
bool load_config() {
  Serial.println(F("[debug]: Loading /config.json"));
  File file = LittleFS.open("/config.json", "r");
  if (!file) {
    Serial.println(F("[error]: Failed to open /config.json"));
    return false;
  }
  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, file);
  file.close();
  if (error) {
    Serial.print(F("[error]: JSON parse failed: ")); Serial.println(error.c_str());
    return false;
  }
  config.overload_threshold = doc["radio"]["overload_threshold"] | 0.85f;
  config.station_relay_midpoint = doc["radio"]["station_relay_midpoint"] | 10.0f;
  config.station_relay_steepness = doc["radio"]["station_relay_steepness"] | 0.2f;
  config.station_sensor_midpoint = doc["radio"]["station_sensor_midpoint"] | 5.0f;
  config.station_sensor_steepness = doc["radio"]["station_sensor_steepness"] | 0.5f;
  config.station_relay_weight = doc["radio"]["station_relay_weight"] | 0.7f;
  config.station_sensor_weight = doc["radio"]["station_sensor_weight"] | 0.3f;
  config.score_rssi_weight = doc["radio"]["score_rssi_weight"] | 0.35f;
  config.score_load_weight = doc["radio"]["score_load_weight"] | 0.35f;
  config.score_type_weight = doc["radio"]["score_type_weight"] | 0.2f;
  config.score_relay_weight = doc["radio"]["score_relay_weight"] | 0.1f;
  config.score_relay_decay = doc["radio"]["score_relay_decay"] | 1.0f;
  config.pong_timeout = doc["radio"]["pong_timeout"] | 12000UL;
  config.keep_alive_interval = doc["radio"]["keep_alive_interval"] | 30000UL;
  config.keep_alive_timeout = doc["radio"]["keep_alive_timeout"] | 60000UL;
  config.latitude = doc["station_info"]["latitude"] | 0.0;
  config.longitude = doc["station_info"]["longitude"] | 0.0;
  latitude = config.latitude;
  longitude = config.longitude;
  config.station_info_interval = doc["station_info"]["station_info_interval"] | 86400000UL;
  config.fixed_deployment = doc["station_info"]["fixed_deployment"] | true;
  config.gps_fixed_interval = doc["station_info"]["gps_fixed_interval"] | 43200000UL;
  doc.clear();
  Serial.println(F("[info]: Loaded /config.json"));
  return true;
}
// Initialize sensors
bool pa1010d_gps_init() {
  //    pa1010d.sendCommand(PMTK_SET_NMEA_OUTPUT_RMCGGA);
  //    pa1010d.sendCommand(PMTK_SET_NMEA_UPDATE_1HZ);
  //    delay(1000);
  //    if (!pa1010d.begin(0x10)) {
  //        Serial.println("[warn] Adafruit PA1010D GPS Module not found.");
  //        return false;
  //    }
  //    Serial.println("[info] Adafruit PA1010D GPS module found");
  if (sparkfun_GPS.begin() == false)
  {
    Serial.println("Module failed to respond. Please check wiring.");
    return false;
  }
  Serial.println("[info] GPS module found");
  return true;
}

bool bme680_init() {
  Serial.println(F("[debug]: Initializing BME680"));
  delay(500);
  if (!bme680.begin()) {
    Serial.println(F("[error]: BME680 init failed"));
    return false;
  }
  bme680.setTemperatureOversampling(BME680_OS_8X);
  bme680.setHumidityOversampling(BME680_OS_2X);
  bme680.setPressureOversampling(BME680_OS_4X);
  bme680.setIIRFilterSize(BME680_FILTER_SIZE_3);
  bme680.setGasHeater(320, 150);
  Serial.println("[info]: Adafruit BME680 qwiic sensor found ... OK");
  return true;
}

bool si7021_init() {
  Serial.println(F("[debug]: Initializing Si7021"));
  delay(500);
  if (!si7021.begin()) {
    Serial.println(F("[error]: Adafruit Si7021 qwiic sensor not found"));
    return false;
  }
  Serial.print(F("[info]: Adafruit Si7021 qwiic sensor found ... OK: model >>"));
  switch (si7021.getModel()) {
    case SI_Engineering_Samples: Serial.print(F("SI engineering samples")); break;
    case SI_7013: Serial.print(F("Si7013")); break;
    case SI_7020: Serial.print(F("Si7020")); break;
    case SI_7021: Serial.print(F("Si7021")); break;
    default: Serial.print(F("Unknown"));
  }
  Serial.print(F(" Rev(")); Serial.print(si7021.getRevision()); Serial.print(F(")"));
  Serial.print(F(" Serial #")); Serial.print(si7021.sernum_a, HEX); Serial.println(si7021.sernum_b, HEX);
  return true;
}

bool tmp117_init() {
  Serial.println(F("[debug]: Initializing TMP117"));
  delay(500);
  if (!tmp117.begin()) {
    Serial.println(F("[error]: Adafruit TMP117 qwiic sensor not found"));
    return false;
  }
  Serial.println(F("[info]: Adafruit TMP117 qwiic sensor found ... OK"));
  return true;
}

bool ltr390_init() {
  Serial.println(F("[debug]: Initializing LTR390"));
  delay(500);
  if (!ltr390.begin()) {
    Serial.println(F("[error]: Adafruit LTR390 qwiic sensor not found"));
    return false;
  }
  ltr390.setMode(LTR390_MODE_UVS); // UV mode, switch to ALS if needed
  ltr390.setGain(LTR390_GAIN_3);
  ltr390.setResolution(LTR390_RESOLUTION_16BIT);
  ltr390.setThresholds(0, 100);
  Serial.println(F("[info]: Adafruit LTR390 qwiic sensor found ... OK"));
  return true;
}

bool pm25aqi_init() {
  Serial.println(F("[debug]: Initializing PM25AQI"));
  delay(500);
  if (!pm25aqi.begin_I2C()) {
    Serial.println(F("[error]: Adafruit PM25AQI qwiic sensor not found"));
    return false;
  }
  Serial.println(F("[info]: Adafruit PM25AQI qwiic sensor found ... OK"));
  return true;
}

// SCD40 state
static char errorMessage[64];
static int16_t error;

bool scd40_init() {
  if (scd40.begin() == false)
  {
    Serial.println(F("Sensor not detected. Please check wiring."));
    return false;
  }
  return true;
}


// RFM95 functions
void rfm95_start() {
  Serial.println(F("[debug]: Starting RFM95"));
  pinMode(RFM95_RST, OUTPUT);
  digitalWrite(RFM95_RST, HIGH);
}

void rfm95_reset() {
  Serial.println(F("[debug]: Resetting RFM95"));
  digitalWrite(RFM95_RST, LOW);
  delay(10);
  digitalWrite(RFM95_RST, HIGH);
  delay(10);
}

bool rfm95_init() {
  Serial.println(F("[debug]: Initializing RFM95"));
  if (!rf95.init()) {
    Serial.println(F("[warn]: LoRa radio init failed"));
    return false;
  }
  Serial.println(F("[info]: Adafruit RP2040-LoRa radio init OK!"));
  if (!rf95.setFrequency(RF95_FREQ)) {
    Serial.println(F("[error]: radio setFrequency() failed"));
    while (1);
  }
  rf95.setModemConfig(RH_RF95::Bw125Cr45Sf128);
  rf95.setTxPower(23, false);
  rf95.setPreambleLength(6);
  Serial.println(F("[info]: RFM95 configured: BW=125kHz, CR=4/5, SF=7, Preamble=6"));
  return true;
}

void rfm95_send(const char* packet) {
  Serial.println(F("[debug]: Enter rfm95_send"));
  uint8_t len = strlen(packet);
  Serial.print(F("[debug]: Packet length: ")); Serial.println(len);
  Serial.print(F("[info]: sending packet >> ")); Serial.println(packet);
  if (!rf95.send((uint8_t*)packet, len)) {
    Serial.println(F("[error]: rf95.send failed"));
    return;
  }
  Serial.println(F("[debug]: Waiting for packet sent"));
  if (!rf95.waitPacketSent()) {
    Serial.println(F("[error]: rf95.waitPacketSent timed out"));
    return;
  }
  Serial.println(F("[debug]: Packet sent successfully"));
  delay(10);
  Serial.println(F("[debug]: Exit rfm95_send"));
}

// Calculate station load
void update_station_load() {
  if (millis() - last_load_update >= 30000) {
    Serial.println(F("[debug]: Updating station load"));
    active_sensors = si7021_connected + bme680_connected + tmp117_connected +
                     ltr390_connected + pm25aqi_connected + scd40_connected;
    float sensor_load = 1.0 / (1.0 + exp(-config.station_sensor_steepness * (active_sensors - config.station_sensor_midpoint)));
    float relay_load = 1.0 / (1.0 + exp(-config.station_relay_steepness * (active_relays - config.station_relay_midpoint)));
    station_load = config.station_relay_weight * relay_load + config.station_sensor_weight * sensor_load;
    active_relays = 0;
    last_load_update = millis();
    Serial.print(F("[info]: Station load: ")); Serial.print(station_load);
    Serial.print(F(" (Relay Load: ")); Serial.print(relay_load);
    Serial.print(F(", Sensor Load: ")); Serial.print(sensor_load);
    Serial.print(F(", Active Sensors: ")); Serial.print(active_sensors); Serial.println(F(")"));
  }
}

// Send ping packet
bool send_ping() {
  if (millis() - last_ping_attempt < PING_MIN_INTERVAL) {
    //Serial.println(F("[debug]: Skipping send_ping, within minimum interval"));
    return false;
  }
  last_ping_attempt = millis();
  Serial.println(F("[debug]: Enter send_ping"));
  StaticJsonDocument<64> doc;
  char packet[48];
  // Packet fields for ping:
  doc["sid"] = device_id;    // "sid": Station ID, 16-char hex (e.g., "0123456789ABCDEF")
  doc["t"] = "A";            // "t": Type, "A" for ping to discover stations/Pi
  size_t serialized_size = serializeJson(doc, packet, sizeof(packet));
  if (serialized_size >= sizeof(packet)) {
    Serial.println(F("[error]: Ping packet buffer overflow"));
    return false;
  }
  waiting_for_pongs = true;
  pong_count = 0;
  pong_start_time = millis();
  last_ping = millis();
  Serial.println(F("[debug]: Sending ping packet"));
  rfm95_send(packet);
  Serial.println(F("[info]: Sent ping, waiting for pongs"));
  while (millis() - pong_start_time < config.pong_timeout) {
    rfm95_receive();
    delay(10);
    rp2040.wdt_reset();
  }
  waiting_for_pongs = false;
  select_best_target();
  bool target_assigned = target_id[0] != '\0';
  if (target_assigned) {
    Serial.print(F("[info]: Target assigned: ")); Serial.println(target_id);
  } else {
    Serial.println(F("[warn]: No target assigned after pong timeout"));
  }
  Serial.println(F("[debug]: Exit send_ping"));
  return target_assigned;
}

// Send disconnect
void send_disconnect() {
  Serial.println(F("[debug]: Sending disconnect to dependents"));
  StaticJsonDocument<64> doc;
  char packet[48];
  for (uint8_t i = 0; i < dependent_count; i++) {
    // Packet fields for disconnect:
    doc["sid"] = device_id;    // "sid": Station ID, 16-char hex
    doc["t"] = "D";            // "t": Type, "D" for disconnect to clear connections
    doc["to"] = dependents[i].id; // "to": Target ID, 16-char hex of dependent
    serializeJson(doc, packet, sizeof(packet));
    rfm95_send(packet);
    Serial.print(F("[info]: Sent disconnect to ")); Serial.println(dependents[i].id);
  }
  dependent_count = 0;
}

// Send keep-alive
void send_keep_alive() {
  if (has_pi_path && millis() - last_keep_alive_sent >= config.keep_alive_interval) {
    Serial.println(F("[debug]: Sending keep-alive to dependents"));
    StaticJsonDocument<64> doc;
    char packet[48];
    for (uint8_t i = 0; i < dependent_count; i++) {
      // Packet fields for keep-alive:
      doc["sid"] = device_id;    // "sid": Station ID, 16-char hex
      doc["t"] = "C";            // "t": Type, "C" for keep-alive to maintain connection
      doc["to"] = dependents[i].id; // "to": Target ID, 16-char hex of dependent
      serializeJson(doc, packet, sizeof(packet));
      rfm95_send(packet);
      Serial.print(F("[info]: Sent keep-alive to ")); Serial.println(dependents[i].id);
    }
    last_keep_alive_sent = millis();
  }
}

// Send station_info
void send_station_info() {
  Serial.println(F("[debug]: Preparing to send station_info"));

  // Read configuration from LittleFS
  File file = LittleFS.open("/config.json", "r");
  if (!file) {
    Serial.println(F("[error]: Failed to open /config.json for station_info"));
    return;
  }

  // Parse JSON configuration
  StaticJsonDocument<256> cfg;
  DeserializationError error = deserializeJson(cfg, file);
  file.close();
  if (error) {
    Serial.print(F("[error]: JSON parse failed: "));
    Serial.println(error.c_str());
    return;
  }

  // Prepare station_info packet
  StaticJsonDocument<256> doc;
  char packet[256];
  doc["sid"] = device_id;    // Station ID, 16-char hex
  doc["t"] = "E";            // Type, "E" for station metadata
  doc["fn"] = cfg["station_info"]["firstname"] | ""; // First name, string
  doc["ln"] = cfg["station_info"]["lastname"] | "";  // Last name, string
  doc["e"] = cfg["station_info"]["email"] | "";     // Email, string
  doc["o"] = cfg["station_info"]["organization"] | ""; // Organization, string
  doc["lat"] = latitude;     // Latitude, float
  doc["lon"] = longitude;    // Longitude, float
  if (target_id[0]) doc["to"] = target_id; // Target ID, 16-char hex if assigned
  doc["r"] = !target_id[0];  // Allow relay, boolean (true if no target)
  String gps_timestamp = get_gps_timestamp();
  if (!gps_timestamp.isEmpty()) doc["ts"] = gps_timestamp; // Timestamp if GPS fix
  serializeJson(doc, packet, sizeof(packet));

  // Send the packet three times with a delay
  const int send_attempts = 3;
  const int delay_ms = 100; // 100ms delay between attempts
  for (int i = 0; i < send_attempts; i++) {
    Serial.print(F("[debug]: Sending station_info attempt "));
    Serial.println(i + 1);
    rfm95_send(packet);
    if (i < send_attempts - 1) { // No delay after the last attempt
      delay(delay_ms);
    }
  }

  Serial.println(F("[info]: Sent station_info message 3 times"));
  last_station_info_sent = millis();
}

// Select best target
void select_best_target() {
  Serial.println(F("[debug]: Selecting best target"));
  if (!pong_count) {
    target_id[0] = '\0';
    has_pi_path = false;
    relay_count = 0;
    send_disconnect();
    Serial.println(F("[warn]: No pongs received, broadcasting without target"));
    return;
  }
  float best_score = -1.0;
  char best_id[17] = {0};
  bool best_is_pi = false;
  uint8_t best_relay_count = 255;
  for (uint8_t i = 0; i < pong_count; i++) {
    float norm_rssi = (pongs[i].rssi + 120.0f) / 70.0;
    if (norm_rssi < 0) norm_rssi = 0;
    if (norm_rssi > 1) norm_rssi = 1;
    float type_bonus = strcmp(pongs[i].type, "pi") == 0 ? 1.0 : 0.0;
    float relay_penalty = exp(-config.score_relay_decay * pongs[i].relay_count);
    float score = config.score_rssi_weight * norm_rssi + config.score_load_weight * (1.0 - pongs[i].load) +
                  config.score_type_weight * type_bonus + config.score_relay_weight * relay_penalty;
    Serial.print(F("[info]: Pong from ")); Serial.print(pongs[i].id);
    Serial.print(F(" (")); Serial.print(pongs[i].type); Serial.print(F(")"));
    Serial.print(F(", RSSI: ")); Serial.print(pongs[i].rssi);
    Serial.print(F(", Load: ")); Serial.print(pongs[i].load);
    Serial.print(F(", Relay Count: ")); Serial.print(pongs[i].relay_count);
    Serial.print(F(", Score: ")); Serial.println(score);
    if (score > best_score || (score == best_score && type_bonus == 1.0)) {
      best_score = score;
      strlcpy(best_id, pongs[i].id, sizeof(best_id));
      best_is_pi = strcmp(pongs[i].type, "pi") == 0;
      best_relay_count = pongs[i].relay_count;
    }
  }
  if (best_id[0]) {
    strlcpy(target_id, best_id, sizeof(target_id));
    has_pi_path = best_is_pi || best_relay_count < 255;
    target_relay_count = best_relay_count;
    relay_count = best_is_pi ? 0 : best_relay_count + 1;
    Serial.print(F("[info]: Selected target: ")); Serial.print(target_id);
    Serial.print(F(" (Pi Path: ")); Serial.print(has_pi_path);
    Serial.print(F(", Relay Count: ")); Serial.print(relay_count); Serial.println(F(")"));
    last_keep_alive_received = millis();
  } else {
    target_id[0] = '\0';
    has_pi_path = false;
    relay_count = 0;
    send_disconnect();
    Serial.println(F("[warn]: No valid target selected"));
  }
}

// Add dependent
void add_dependent(const char* station_id) {
  Serial.print(F("[debug]: Adding dependent: ")); Serial.println(station_id);
  for (uint8_t i = 0; i < dependent_count; i++) {
    if (!strcmp(dependents[i].id, station_id)) {
      Serial.println(F("[info]: Already a dependent"));
      return;
    }
  }
  if (dependent_count < sizeof(dependents) / sizeof(dependents[0])) {
    strlcpy(dependents[dependent_count].id, station_id, sizeof(dependents[0].id));
    dependent_count++;
    Serial.print(F("[info]: Added dependent: ")); Serial.println(station_id);
  }
}

// Receive LoRa packets
void rfm95_receive() {
  Serial.println(F("[debug]: Enter rfm95_receive"));
  if (rf95.waitAvailableTimeout(2000)) {
    uint8_t buf[128];
    uint8_t len = sizeof(buf);
    int8_t rssi = rf95.lastRssi();
    if (rf95.recv(buf, &len)) {
      buf[len] = '\0';
      Serial.print(F("[info]: Received packet >> ")); Serial.println((char*)buf);
      StaticJsonDocument<96> doc;
      DeserializationError error = deserializeJson(doc, (char*)buf);
      if (error) {
        Serial.print(F("[error]: JSON deserialization failed: ")); Serial.println(error.c_str());
        return;
      }
      const char* station_id = doc["sid"] | "";
      if (!station_id[0] || !strcmp(station_id, device_id)) {
        Serial.print(F("[error]: Invalid station_id in packet: ")); Serial.println(station_id);
        return;
      }
      if (doc["t"] == "A") {
        update_station_load();
        if (station_load > config.overload_threshold) {
          Serial.println(F("[warn]: Load too high, refusing pong response"));
          return;
        }
        if (!has_pi_path) {
          Serial.println(F("[info]: No Pi path, skipping pong response"));
          return;
        }
        StaticJsonDocument<96> pong_doc;
        char packet[64];
        // Packet fields for pong:
        pong_doc["sid"] = device_id;    // "sid": Station ID, 16-char hex
        pong_doc["t"] = "B";            // "t": Type, "B" for pong response to ping
        pong_doc["ty"] = "2";           // "ty": Device type, "2" for station (vs. "1" for Pi)
        pong_doc["l"] = station_load;   // "l": Station load, float (0.0 to 1.0)
        pong_doc["rssi"] = rssi;        // "rssi": Received signal strength, int8_t (e.g., -100)
        pong_doc["rc"] = relay_count;   // "rc": Relay count, uint8_t (hops to Pi)
        serializeJson(pong_doc, packet, sizeof(packet));
        rfm95_send(packet);
        Serial.println(F("[info]: Sent pong response"));
      } else if (doc["t"] == "B" && waiting_for_pongs) {
        if (pong_count < sizeof(pongs) / sizeof(pongs[0])) {
          strlcpy(pongs[pong_count].id, station_id, sizeof(pongs[0].id));
          strlcpy(pongs[pong_count].type, doc["ty"] | "2", sizeof(pongs[0].type));
          pongs[pong_count].load = doc["l"] | 0.0f;
          pongs[pong_count].rssi = doc["rssi"] | 0;
          pongs[pong_count].relay_count = doc["rc"] | 0;
          pong_count++;
          Serial.println(F("[info]: Stored pong"));
        }
      } else if (doc["t"] == "C" && !strcmp(doc["to"] | "", device_id)) {
        if (!strcmp(station_id, target_id)) {
          last_keep_alive_received = millis();
          Serial.println(F("[info]: Received keep-alive from target"));
          //delay(2000);
        }
      } else if (doc["t"] == "D" && !strcmp(doc["to"] | "", device_id)) {
        target_id[0] = '\0';
        has_pi_path = false;
        relay_count = 0;
        send_disconnect();
        Serial.println(F("[info]: Received disconnect, cleared target and sent disconnect to dependents"));
        send_ping();
      } else if (doc["to"] && !strcmp(doc["to"] | "", device_id)) {
        add_dependent(station_id);
        if (target_id[0] && doc["r"] | false && station_load <= config.overload_threshold) {
          doc["to"] = target_id;
          char packet[128];
          serializeJson(doc, packet, sizeof(packet));
          rfm95_send(packet);
          active_relays++;
          Serial.println(F("[info]: Relayed packet"));
        }
      } else if (target_id[0] && doc["r"] | false && !doc["to"].isNull() && station_load <= config.overload_threshold) {
        doc["to"] = target_id;
        char packet[128];
        serializeJson(doc, packet, sizeof(packet));
        rfm95_send(packet);
        active_relays++;
        Serial.println(F("[info]: Relayed packet"));
      }
    }
  }
  Serial.println(F("[debug]: Exit rfm95_receive"));
}

// Helper for JSON fields
void add_common_json_fields(JsonDocument& doc, const String& timestamp, const char* sensor, const char* measurement, float data) {
  // Common fields for sensor packets:
  doc["sid"] = device_id;    // "sid": Station ID, 16-char hex
  if (!timestamp.isEmpty()) doc["ts"] = timestamp; // "ts": Timestamp, ISO 8601 string (e.g., "2025-06-22T20:56:00Z")
  doc["s"] = sensor;         // "s": Sensor name, string (e.g., "bme680")
  doc["m"] = measurement;    // "m": Measurement type, string (e.g., "temperature")
  doc["d"] = data;           // "d": Measurement value, float (e.g., 23.5)
  if (target_id[0]) doc["to"] = target_id; // "to": Target ID, 16-char hex if assigned
  doc["r"] = !target_id[0];  // "r": Allow relay, boolean (true if no target)
}

// Sensor transmit functions
bool si7021_measure_transmit() {
  Serial.println(F("[debug]: Enter si7021_measure_transmit"));
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping Si7021 transmit"));
    return false;
  }
  String timestamp = get_gps_timestamp();
  StaticJsonDocument<96> doc;
  char packet[128];
  // Sensor packet for temperature:
  doc["t"] = "F";            // "t": Type, "F" for sensor data
  add_common_json_fields(doc, timestamp, "si7021", "tmp", si7021.readTemperature());
  serializeJson(doc, packet, sizeof(packet));
  rfm95_send(packet);

  // Sensor packet for humidity:
  doc["t"] = "F";            // "t": Type, "F" for sensor data
  add_common_json_fields(doc, timestamp, "si7021", "rh", si7021.readHumidity());
  serializeJson(doc, packet, sizeof(packet));
  rfm95_send(packet);
  Serial.println(F("[debug]: Exit si7021_measure_transmit"));
  return true;
}

bool bme680_measure_transmit() {
  Serial.println(F("[debug]: Enter bme680_measure_transmit"));
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping BME680 transmit"));
    return false;
  }
  if (!bme680.performReading()) {
    Serial.println(F("[error]: Failed to perform reading"));
    return false;
  }
  String timestamp = get_gps_timestamp();
  StaticJsonDocument<96> doc;
  char packet[144];
  // Sensor packet for temperature:
  doc["t"] = "F";            // "t": Type, "F" for sensor data
  add_common_json_fields(doc, timestamp, "bme680", "tmp", bme680.temperature);
  serializeJson(doc, packet, sizeof(packet));
  rfm95_send(packet);
  // Sensor packet for humidity:
  doc["t"] = "F";            // "t": Type, "F" for sensor data
  add_common_json_fields(doc, timestamp, "bme680", "rh", bme680.humidity);
  serializeJson(doc, packet, sizeof(packet));
  rfm95_send(packet);
  // Sensor packet for pressure:
  doc["t"] = "F";            // "t": Type, "F" for sensor data
  add_common_json_fields(doc, timestamp, "bme680", "pre", bme680.pressure / 100.0);
  serializeJson(doc, packet, sizeof(packet));
  rfm95_send(packet);
  Serial.println(F("[debug]: Exit bme680_measure_transmit"));
  return true;
}

bool tmp117_measure_transmit() {
  Serial.println(F("[debug]: Enter tmp117_measure_transmit"));
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping TMP117 transmit"));
    return false;
  }
  sensors_event_t temp;
  tmp117.getEvent(&temp);
  String timestamp = get_gps_timestamp();
  StaticJsonDocument<96> doc;
  char packet[144];
  // Sensor packet for temperature:
  doc["t"] = "F";            // "t": Type, "F" for sensor data
  add_common_json_fields(doc, timestamp, "tmp117", "tmp", temp.temperature);
  serializeJson(doc, packet, sizeof(packet));
  rfm95_send(packet);
  Serial.println(F("[debug]: Exit tmp117_measure_transmit"));
  return true;
}

bool ltr390_measure_transmit() {
  Serial.println(F("[debug]: Enter ltr390_measure_transmit"));
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping LTR390 transmit"));
    return false;
  }
  String timestamp = get_gps_timestamp();
  StaticJsonDocument<96> doc;
  char packet[144];
  // Sensor packet for UV index (UVI):
  ltr390.setMode(LTR390_MODE_UVS);
  if (ltr390.newDataAvailable()) {
    float uvs = ltr390.readUVS();
    doc["t"] = "F";            // "t": Type, "F" for sensor data
    add_common_json_fields(doc, timestamp, "ltr390", "uvs", uvs);
    serializeJson(doc, packet, sizeof(packet));
    rfm95_send(packet);
  }
  // Sensor packet for ambient light (ALS):
  ltr390.setMode(LTR390_MODE_ALS);
  if (ltr390.newDataAvailable()) {
    float als = ltr390.readALS();
    doc["t"] = "F";            // "t": Type, "F" for sensor data
    add_common_json_fields(doc, timestamp, "ltr390", "als", als);
    serializeJson(doc, packet, sizeof(packet));
    rfm95_send(packet);
  }
  Serial.println(F("[debug]: Exit ltr390_measure_transmit"));
  return true;
}

bool pm25aqi_measure_transmit() {
  Serial.println(F("[debug]: Enter pm25aqi_measure_transmit"));
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping PM25AQI transmit"));
    return false;
  }
  PM25_AQI_Data data;
  if (!pm25aqi.read(&data)) {
    Serial.println("[warn] could not read from AQI");
    return false;
  }
  String timestamp = get_gps_timestamp();
  StaticJsonDocument<96> doc;
  char packet[144];
  const char* measurements[] = {"pm10standard", "pm25standard", "pm100standard", "pm10env", "pm25env", "pm100env",
                                "partcount03um", "partcount05um", "partcount10um", "partcount25um", "partcount50um", "partcount100um"
                               };
  int values[] = {data.pm10_standard, data.pm25_standard, data.pm100_standard, data.pm10_env, data.pm25_env, data.pm100_env,
                  data.particles_03um, data.particles_05um, data.particles_10um, data.particles_25um, data.particles_50um, data.particles_100um
                 };
  for (int i = 0; i < 12; i++) {
    doc["t"] = "F";
    char buff[5];
    const char *measurement = "pm";
    sprintf(buff, "%s%d", measurement, i);
    add_common_json_fields(doc, timestamp, "pmsa003i", buff, values[i]);
    serializeJson(doc, packet);
    rfm95_send(packet);

  }
  return true;

}

String get_gps_timestamp() {
  if (pa1010d_connected)  {
    while (sparkfun_GPS.available()) {
      gps.encode(sparkfun_GPS.read());
    }

    if (gps.time.isValid() && gps.date.isValid()) {
      char buf[25];
      snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02dZ",
               gps.date.year(), gps.date.month(), gps.date.day(),
               gps.time.hour(), gps.time.minute(), gps.time.second());
      gps_timestamp = String(buf);
    }


  }

  return gps_timestamp;
}

bool gps_measure_transmit() {
  Serial.println(F("[debug]: Enter gps_measure_transmit"));
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping GPS transmit"));
    return false;
  }

  if (config.fixed_deployment && (millis() - last_gps_sent < config.gps_fixed_interval)) {
    return false;
  }

  bool has_valid_data = false;
  String gps_module = "default";

  if (pa1010d_connected ) {
    while (sparkfun_GPS.available()) {
      //rp2040.wdt_reset();
      gps.encode(sparkfun_GPS.read());
    }
    if (gps.location.isValid()) {
      latitude = gps.location.lat();
      longitude = gps.location.lng();
      has_valid_data = true;
      gps_module = "pa1010d";
    }

  }

  if (!has_valid_data) {
    Serial.println(F("[info]: Using last recorded GPS coordinates"));
  }


  String timestamp = get_gps_timestamp();
  StaticJsonDocument<96> doc;
  char packet[144];

  // Sensor packet for latitude
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, gps_module.c_str(), "lat", latitude);
  serializeJson(doc, packet, sizeof(packet));
  rfm95_send(packet);


  // Sensor packet for longitude
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, gps_module.c_str(), "lon", longitude);
  serializeJson(doc, packet, sizeof(packet));
  rfm95_send(packet);

  last_gps_sent = millis();
  Serial.println(F("[debug]: Exit gps_measure_transmit"));
  return true;
}


bool scd40_measure_transmit() {
  Serial.println(F("[debug]: Enter scd40_measure_transmit"));
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping SCD40 transmit"));
    return false;
  }
  uint16_t co2;
  float temperature;
  float humidity;
  if (scd40.readMeasurement()) // readMeasurement will return true when fresh data is available
  {
    co2 = scd40.getCO2();
    temperature = scd40.getTemperature();
    humidity = scd40.getHumidity();

  }
  else
    return false;

  String timestamp = get_gps_timestamp();
  StaticJsonDocument<96> doc;
  char packet[144];
  // Sensor packet for CO2:
  doc["t"] = "F";            // "t": Type, "F" for sensor data
  add_common_json_fields(doc, timestamp, "scd40", "CO2", co2);
  serializeJson(doc, packet, sizeof(packet));
  rfm95_send(packet);
  // Sensor packet for temperature:
  doc["t"] = "F";            // "t": Type, "F" for sensor data
  add_common_json_fields(doc, timestamp, "scd40", "tmp", temperature);
  serializeJson(doc, packet, sizeof(packet));
  rfm95_send(packet);
  // Sensor packet for humidity:
  doc["t"] = "F";            // "t": Type, "F" for sensor data
  add_common_json_fields(doc, timestamp, "scd40", "rh", humidity);
  serializeJson(doc, packet, sizeof(packet));
  rfm95_send(packet);
  Serial.println(F("[debug]: Exit scd40_measure_transmit"));
  return true;
}

// Setup
void setup() {
  delay(5000);
  Serial.begin(115200);
  while (!Serial && millis() < 10000);
  Serial.println(F("*** This is IoTwx-LoRa-RP2040 v0.1 ..."));
  Wire.begin();
  //Wire.setTimeout(100);
  rp2040.wdt_begin(15000);
  Serial.println(F("[debug]: Initializing LittleFS"));
  if (!LittleFS.begin()) {
    Serial.println(F("[error]: LittleFS init failed"));
    while (1);
  }
  Serial.println(F("[info]: LittleFS Initialized"));
  if (!load_config()) {
    Serial.println(F("[error]: Config load failed, using defaults"));
    config.overload_threshold = 0.85f;
    config.station_relay_midpoint = 10.0f;
    config.station_relay_steepness = 0.2f;
    config.station_sensor_midpoint = 5.0f;
    config.station_sensor_steepness = 0.5f;
    config.station_relay_weight = 0.7f;
    config.station_sensor_weight = 0.3f;
    config.score_rssi_weight = 0.35f;
    config.score_load_weight = 0.35f;
    config.score_type_weight = 0.2f;
    config.score_relay_weight = 0.1f;
    config.score_relay_decay = 1.0f;
    config.pong_timeout = 12000UL;
    config.keep_alive_interval = 30000UL;
    config.keep_alive_timeout = 60000UL;
    config.latitude = 0.0;
    config.longitude = 0.0;
    latitude = config.latitude;
    longitude = config.longitude;
    config.station_info_interval = 86400000UL;
    config.fixed_deployment = true;
    config.gps_fixed_interval = 43200000UL;
  }
  rfm95_start();
  rfm95_reset();
  rfm95_init();
  Serial.println(F("[debug]: Generating device_id"));
  for (size_t i = 0; i < UniqueIDsize; i++) {
    sprintf(&device_id[i * 2], "%.2X", UniqueID[i]);
  }
  Serial.print(F("[info]: device_id ==> ")); Serial.println(device_id);
  pa1010d_connected = pa1010d_gps_init();
  send_station_info();
  si7021_connected = si7021_init();
  bme680_connected = bme680_init();
  tmp117_connected = tmp117_init();
  ltr390_connected = ltr390_init();
  pm25aqi_connected = pm25aqi_init();
  scd40_connected = scd40_init();
  //send_station_info();
  pinMode(LED_BUILTIN, OUTPUT);
}

// Loop
void loop() {
  rp2040.wdt_reset();
  if (!target_id[0]) {
    //Serial.println(F("[debug]: No target, sending ping"));
    send_ping();
    return;
  }
  static uint32_t last_sensor_transmit = 0;
  if (millis() - last_sensor_transmit < 5000) return;
  last_sensor_transmit = millis();
  rfm95_receive();
  if (target_id[0] && millis() - last_keep_alive_received >= config.keep_alive_timeout) {
    Serial.println(F("[warn]: Keep-alive timeout, clearing target"));
    target_id[0] = '\0';
    has_pi_path = false;
    relay_count = 0;
    send_disconnect();
    return;
  }
  send_keep_alive();
  if (has_pi_path && millis() - last_station_info_sent >= config.station_info_interval) {
    send_station_info();
  }
  update_station_load();
  bool transmit_ok;
  if (si7021_connected) {
    transmit_ok = si7021_measure_transmit();
    if (transmit_ok) blink_led();
  }
  if (bme680_connected) {
    transmit_ok = bme680_measure_transmit();
    if (transmit_ok) blink_led();
  }
  if (tmp117_connected) {
    transmit_ok = tmp117_measure_transmit();
    if (transmit_ok) blink_led();
  }
  if (ltr390_connected) {
    transmit_ok = ltr390_measure_transmit();
    if (transmit_ok) blink_led();
  }
  if (pm25aqi_connected) {
    transmit_ok = pm25aqi_measure_transmit();
    if (transmit_ok) blink_led();
  }
  if (pa1010d_connected) {
    transmit_ok = gps_measure_transmit();
    if (transmit_ok) blink_led();
  }
  if (scd40_connected) {
    transmit_ok = scd40_measure_transmit();
    if (transmit_ok) blink_led();
  }
  //  delay(100);
}