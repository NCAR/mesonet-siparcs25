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
#include <TinyGPSPlus.h>
#include <SparkFun_I2C_GPS_Arduino_Library.h>
#include <SparkFun_SCD4x_Arduino_Library.h>
#include <ArduinoJson.h>
#include <pico/stdlib.h>
#include <pico/multicore.h>
#include <pico/sync.h>
#include <SoftwareSerial.h>
#include <Arduino.h>
#include <LittleFS.h>
#include <math.h>
#include <cstring>
#include <SerialPIO.h>

// --- Constants ---
#define RFM95_CS 16
#define RFM95_INT 21
#define RFM95_RST 17
#define RF95_FREQ 915.0
#define SEALEVELPRESSURE_HPA (1013.25)
#define STATION_INFO_COUNT 3
#define STATION_INFO_DELAY 100
#define BLINK_HIGH_DURATION 500
#define BLINK_LOW_DURATION 500
#define NO_ERROR 0
#undef MAX_PACKET_SIZE
#define MAX_PACKET_SIZE 256
#define RG15_RX_PIN 1
#define RG15_TX_PIN 0
#define CONTINUOUS_TX_DURATION 6000 // 6 seconds for continuous transmission
#define CONTINUOUS_PONG_DELAY_MAX 1500 //1.5 seconds for random pong max delay
#define RG15_ACC_INTERVAL 86400000UL // 24-hour interval for accumulated rainfall reset (in milliseconds)
#define RELAY_QUEUE_SIZE 32
#define PING_MIN_INTERVAL 8000

#define WIND_TX_PIN 24
#define WIND_RX_PIN 25
#define WIND_SLAVE_ADDR 0x01   // confirm against WS302 paperwork if you have it
#define WIND_REG_SPEED 0x0000
#define WIND_REG_DIR   0x0001
#define WIND_BAUD 9600
#define WIND_RESPONSE_TIMEOUT 300

// SEN0600 soil moisture/temperature — Serial1 and Serial2 are already taken
// (RG15, WS302), so this uses SerialPIO on spare Feather pins A0/A1, same
// as the standalone RP2040 test. NOT SEN0601 — this sensor only exposes
// humidity + temperature, no EC/salinity/TDS. See wiki.dfrobot.com/sen0600
#define SOIL_TX_PIN A1
#define SOIL_RX_PIN A0
#define SOIL_SLAVE_ADDR 0x01
#define SOIL_REG_START 0x0000   // reg0 = humidity, reg1 = temperature
#define SOIL_BAUD 9600
#define SOIL_RESPONSE_TIMEOUT 400

// --- MRT (ISO 7726) ---
#define SIGMA 5.670374419e-8f          // Stefan-Boltzmann, W/m2K4
#define MRT_GLOBE_DIAMETER_M 0.038f    // OpenIoTwx 3.8cm globe (update if globe changes)
#define MRT_GLOBE_EMISSIVITY 0.95f



// --- State Enum ---
enum SystemState {
  IDLE,
  SENDING_PONG,
  SENDING_STATION_INFO,
  SENDING_CONTINUOUS_PONG
};

// --- Hardware Objects ---
RH_RF95 rf95(RFM95_CS, RFM95_INT);
Adafruit_Si7021 si7021;
Adafruit_BME680 bme680_1;  // 0x77 default
Adafruit_BME680 bme680_2;  // 0x76 soldered
Adafruit_TMP117 tmp117;
Adafruit_GPS pa1010d(&Wire);
I2CGPS sparkfun_GPS;
Adafruit_LTR390 ltr390;
Adafruit_PM25AQI pm25aqi;
TinyGPSPlus gps;
SCD4x scd40;
SoftwareSerial rg15Serial(RG15_RX_PIN, RG15_TX_PIN);
SerialPIO soilSerial(SOIL_TX_PIN, SOIL_RX_PIN);

// --- RG15 Rain Sensor ---
bool rg15_connected = false;

// --- Wind Sensor ---
bool wind_connected = false;
float last_wind_speed_ms = 0.0f;
bool last_wind_speed_valid = false;

// --- Soil Sensor ---
bool soil_connected = false;
float last_soil_moisture_pct = 0.0f;
float last_soil_temp_c = 0.0f;
bool last_soil_valid = false;

// --- Configuration and State ---
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
  uint32_t connect_timeout;
  float latitude;
  float longitude;
  float altitude;
  uint32_t station_info_interval;
  bool fixed_deployment;
  uint32_t gps_fixed_interval;
  uint32_t sensor_transmit_delay;
  char firstname[48];
  char lastname[48];
  char email[64];
  char organization[64];
  char device[64];
} config;

struct Dependent {
  char id[17];
};

struct Pong {
  char id[17];
  char type[3];
  float load;
  int8_t rssi;
  uint8_t relay_count;
};

// TX queue: Core 0 → Core 1
char tx_packet_queue[RELAY_QUEUE_SIZE][MAX_PACKET_SIZE];
uint8_t tx_packet_lengths[RELAY_QUEUE_SIZE];
volatile uint8_t tx_queue_head = 0;
volatile uint8_t tx_queue_tail = 0;
mutex_t tx_queue_mutex;

// --- Global Variables ---
uint32_t last_ping_attempt = 0;
char device_id[17] = {0};
char target_id[17] = {0};
bool has_pi_path = false;
bool can_ping = true;
bool can_select = false;
bool can_transmit = true;
uint8_t relay_count = 0;
uint8_t target_relay_count = 0;
uint32_t last_broadcast = 0;
uint32_t last_connect = 0;
uint32_t last_sensor_transmit = 0;
bool waiting_for_pongs = false;
uint32_t pong_start_time = 0;
uint32_t last_station_info_sent = 0;
uint32_t last_gps_sent = 0;
uint8_t active_sensors = 0;
uint8_t active_relays = 0;
uint32_t last_load_update = 0;
float station_load = 0.0;
bool si7021_connected = false;
bool bme680_1_connected = false;
bool bme680_2_connected = false;
bool bme680_1_fresh = false;   // true only if performReading() succeeded THIS cycle
bool bme680_2_fresh = false;   // true only if performReading() succeeded THIS cycle
bool tmp117_connected = false;
bool ltr390_connected = false;
bool pm25aqi_connected = false;
bool pa1010d_connected = false;
bool gps_connected = false;
bool scd40_connected = false;
String gps_module;
double latitude;
double longitude;
double altitude;
Dependent dependents[20];
uint8_t dependent_count = 0;
Pong pongs[20];
uint8_t pong_count = 0;
bool led_state = false;
SystemState current_state = IDLE;
uint8_t pong_index = 0;
uint32_t last_packet_time = 0;
uint32_t last_blink_time = 0;
uint8_t station_info_index = 0;
uint32_t continuous_pong_start = 0;
uint32_t last_rg15_acc_reset = -RG15_ACC_INTERVAL - 1; // Track last reset time for RG15 accumulated rainfall
float rg15_acc_mm = 0.0;
float rg15_event_acc_mm = 0.0;
float rg15_total_acc_mm = 0.0;
float rg15_r_int_mm = 0.0;
bool rg15_data_valid = false;
char relay_packet_queue[RELAY_QUEUE_SIZE][MAX_PACKET_SIZE];
uint8_t relay_packet_lengths[RELAY_QUEUE_SIZE];
volatile uint8_t relay_queue_head = 0;
volatile uint8_t relay_queue_tail = 0;
mutex_t relay_queue_mutex;

// --- Threading and Synchronization ---
mutex_t state_mutex;
mutex_t radio_mutex;

// --- Mutex Functions ---
void mutex_safe_update_pong(const char* station_id, const char* type, float load, int8_t rssi, uint8_t relay_count) {
  mutex_enter_blocking(&state_mutex);

  // Check for existing pong with the same station_id
  for (uint8_t i = 0; i < pong_count; i++) {
    if (strcmp(pongs[i].id, station_id) == 0) {
      // Update existing pong
      strlcpy(pongs[i].type, type, sizeof(pongs[i].type));
      pongs[i].load = load;
      pongs[i].rssi = rssi;
      pongs[i].relay_count = relay_count;
      Serial.print(F("[info]: Updated existing pong for station_id: "));
      Serial.println(station_id);
      mutex_exit(&state_mutex);
      return;
    }
  }

  // Add new pong if there's space
  if (pong_count < sizeof(pongs) / sizeof(pongs[0])) {
    strlcpy(pongs[pong_count].id, station_id, sizeof(pongs[0].id));
    strlcpy(pongs[pong_count].type, type, sizeof(pongs[0].type));
    pongs[pong_count].load = load;
    pongs[pong_count].rssi = rssi;
    pongs[pong_count].relay_count = relay_count;
    pong_count++;
    Serial.print(F("[info]: Added new pong for station_id: "));
    Serial.println(station_id);
  } else {
    Serial.println(F("[warn]: Pong array full, cannot add new pong"));
  }

  mutex_exit(&state_mutex);
}

void mutex_safe_update_target(const char* new_target, bool new_has_pi_path, uint8_t new_relay_count) {
  mutex_enter_blocking(&state_mutex);
  strlcpy(target_id, new_target, sizeof(target_id));
  has_pi_path = new_has_pi_path;
  relay_count = new_relay_count;
  last_connect = millis();
  mutex_exit(&state_mutex);
}

void mutex_safe_clear_target() {
  mutex_enter_blocking(&state_mutex);
  target_id[0] = '\0';
  has_pi_path = false;
  relay_count = 0;
  mutex_exit(&state_mutex);
}

bool mutex_safe_get_waiting_for_pongs() {
  mutex_enter_blocking(&state_mutex);
  bool value = waiting_for_pongs;
  mutex_exit(&state_mutex);
  return value;
}

void mutex_safe_set_waiting_for_pongs(bool value) {
  mutex_enter_blocking(&state_mutex);
  waiting_for_pongs = value;
  mutex_exit(&state_mutex);
}

// --- Utility Functions ---
void start_blink_led() {
  mutex_enter_blocking(&state_mutex);
  current_state = IDLE;
  digitalWrite(LED_BUILTIN, HIGH);
  led_state = true;
  last_blink_time = millis();
  mutex_exit(&state_mutex);
}

void handle_blink_led() {
  mutex_enter_blocking(&state_mutex);
  if (current_state != IDLE) {
    mutex_exit(&state_mutex);
    return;
  }
  uint32_t current_time = millis();
  if (led_state && current_time - last_blink_time >= BLINK_HIGH_DURATION) {
    digitalWrite(LED_BUILTIN, LOW);
    led_state = false;
    last_blink_time = current_time;
  }
  // removed the else-if that caused the double exit
  mutex_exit(&state_mutex);
}

String get_gps_timestamp() {
  if (!pa1010d_connected || strcmp(gps_module.c_str(), "pa1010d")) return String();
  while (sparkfun_GPS.available()) {
    gps.encode(sparkfun_GPS.read());
  }
  if (gps.time.isValid() && gps.date.isValid()) {
    char buf[25];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02dZ",
             gps.date.year(), gps.date.month(), gps.date.day(),
             gps.time.hour(), gps.time.minute(), gps.time.second());
    return String(buf);
  }
  return String();
}

void update_station_load() {
  if (millis() - last_load_update < 30000) return;
  Serial.println(F("[debug]: Updating station load"));
  float sensor_load = 1.0 / (1.0 + exp(-config.station_sensor_steepness * (active_sensors - config.station_sensor_midpoint)));
  float relay_load = 1.0 / (1.0 + exp(-config.station_relay_steepness * (active_relays - config.station_relay_midpoint)));
  station_load = config.station_relay_weight * relay_load + config.station_sensor_weight * sensor_load;
  active_relays = 0;
  last_load_update = millis();
  Serial.print(F("[info]: Connected sensors: "));
  if (si7021_connected) Serial.print(F("Si7021 "));
  if (bme680_1_connected) Serial.print(F("BME680_1 "));
  if (bme680_2_connected) Serial.print(F("BME680_2 "));
  if (tmp117_connected) Serial.print(F("TMP117 "));
  if (ltr390_connected) Serial.print(F("LTR390 "));
  if (pm25aqi_connected) Serial.print(F("PM25AQI "));
  if (scd40_connected) Serial.print(F("SCD40 "));
  if (rg15_connected) Serial.print(F("RG15 "));
  if (pa1010d_connected) Serial.print(F("PA1010D "));
  if (active_sensors == 0) Serial.print(F("None"));
  Serial.println();
  Serial.print(F("[info]: Station load: ")); Serial.print(station_load);
  Serial.print(F(" (Relay Load: ")); Serial.print(relay_load);
  Serial.print(F(", Sensor Load: ")); Serial.print(sensor_load);
  Serial.print(F(", Active Sensors: ")); Serial.print(active_sensors); Serial.println(F(")"));
}

bool load_config() {
  Serial.println(F("[debug]: Loading /config.json"));
  File file = LittleFS.open("/config.json", "r");
  if (!file) {
    Serial.println(F("[warn]: Failed to open /config.json, using hardcoded defaults"));
  } else {
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, file);
    file.close();
    if (error) {
      Serial.print(F("[warn]: JSON parse failed: ")); Serial.println(error.c_str());
      Serial.println(F("[warn]: Falling back to hardcoded defaults"));
    } else {
      config.overload_threshold       = doc["radio"]["overload_threshold"]       | 0.85f;
      config.station_relay_midpoint   = doc["radio"]["station_relay_midpoint"]   | 10.0f;
      config.station_relay_steepness  = doc["radio"]["station_relay_steepness"]  | 0.2f;
      config.station_sensor_midpoint  = doc["radio"]["station_sensor_midpoint"]  | 5.0f;
      config.station_sensor_steepness = doc["radio"]["station_sensor_steepness"] | 0.5f;
      config.station_relay_weight     = doc["radio"]["station_relay_weight"]     | 0.7f;
      config.station_sensor_weight    = doc["radio"]["station_sensor_weight"]    | 0.3f;
      config.score_rssi_weight        = doc["radio"]["score_rssi_weight"]        | 0.35f;
      config.score_load_weight        = doc["radio"]["score_load_weight"]        | 0.35f;
      config.score_type_weight        = doc["radio"]["score_type_weight"]        | 0.2f;
      config.score_relay_weight       = doc["radio"]["score_relay_weight"]       | 0.1f;
      config.score_relay_decay        = doc["radio"]["score_relay_decay"]        | 1.0f;
      config.pong_timeout             = doc["radio"]["pong_timeout"]             | 5000UL;
      config.connect_timeout          = doc["radio"]["connect_timeout"]          | 900000UL;
      config.latitude                 = doc["station_info"]["latitude"]          | 0.0;
      config.longitude                = doc["station_info"]["longitude"]         | 0.0;
      config.altitude                 = doc["station_info"]["altitude"]          | 0.0;
      strlcpy(config.firstname,    doc["station_info"]["firstname"]    | "",  sizeof(config.firstname));
      strlcpy(config.lastname,     doc["station_info"]["lastname"]     | "",  sizeof(config.lastname));
      strlcpy(config.email,        doc["station_info"]["email"]        | "",  sizeof(config.email));
      strlcpy(config.organization, doc["station_info"]["organization"] | "",  sizeof(config.organization));
      strlcpy(config.device,       doc["station_info"]["device"]       | "",  sizeof(config.device));
      config.station_info_interval    = doc["station_info"]["station_info_interval"]  | 86400000UL;
      config.fixed_deployment         = doc["station_info"]["fixed_deployment"]       | false;
      config.sensor_transmit_delay    = doc["station_info"]["sensor_transmit_delay"]  | 60000UL;
      config.gps_fixed_interval       = doc["station_info"]["gps_fixed_interval"]     | 43200000UL;
      latitude  = config.latitude;
      longitude = config.longitude;
      altitude  = config.altitude;
      Serial.println(F("[info]: Loaded /config.json"));
      return true;
    }
  }

  // Hardcoded defaults — used when config.json is missing or unreadable
  config.overload_threshold       = 0.85f;
  config.station_relay_midpoint   = 10.0f;
  config.station_relay_steepness  = 0.2f;
  config.station_sensor_midpoint  = 5.0f;
  config.station_sensor_steepness = 0.5f;
  config.station_relay_weight     = 0.7f;
  config.station_sensor_weight    = 0.3f;
  config.score_rssi_weight        = 0.35f;
  config.score_load_weight        = 0.35f;
  config.score_type_weight        = 0.2f;
  config.score_relay_weight       = 0.1f;
  config.score_relay_decay        = 1.0f;
  config.pong_timeout             = 5000UL;
  config.connect_timeout          = 900000UL;  // 15 min — critical, was 60s
  config.latitude                 = 0.0;
  config.longitude                = 0.0;
  config.altitude                 = 0.0;
  config.station_info_interval    = 86400000UL;
  config.fixed_deployment         = false;
  config.gps_fixed_interval       = 43200000UL;
  config.sensor_transmit_delay    = 60000UL;
  
  const char fn_ph[] = {'I','O','T','W','X','F','N','A','M','E',
                        '0','0','0','0','0','0','0','0','0','0',
                        '0','0','0','0','0','0','0','0','0','0','0','0','\0'};
  memcpy(config.firstname, fn_ph, sizeof(fn_ph));

  const char ln_ph[] = {'I','O','T','W','X','L','N','A','M','E',
                        '1','2','3','4','5','6','7','8','9','0',
                        'a','b','c','d','e','f','g','h','i','j','k','l','\0'};
  memcpy(config.lastname, ln_ph, sizeof(ln_ph));

  const char em_ph[] = {'I','O','T','W','X','E','M','A','I','L',
                        '2','3','4','5','6','7','8','9','0','a',
                        'b','c','d','e','f','g','h','i','j','k',
                        'l','m','n','o','p','q','r','s','t','u',
                        'v','w','x','y','z','A','B','\0'};
  memcpy(config.email, em_ph, sizeof(em_ph));
  const char or_ph[] = {'I','O','T','W','X','O','R','G','S',
                        '3','4','5','6','7','8','9','0','a','b',
                        'c','d','e','f','g','h','i','j','k','l',
                        'm','n','o','p','q','r','s','t','u','v',
                        'w','x','y','z','A','B','C','D','E','\0'};
  memcpy(config.organization, or_ph, sizeof(or_ph));

  strlcpy(config.device,       "adafruit RP2040 RFM95 LoRa",                        sizeof(config.device));
  latitude  = config.latitude;
  longitude = config.longitude;
  altitude  = config.altitude;
  Serial.println(F("[info]: Using hardcoded defaults"));
  return true;  // always return true — board works either way
}

void add_dependent(const char* station_id) {
  mutex_enter_blocking(&state_mutex);
  Serial.print(F("[debug]: Attempting to add dependent: ")); Serial.println(station_id);
  for (uint8_t i = 0; i < dependent_count; i++) {
    if (!strcmp(dependents[i].id, station_id)) {
      Serial.println(F("[info]: Already a dependent"));
      mutex_exit(&state_mutex);
      return;
    }
  }
  if (dependent_count < sizeof(dependents) / sizeof(dependents[0])) {
    strlcpy(dependents[dependent_count].id, station_id, sizeof(dependents[0].id));
    dependent_count++;
    Serial.print(F("[info]: Added dependent: ")); Serial.println(station_id);
  } else {
    Serial.println(F("[warn]: Dependent list full, cannot add"));
  }
  mutex_exit(&state_mutex);
}

void add_common_json_fields(JsonDocument& doc, const String& timestamp, const char* sensor, const char* measurement, float data, const char* protocol) {
  doc["sid"] = device_id;
  if (!timestamp.isEmpty()) doc["ts"] = timestamp;
  doc["s"] = sensor;
  doc["m"] = measurement;
  doc["d"] = data;
  doc["p"] = protocol;
  doc["to"] = target_id;
  mutex_enter_blocking(&state_mutex);
  mutex_exit(&state_mutex);
}

// --- Network Communication ---
void start_ping() {
  Serial.println(F("[debug]: Enter start_ping"));
  JsonDocument doc;
  char packet[64];
  doc["sid"] = device_id;
  doc["t"] = "A";
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: Ping packet buffer overflow"));
    return;
  }
  mutex_safe_set_waiting_for_pongs(true);
  mutex_enter_blocking(&state_mutex);
  can_ping = false;
  pong_count = 0;
  mutex_exit(&state_mutex);
  rfm95_send(packet);
  mutex_enter_blocking(&state_mutex);
  pong_start_time = millis();
  last_ping_attempt = millis();
  can_select = true;
  mutex_exit(&state_mutex);
  Serial.println(F("[info]: Sent ping, waiting for pongs"));
}

void handle_continuous_pong() {
  mutex_enter_blocking(&state_mutex);
  if (current_state != SENDING_CONTINUOUS_PONG) {
    mutex_exit(&state_mutex);
    return;
  }
  if (millis() - continuous_pong_start >= CONTINUOUS_TX_DURATION) {
    Serial.println(F("[info]: Completed continuous pong transmission"));
    pong_index = 0;
    current_state = IDLE;
    last_packet_time = millis();
    mutex_exit(&state_mutex);
    return;
  }
  if (!target_id[0]) {
    mutex_exit(&state_mutex);
    return;
  }
  // Add random initial delay
  static bool initial_delay_done = false;
  static uint32_t initial_delay_ms = 0;
  if (!initial_delay_done) {
    initial_delay_ms = random(0, (uint32_t)(CONTINUOUS_PONG_DELAY_MAX));
    Serial.print(F("[info]: Delaying continuous pong by ")); Serial.print(initial_delay_ms); Serial.println(F(" ms"));
    delay(initial_delay_ms);
    initial_delay_done = true;
  }
  JsonDocument pong_doc;
  char packet[128];
  pong_doc["sid"] = device_id;
  pong_doc["t"] = "B";
  pong_doc["ty"] = "2";
  pong_doc["l"] = station_load;
  pong_doc["rssi"] = rf95.lastRssi();
  pong_doc["rc"] = relay_count;
  pong_doc["tar"] = target_id;
  if (serializeJson(pong_doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: Continuous pong packet buffer overflow"));
    mutex_exit(&state_mutex);
    return;
  }
  mutex_exit(&state_mutex);
  rfm95_send(packet);
  Serial.print(F("[info]: Sent continuous pong at ")); Serial.print(millis() - continuous_pong_start); Serial.println(F(" ms"));
  mutex_enter_blocking(&state_mutex);
  last_packet_time = millis();
  mutex_exit(&state_mutex);
}


void start_continuous_pong() {
  mutex_enter_blocking(&state_mutex);
  if (current_state != IDLE && current_state != SENDING_CONTINUOUS_PONG) {
    Serial.println(F("[info]: Cannot start continuous pong (wrong state)"));
    mutex_exit(&state_mutex);
    return;
  }
  if (station_load > config.overload_threshold || !has_pi_path) {
    Serial.println(F("[info]: Cannot start continuous pong (load or no Pi path)"));
    mutex_exit(&state_mutex);
    return;
  }
  Serial.println(F("[debug]: Starting/Extending continuous pong for 6 seconds"));
  current_state = SENDING_CONTINUOUS_PONG;
  continuous_pong_start = millis();
  last_packet_time = millis();
  mutex_exit(&state_mutex);
}

void handle_station_info() {
  mutex_enter_blocking(&state_mutex);
  if (current_state != SENDING_STATION_INFO) {
    mutex_exit(&state_mutex);
    return;
  }
  if (millis() - last_station_info_sent >= CONTINUOUS_TX_DURATION) {
    Serial.println(F("[info]: Completed continuous station_info transmission"));
    can_transmit = true;
    current_state = IDLE;
    last_packet_time = millis();
    mutex_exit(&state_mutex);
    return;
  }
  mutex_exit(&state_mutex);

  JsonDocument doc;
  char packet[256];
  mutex_enter_blocking(&state_mutex);
  doc["sid"] = device_id;
  doc["t"]   = "E";
  char fn_buf[24], ln_buf[24], em_buf[32], or_buf[24];
  strncpy(fn_buf, config.firstname,    23); fn_buf[23] = '\0';
  strncpy(ln_buf, config.lastname,     23); ln_buf[23] = '\0';
  strncpy(em_buf, config.email,        31); em_buf[31] = '\0';
  strncpy(or_buf, config.organization, 23); or_buf[23] = '\0';
  doc["fn"] = fn_buf;
  doc["ln"] = ln_buf;
  doc["e"]  = em_buf;
  doc["o"]  = or_buf;
  doc["de"] = config.device;
  doc["lat"] = latitude;
  doc["lon"] = longitude;
  doc["al"]  = altitude;
  doc["to"]  = target_id;
  String gps_timestamp = get_gps_timestamp();
  if (!gps_timestamp.isEmpty()) doc["ts"] = gps_timestamp;
  mutex_exit(&state_mutex);

  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: Station info packet buffer overflow"));
    mutex_enter_blocking(&state_mutex);
    current_state = IDLE;
    can_transmit = true;
    last_packet_time = millis();
    mutex_exit(&state_mutex);
    return;
  }
  rfm95_send(packet);
  Serial.print(F("[info]: Sent continuous station_info at "));
  Serial.print(millis() - last_station_info_sent);
  Serial.println(F(" ms"));
  mutex_enter_blocking(&state_mutex);
  last_packet_time = millis();
  mutex_exit(&state_mutex);
}

bool start_station_info() {
  mutex_enter_blocking(&state_mutex);
  if (current_state != IDLE || !target_id[0]) {
    mutex_exit(&state_mutex);
    return false;
  }
  current_state = SENDING_STATION_INFO;
  last_station_info_sent = millis();
  can_transmit = false;
  mutex_exit(&state_mutex);
  Serial.println(F("[debug]: Starting continuous station_info transmission for 6 seconds"));
  return true;
}
void send_disconnect() {
  mutex_enter_blocking(&state_mutex);
  Serial.println(F("[debug]: Sending disconnect to dependents"));
  JsonDocument doc;
  char packet[48];
  for (uint8_t i = 0; i < dependent_count; i++) {
    doc["sid"] = device_id;
    doc["t"] = "D";
    doc["to"] = dependents[i].id;
    if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
      Serial.println(F("[error]: Disconnect packet buffer overflow"));
      continue;
    }
    mutex_exit(&state_mutex);
    rfm95_send(packet);
    mutex_enter_blocking(&state_mutex);
    Serial.print(F("[info]: Sent disconnect to ")); Serial.println(dependents[i].id);
  }
  dependent_count = 0;
  mutex_exit(&state_mutex);
}

void select_best_target() {
  mutex_enter_blocking(&state_mutex);
  Serial.println(F("[debug]: Selecting best target"));
  float best_pi_score = -1.0;
  char best_pi_id[17] = {0};
  uint8_t best_pi_relay_count = 255;
  float best_station_score = -1.0;
  char best_station_id[17] = {0};
  uint8_t best_station_relay_count = 255;
  uint8_t min_pi_relay_count = 255;
  uint8_t min_station_relay_count = 255;

  // Find minimum relay counts for Pi and station
  for (uint8_t i = 0; i < pong_count; i++) {
    if (strcmp(pongs[i].type, "1") == 0) {
      min_pi_relay_count = min(min_pi_relay_count, pongs[i].relay_count);
    } else {
      min_station_relay_count = min(min_station_relay_count, pongs[i].relay_count);
    }
  }

  // Evaluate pongs with minimum relay counts
  for (uint8_t i = 0; i < pong_count; i++) {
    if (strcmp(pongs[i].type, "1") == 0 && pongs[i].relay_count > min_pi_relay_count) continue;
    if (strcmp(pongs[i].type, "2") == 0 && pongs[i].relay_count > min_station_relay_count) continue;

    float norm_rssi = (pongs[i].rssi + 120.0f) / 70.0;
    norm_rssi = constrain(norm_rssi, 0.0, 1.0);
    float type_bonus = (strcmp(pongs[i].type, "1") == 0) ? 1.0 : 0.0;
    float relay_penalty = exp(-config.score_relay_decay * pongs[i].relay_count);
    float score = config.score_rssi_weight * norm_rssi +
                  config.score_load_weight * (1.0 - pongs[i].load) +
                  config.score_type_weight * type_bonus +
                  config.score_relay_weight * relay_penalty;

    Serial.print(F("[info]: Pong from ")); Serial.print(pongs[i].id);
    Serial.print(F(" (")); Serial.print(pongs[i].type); Serial.print(F(")"));
    Serial.print(F(", RSSI: ")); Serial.print(pongs[i].rssi);
    Serial.print(F(", Load: ")); Serial.print(pongs[i].load);
    Serial.print(F(", Relay Count: ")); Serial.print(pongs[i].relay_count);
    Serial.print(F(", Score: ")); Serial.println(score);

    if (strcmp(pongs[i].type, "1") == 0) {
      if (score > best_pi_score && pongs[i].relay_count == min_pi_relay_count) {
        best_pi_score = score;
        strlcpy(best_pi_id, pongs[i].id, sizeof(best_pi_id));
        best_pi_relay_count = pongs[i].relay_count;
      }
    } else {
      if (score > best_station_score && pongs[i].relay_count == min_station_relay_count) {
        best_station_score = score;
        strlcpy(best_station_id, pongs[i].id, sizeof(best_station_id));
        best_station_relay_count = pongs[i].relay_count;
      }
    }
  }

  // Choose the best Pi if available; otherwise, choose the best station
  bool target_changed = false;
  if (best_pi_id[0]) { // Pi available
    target_changed = strcmp(target_id, best_pi_id) != 0;
    strlcpy(target_id, best_pi_id, sizeof(target_id));
    has_pi_path = true;
    target_relay_count = best_pi_relay_count;
    relay_count = best_pi_relay_count + 1;
    Serial.print(F("[info]: Selected Pi target: ")); Serial.print(target_id);
    Serial.print(F(", Relay Count: ")); Serial.print(relay_count); Serial.println(F(")"));
  } else if (best_station_id[0]) { // No Pi, fall back to station
    target_changed = strcmp(target_id, best_station_id) != 0;
    strlcpy(target_id, best_station_id, sizeof(target_id));
    has_pi_path = true; // Stations can still have a path to Pi
    target_relay_count = best_station_relay_count;
    relay_count = best_station_relay_count + 1;
    Serial.print(F("[info]: Selected station target: ")); Serial.print(target_id);
    Serial.print(F(", Relay Count: ")); Serial.print(relay_count); Serial.println(F(")"));
  } else {
    target_id[0] = '\0';
    has_pi_path = false;
    relay_count = 0;
    mutex_exit(&state_mutex);
    send_disconnect();
    Serial.println(F("[warn]: No valid target selected"));
    return;
  }

  if (target_changed) {
    station_info_index = 0;
    last_connect = millis();
    last_station_info_sent = millis() - config.station_info_interval - 1;
    last_sensor_transmit = -config.sensor_transmit_delay - 1;
    mutex_exit(&state_mutex);
    start_station_info();
  } else {
    mutex_exit(&state_mutex);
  }

  mutex_enter_blocking(&state_mutex);
  can_ping = true;
  can_select = false;
  mutex_exit(&state_mutex);
}

// --- RFM95 Radio Functions ---
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
  //rf95.setPreambleLength(6);
  //Serial.println(F("[info]: RFM95 configured: BW=125kHz, CR=4/5, SF=7, Preamble=6"));
  return true;
}


uint16_t modbus_crc16(const uint8_t* buf, int len) {
  uint16_t crc = 0xFFFF;
  for (int pos = 0; pos < len; pos++) {
    crc ^= (uint16_t)buf[pos];
    for (int i = 0; i < 8; i++) {
      if (crc & 0x0001) {
        crc >>= 1;
        crc ^= 0xA001;
      } else {
        crc >>= 1;
      }
    }
  }
  return crc;
}

// Reads `count` holding registers starting at start_reg. Returns true on success.
bool wind_query_registers(uint16_t start_reg, uint16_t count, uint16_t* out_values) {
  uint8_t request[8];
  request[0] = WIND_SLAVE_ADDR;
  request[1] = 0x03;
  request[2] = (start_reg >> 8) & 0xFF;
  request[3] = start_reg & 0xFF;
  request[4] = (count >> 8) & 0xFF;
  request[5] = count & 0xFF;
  uint16_t crc = modbus_crc16(request, 6);
  request[6] = crc & 0xFF;
  request[7] = (crc >> 8) & 0xFF;

  while (Serial2.available()) Serial2.read(); // flush stale bytes

  Serial2.write(request, 8);
  Serial2.flush();

  uint8_t expected_len = 5 + count * 2; // addr+func+bytecount+data+crc
  uint8_t response[64];
  uint8_t idx = 0;
  uint32_t start_time = millis();
  while (millis() - start_time < WIND_RESPONSE_TIMEOUT && idx < expected_len) {
    if (Serial2.available()) {
      response[idx++] = Serial2.read();
    }
  }

  if (idx < expected_len) {
    Serial.print(F("[warn]: WS302 response too short, got ")); Serial.println(idx);
    return false;
  }

  uint16_t recv_crc = response[idx - 2] | (response[idx - 1] << 8);
  uint16_t calc_crc = modbus_crc16(response, idx - 2);
  if (recv_crc != calc_crc) {
    Serial.println(F("[warn]: WS302 CRC mismatch"));
    return false;
  }
  if (response[0] != WIND_SLAVE_ADDR || response[1] != 0x03) {
    Serial.println(F("[warn]: WS302 unexpected slave/function in response"));
    return false;
  }

  for (int i = 0; i < count; i++) {
    out_values[i] = (response[3 + i * 2] << 8) | response[4 + i * 2];
  }
  return true;
}


// Reads `count` holding registers starting at start_reg from the SEN0600.
bool soil_query_registers(uint16_t start_reg, uint16_t count, uint16_t* out_values) {
  uint8_t request[8];
  request[0] = SOIL_SLAVE_ADDR;
  request[1] = 0x03;
  request[2] = (start_reg >> 8) & 0xFF;
  request[3] = start_reg & 0xFF;
  request[4] = (count >> 8) & 0xFF;
  request[5] = count & 0xFF;
  uint16_t crc = modbus_crc16(request, 6);
  request[6] = crc & 0xFF;
  request[7] = (crc >> 8) & 0xFF;

  while (soilSerial.available()) soilSerial.read(); // flush stale bytes

  soilSerial.write(request, 8);
  soilSerial.flush();

  uint8_t expected_len = 5 + count * 2; // addr+func+bytecount+data+crc
  uint8_t response[32];
  uint8_t idx = 0;
  uint32_t start_time = millis();
  while (millis() - start_time < SOIL_RESPONSE_TIMEOUT && idx < expected_len) {
    if (soilSerial.available()) {
      response[idx++] = soilSerial.read();
    }
  }

  if (idx < expected_len) {
    Serial.print(F("[warn]: SEN0600 response too short, got ")); Serial.println(idx);
    return false;
  }

  uint16_t recv_crc = response[idx - 2] | (response[idx - 1] << 8);
  uint16_t calc_crc = modbus_crc16(response, idx - 2);
  if (recv_crc != calc_crc) {
    Serial.println(F("[warn]: SEN0600 CRC mismatch"));
    return false;
  }
  if (response[0] != SOIL_SLAVE_ADDR || response[1] != 0x03) {
    Serial.println(F("[warn]: SEN0600 unexpected slave/function in response"));
    return false;
  }

  for (int i = 0; i < count; i++) {
    out_values[i] = (response[3 + i * 2] << 8) | response[4 + i * 2];
  }
  return true;
}


void rfm95_send(const char* packet) {
  uint8_t len = strlen(packet) + 1;
  if (len > MAX_PACKET_SIZE) {
    Serial.println(F("[error]: Packet too large for FIFO"));
    return;
  }
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, packet);
  if (error) {
    Serial.print(F("[error]: Invalid JSON packet: ")); Serial.println(packet);
    return;
  }
  Serial.print(F("[debug]: Preparing to send packet: ")); Serial.println(packet);

  if (get_core_num() == 0) {
    mutex_enter_blocking(&tx_queue_mutex);
    if ((tx_queue_head + 1) % RELAY_QUEUE_SIZE == tx_queue_tail) {
        Serial.println(F("[error]: TX queue full, dropping packet"));
        mutex_exit(&tx_queue_mutex);
        return;
    }
    strlcpy(tx_packet_queue[tx_queue_head], packet, MAX_PACKET_SIZE);
    tx_packet_lengths[tx_queue_head] = len;
    tx_queue_head = (tx_queue_head + 1) % RELAY_QUEUE_SIZE;
    mutex_exit(&tx_queue_mutex);
  } else {
    // Core 1: send directly — FIFO goes the wrong direction from here
    mutex_enter_blocking(&radio_mutex);
    if (!rf95.send((uint8_t*)packet, len - 1)) {
      Serial.println(F("[error]: rf95.send failed (direct)"));
    } else if (!rf95.waitPacketSent()) {
      Serial.println(F("[error]: rf95.waitPacketSent timed out (direct)"));
    } else {
      Serial.print(F("[debug]: Packet sent directly, length: ")); Serial.println(len - 1);
    }
    mutex_exit(&radio_mutex);
  }
}

void core1_entry() {
  while (true) {
    rp2040.wdt_reset();

    if (rf95.available()) {
      mutex_enter_blocking(&radio_mutex);
      uint8_t buf[255];
      uint8_t len = sizeof(buf);
      int8_t rssi = rf95.lastRssi();
      if (rf95.recv(buf, &len)) {
        buf[len] = '\0';
        Serial.print(F("[info]: Core1 Received packet >> ")); Serial.println((char*)buf);
        JsonDocument doc;
        DeserializationError error = deserializeJson(doc, (char*)buf);
        if (error) {
          Serial.print(F("[error]: JSON deserialization failed: ")); Serial.println(error.c_str());
          mutex_exit(&radio_mutex);
          continue;
        }
        const char* station_id = doc["sid"] | "";
        if (!station_id[0] || !strcmp(station_id, device_id)) {
          Serial.print(F("[error]: Invalid station_id: ")); Serial.println(station_id);
          mutex_exit(&radio_mutex);
          continue;
        }
        if (doc["t"] == "A") {
          update_station_load();
          mutex_enter_blocking(&state_mutex);
          if (station_load > config.overload_threshold) {
            Serial.println(F("[warn]: Load too high, refusing pong response"));
            mutex_exit(&state_mutex);
            mutex_exit(&radio_mutex);
            continue;
          }
          if (!has_pi_path) {
            Serial.println(F("[info]: No Pi path, skipping pong response"));
            mutex_exit(&state_mutex);
            mutex_exit(&radio_mutex);
            continue;
          }
          current_state = SENDING_CONTINUOUS_PONG;
          continuous_pong_start = millis();
          last_packet_time = millis();
          mutex_exit(&state_mutex);
          mutex_exit(&radio_mutex);  // release BEFORE calling rfm95_send indirectly
          handle_continuous_pong();
          continue;  // skip the mutex_exit(&radio_mutex) at the bottom of the block
          //only receive pong if the end target is not this station(to avoid infinite send loop between two stations)
        } else if (doc["t"] == "B" && !strcmp(doc["tar"] | "", device_id) && mutex_safe_get_waiting_for_pongs()) {
          mutex_safe_update_pong(station_id, doc["ty"] | "2", doc["l"] | 0.0f, doc["rssi"] | 0, doc["rc"] | 0);
          Serial.println(F("[info]: Stored pong"));
        } else if (doc["t"] == "D" && !strcmp(doc["to"] | "", device_id)) {
          mutex_safe_clear_target();
          send_disconnect();
          Serial.println(F("[info]: Received disconnect, cleared target and sent disconnect to dependents"));
          start_ping();
        } else if (doc["t"] == "E") {
          Serial.print(F("[debug]: Received type E packet, to: ")); Serial.print(doc["to"] | "None");
          Serial.print(F(", device_id: ")); Serial.println(device_id);
          if (!strcmp(doc["to"] | "", device_id)) add_dependent(station_id);
          mutex_enter_blocking(&state_mutex);
          Serial.print(F("[debug]: target_id: ")); Serial.println(target_id[0] ? target_id : "None");
          Serial.print(F("[debug]: station_load: ")); Serial.print(station_load);
          Serial.print(F(", overload_threshold: ")); Serial.println(config.overload_threshold);
          if (target_id[0] && station_load <= config.overload_threshold) {
            doc["to"] = target_id;
            char packet[255];
            size_t serialized_len = serializeJson(doc, packet, sizeof(packet));
            if (serialized_len >= sizeof(packet)) {
              mutex_exit(&state_mutex);
              Serial.println(F("[error]: Relay packet buffer overflow for type E"));
            } else {
              mutex_exit(&state_mutex);
              Serial.print(F("[debug]: Preparing to queue type E packet: ")); Serial.println(packet);
              delay(50);
              if (queue_relay_packet(packet, serialized_len)) {
                active_relays++;
                Serial.println(F("[info]: Relayed type E packet to Core0 queue"));
              } else {
                Serial.println(F("[error]: Failed to queue type E packet to Core0"));
              }
            }
          } else {
            Serial.println(F("[warn]: Cannot relay type E packet: no target or overloaded"));
            mutex_exit(&state_mutex);
          }
        } else if (doc["t"] == "F" && !strcmp(doc["to"] | "", device_id)) {
          Serial.print(F("[debug]: Received type F packet, to: ")); Serial.print(doc["to"] | "None");
          Serial.print(F(", device_id: ")); Serial.println(device_id);
          add_dependent(station_id);
          mutex_enter_blocking(&state_mutex);
          Serial.print(F("[debug]: target_id: ")); Serial.println(target_id[0] ? target_id : "None");
          Serial.print(F("[debug]: station_load: ")); Serial.print(station_load);
          Serial.print(F(", overload_threshold: ")); Serial.println(config.overload_threshold);
          if (target_id[0] && station_load <= config.overload_threshold) {
            doc["to"] = target_id;
            char packet[255];
            size_t serialized_len = serializeJson(doc, packet, sizeof(packet));
            if (serialized_len >= sizeof(packet)) {
              mutex_exit(&state_mutex);
              Serial.println(F("[error]: Relay packet buffer overflow for type F"));
            } else {
              mutex_exit(&state_mutex);
              Serial.print(F("[debug]: Preparing to queue type F packet: ")); Serial.println(packet);
              delay(50);
              if (queue_relay_packet(packet, serialized_len)) {
                active_relays++;
                Serial.println(F("[info]: Relayed type F packet to Core0 queue"));
              } else {
                Serial.println(F("[error]: Failed to queue type F packet to Core0"));
              }
            }
          } else {
            Serial.println(F("[warn]: Cannot relay type F packet: no target or overloaded"));
            mutex_exit(&state_mutex);
          }
        } else if (doc["t"] == "R" && !strcmp(doc["to"] | "", device_id)) {
            Serial.println(F("[info]: Not yet implemented"));
        }
      }
      mutex_exit(&radio_mutex);
    }

    mutex_enter_blocking(&state_mutex);
    if (waiting_for_pongs && can_select && pong_count == 0 && millis() - pong_start_time >= config.pong_timeout) {
        can_ping = true;
        waiting_for_pongs = false;  // ← was missing
        can_select = false;          // ← was missing
        mutex_exit(&state_mutex);
        continue;
    }
    if (waiting_for_pongs && can_select && pong_count > 0 && millis() - pong_start_time >= config.pong_timeout) {
      waiting_for_pongs = false;
      mutex_exit(&state_mutex);
      select_best_target();
      Serial.print(F("[info]: Target assigned: ")); Serial.println(target_id[0] ? target_id : "None");
    } else {
      mutex_exit(&state_mutex);
    }

    mutex_enter_blocking(&tx_queue_mutex);
    if (tx_queue_head != tx_queue_tail) {
        char pkt[MAX_PACKET_SIZE];
        uint8_t plen = tx_packet_lengths[tx_queue_tail];
        strlcpy(pkt, tx_packet_queue[tx_queue_tail], MAX_PACKET_SIZE);
        tx_queue_tail = (tx_queue_tail + 1) % RELAY_QUEUE_SIZE;
        mutex_exit(&tx_queue_mutex);
        mutex_enter_blocking(&radio_mutex);
        Serial.print(F("[debug]: Core1 Sending packet >> ")); Serial.println(pkt);
        if (!rf95.send((uint8_t*)pkt, plen - 1)) {
            Serial.println(F("[error]: rf95.send failed"));
        } else if (!rf95.waitPacketSent()) {
            Serial.println(F("[error]: rf95.waitPacketSent timed out"));
        } else {
            Serial.print(F("[debug]: Packet sent, length: ")); Serial.println(plen - 1);
        }
        delay(10);
        mutex_exit(&radio_mutex);
    } else {
        mutex_exit(&tx_queue_mutex);
    }
  }
}


// --- Relay functions ---
void init_relay_queue() {
  mutex_init(&relay_queue_mutex);
}

bool queue_relay_packet(const char* packet, uint8_t len) {
  mutex_enter_blocking(&relay_queue_mutex);
  if ((relay_queue_head + 1) % RELAY_QUEUE_SIZE == relay_queue_tail) {
    Serial.println(F("[error]: Relay packet queue full"));
    mutex_exit(&relay_queue_mutex);
    return false;
  }
  if (len > MAX_PACKET_SIZE) {
    Serial.println(F("[error]: Relay packet too large"));
    mutex_exit(&relay_queue_mutex);
    return false;
  }
  strlcpy(relay_packet_queue[relay_queue_head], packet, sizeof(relay_packet_queue[relay_queue_head]));
  relay_packet_lengths[relay_queue_head] = len;
  relay_queue_head = (relay_queue_head + 1) % RELAY_QUEUE_SIZE;
  Serial.print(F("[debug]: Queued relay packet to Core0 queue: ")); Serial.println(packet);
  mutex_exit(&relay_queue_mutex);
  return true;
}

void process_relay_queue() {
  mutex_enter_blocking(&relay_queue_mutex);
  if (relay_queue_head != relay_queue_tail) {
    const char* packet = relay_packet_queue[relay_queue_tail];
    uint8_t len = relay_packet_lengths[relay_queue_tail];
    relay_queue_tail = (relay_queue_tail + 1) % RELAY_QUEUE_SIZE;
    mutex_exit(&relay_queue_mutex);
    Serial.print(F("[debug]: Sending relay packet from Core0: ")); Serial.println(packet);
    rfm95_send(packet);
  } else {
    mutex_exit(&relay_queue_mutex);
  }
}

void wind_init_nonblocking() {
  static bool init_started = false;
  static uint32_t init_start_time = 0;
  if (!init_started) {
    Serial.println(F("[debug]: Initializing WS302 wind sensor"));
    init_started = true;
    init_start_time = millis();
  }
  if (millis() - init_start_time >= 500) {
    uint16_t regs[4];
    if (wind_query_registers(WIND_REG_SPEED, 4, regs)) {
      Serial.println(F("[info]: WS302 wind sensor found ... OK"));
      wind_connected = true;
      active_sensors++;
      Serial.print(F("[info]: Active sensors updated: ")); Serial.println(active_sensors);
    } else {
      Serial.println(F("[error]: WS302 wind sensor not responding"));
      wind_connected = false;
    }
    init_started = false;
  }
}

void soil_init_nonblocking() {
  static bool init_started = false;
  static uint32_t init_start_time = 0;
  if (!init_started) {
    Serial.println(F("[debug]: Initializing SEN0600 soil sensor"));
    init_started = true;
    init_start_time = millis();
  }
  if (millis() - init_start_time >= 500) {
    uint16_t regs[2];
    if (soil_query_registers(SOIL_REG_START, 2, regs)) {
      Serial.println(F("[info]: SEN0600 soil sensor found ... OK"));
      soil_connected = true;
      active_sensors++;
      Serial.print(F("[info]: Active sensors updated: ")); Serial.println(active_sensors);
    } else {
      Serial.println(F("[error]: SEN0600 soil sensor not responding"));
      soil_connected = false;
    }
    init_started = false;
  }
}

// --- Sensor Initialization ---
void si7021_init_nonblocking() {
  static bool init_started = false;
  static uint32_t init_start_time = 0;
  if (!init_started) {
    Serial.println(F("[debug]: Initializing Si7021"));
    init_started = true;
    init_start_time = millis();
  }
  if (millis() - init_start_time >= 500) {
    if (!si7021.begin()) {
      Serial.println(F("[error]: Adafruit Si7021 qwiic sensor not found"));
      si7021_connected = false;
    } else {
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
      si7021_connected = true;
      active_sensors++;
      Serial.print(F("[info]: Active sensors updated: ")); Serial.println(active_sensors);
    }
    init_started = false;
  }
}

void bme680_init_nonblocking() {
  static bool init_started = false;
  static uint32_t init_start_time = 0;
  if (!init_started) {
    Serial.println(F("[debug]: Initializing BME680 x2"));
    init_started = true;
    init_start_time = millis();
  }
  if (millis() - init_start_time >= 1000) {
    if (!bme680_1.begin(0x77)) {
      Serial.println(F("[error]: BME680 #1 not found at 0x77"));
      bme680_1_connected = false;
    } else {
      bme680_1.setTemperatureOversampling(BME680_OS_8X);
      bme680_1.setHumidityOversampling(BME680_OS_2X);
      bme680_1.setPressureOversampling(BME680_OS_4X);
      bme680_1.setIIRFilterSize(BME680_FILTER_SIZE_3);
      bme680_1.setGasHeater(320, 150);
      bme680_1_connected = true;
      active_sensors++;
      Serial.println(F("[info]: BME680 #1 found at 0x77"));
    }
    if (!bme680_2.begin(0x76)) {
      Serial.println(F("[error]: BME680 #2 not found at 0x76"));
      bme680_2_connected = false;
    } else {
      bme680_2.setTemperatureOversampling(BME680_OS_8X);
      bme680_2.setHumidityOversampling(BME680_OS_2X);
      bme680_2.setPressureOversampling(BME680_OS_4X);
      bme680_2.setIIRFilterSize(BME680_FILTER_SIZE_3);
      bme680_2.setGasHeater(320, 150);
      bme680_2_connected = true;
      active_sensors++;
      Serial.println(F("[info]: BME680 #2 found at 0x76"));
    }
    init_started = false;
  }
}

void tmp117_init_nonblocking() {
  static bool init_started = false;
  static uint32_t init_start_time = 0;
  if (!init_started) {
    Serial.println(F("[debug]: Initializing TMP117"));
    init_started = true;
    init_start_time = millis();
  }
  if (millis() - init_start_time >= 500) {
    if (!tmp117.begin()) {
      Serial.println(F("[error]: Adafruit TMP117 qwiic sensor not found"));
      tmp117_connected = false;
    } else {
      Serial.println(F("[info]: Adafruit TMP117 qwiic sensor found ... OK"));
      tmp117_connected = true;
      active_sensors++;
      Serial.print(F("[info]: Active sensors updated: ")); Serial.println(active_sensors);
    }
    init_started = false;
  }
}

void ltr390_init_nonblocking() {
  static bool init_started = false;
  static uint32_t init_start_time = 0;
  if (!init_started) {
    Serial.println(F("[debug]: Initializing LTR390"));
    init_started = true;
    init_start_time = millis();
  }
  if (millis() - init_start_time >= 500) {
    if (!ltr390.begin()) {
      Serial.println(F("[error]: Adafruit LTR390 qwiic sensor not found"));
      ltr390_connected = false;
    } else {
      ltr390.setMode(LTR390_MODE_UVS);
      ltr390.setGain(LTR390_GAIN_3);
      ltr390.setResolution(LTR390_RESOLUTION_16BIT);
      ltr390.setThresholds(0, 100);
      Serial.println(F("[info]: Adafruit LTR390 qwiic sensor found ... OK"));
      ltr390_connected = true;
      active_sensors++;
      Serial.print(F("[info]: Active sensors updated: ")); Serial.println(active_sensors);
    }
    init_started = false;
  }
}

void pm25aqi_init_nonblocking() {
  static bool init_started = false;
  static uint32_t init_start_time = 0;
  if (!init_started) {
    Serial.println(F("[debug]: Initializing PM25AQI"));
    init_started = true;
    init_start_time = millis();
  }
  if (millis() - init_start_time >= 500) {
    if (!pm25aqi.begin_I2C()) {
      Serial.println(F("[error]: Adafruit PM25AQI qwiic sensor not found"));
      pm25aqi_connected = false;
    } else {
      Serial.println(F("[info]: Adafruit PM25AQI qwiic sensor found ... OK"));
      pm25aqi_connected = true;
      active_sensors++;
      Serial.print(F("[info]: Active sensors updated: ")); Serial.println(active_sensors);
    }
    init_started = false;
  }
}

void scd40_init_nonblocking() {
  static bool init_started = false;
  static uint32_t init_start_time = 0;
  if (!init_started) {
    Serial.println(F("[debug]: Initializing SCD40"));
    init_started = true;
    init_start_time = millis();
  }
  if (millis() - init_start_time >= 500) {
    if (scd40.begin() == false) {
      Serial.println(F("[error]: SCD40 sensor not detected. Please check wiring."));
      scd40_connected = false;
    } else {
      Serial.println(F("[info]: SCD40 sensor found ... OK"));
      scd40_connected = true;
      active_sensors++;
      Serial.print(F("[info]: Active sensors updated: ")); Serial.println(active_sensors);
    }
    init_started = false;
  }
}

bool pa1010d_gps_init() {
  if (!sparkfun_GPS.begin()) {
    Serial.println(F("[error]: GPS module failed to respond. Please check wiring."));
    return false;
  }
  Serial.println(F("[info]: GPS module found"));
  return true;
}

// --- Sensor Data Transmission ---


// --- MRT calculation (ISO 7726) ---
float hcg_natural(float Ta, float Tg, float D) {
  return 1.4f * pow(fabs(Ta - Tg) / D, 0.25f);
}

float hcg_forced(float va, float D) {
  return 6.3f * pow(va, 0.6f) / pow(D, 0.4f);
}

bool calculate_mrt(float Tg, float Ta, float va, float D, float eps_g, float* mrt_c_out) {
  if (D <= 0 || eps_g <= 0 || eps_g > 1 || va < 0) {
    Serial.println(F("[error]: MRT invalid input params"));
    return false;
  }

  float h_nat = hcg_natural(Ta, Tg, D);
  float h_forced = (va > 0) ? hcg_forced(va, D) : 0.0f;
  float hcg = max(h_nat, h_forced);

  float Tg_k = Tg + 273.15f;
  float inner = pow(Tg_k, 4) + (hcg / (eps_g * SIGMA)) * (Tg - Ta);

  if (inner < 0) {
    Serial.print(F("[error]: MRT negative under 4th root, inner=")); Serial.println(inner);
    return false;
  }

  float mrt_k = pow(inner, 0.25f);
  *mrt_c_out = mrt_k - 273.15f;
  return true;
}


bool si7021_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping Si7021 transmit"));
    return false;
  }
  Serial.println(F("[debug]: Enter si7021_measure_transmit"));
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[144];
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, "si7021", "tmp", si7021.readTemperature(), "i2");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: Si7021 temperature packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, "si7021", "rh", si7021.readHumidity(), "i2");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: Si7021 humidity packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);
  Serial.println(F("[debug]: Exit si7021_measure_transmit"));
  return true;
}

bool bme680_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping BME680 transmit"));
    return false;
  }
  Serial.println(F("[debug]: Enter bme680_measure_transmit"));
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[144];
  const char* measurements[] = {"tmp", "rh", "pre", "gr", "al"};

  if (bme680_1_connected) {
    delay(500);
    rp2040.wdt_reset();
    Serial.println(F("[debug]: Calling BME680 #1 performReading..."));
    if (!bme680_1.performReading()) {
      Serial.println(F("[warn]: BME680 #1 performReading failed"));
      bme680_1_fresh = false;
    } else {
      bme680_1_fresh = true;
      Serial.println(F("[debug]: BME680 #1 reading OK"));
      altitude = bme680_1.readAltitude(SEALEVELPRESSURE_HPA);
      float values[] = {bme680_1.temperature, bme680_1.humidity,
                      (float)(bme680_1.pressure / 100.0),
                      (float)(bme680_1.gas_resistance / 1000.0),
                      (float)altitude};
      for (int i = 0; i < 5; i++) {
        doc["t"] = "F";
        add_common_json_fields(doc, timestamp, "bme680", measurements[i], values[i], "i2");
        if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
          Serial.println(F("[error]: BME680 #1 packet buffer overflow"));
          continue;
        }
        rfm95_send(packet);
      }
    }
  }

  if (bme680_2_connected) {
    delay(500);
    rp2040.wdt_reset();
    Serial.println(F("[debug]: Calling BME680 #2 performReading..."));
    if (!bme680_2.performReading()) {
      Serial.println(F("[warn]: BME680 #2 performReading failed"));
      bme680_2_fresh = false;
    } else {
      bme680_2_fresh = true;
      Serial.println(F("[debug]: BME680 #2 reading OK"));
      const char* gbt_measurements[] = {"globe_temperature", "globe_humidity",
                                         "globe_pressure", "globe_gas_resistance",
                                         "globe_altitude"};
      float values[] = {bme680_2.temperature, bme680_2.humidity,
                       (float)(bme680_2.pressure / 100.0),
                       (float)(bme680_2.gas_resistance / 1000.0),
                       (float)bme680_2.readAltitude(SEALEVELPRESSURE_HPA)};
      for (int i = 0; i < 5; i++) {
        doc["t"] = "F";
        add_common_json_fields(doc, timestamp, "gbt_bme680", gbt_measurements[i], values[i], "i2");
        if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
          Serial.println(F("[error]: BME680 #2 packet buffer overflow"));
          continue;
        }
        rfm95_send(packet);
      }
    }
  }

  Serial.println(F("[debug]: Exit bme680_measure_transmit"));
  return true;
}

bool mrt_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping MRT transmit"));
    return false;
  }
  if (!bme680_1_connected || !bme680_2_connected) {
    Serial.println(F("[warn]: MRT requires both BME680 sensors, skipping"));
    return false;
  }
  if (!bme680_1_fresh || !bme680_2_fresh) {
    Serial.println(F("[warn]: MRT requires fresh BME680 readings this cycle, skipping"));
    return false;
  }
  if (!wind_connected || !last_wind_speed_valid) {
    Serial.println(F("[warn]: MRT requires WS302 wind data, skipping"));
    return false;
  }

  Serial.println(F("[debug]: Enter mrt_measure_transmit"));

  float Ta = bme680_1.temperature;      // ambient
  float Tg = bme680_2.temperature;      // globe (soldered, 0x76)
  float va = last_wind_speed_ms;

  Serial.print(F("[debug]: MRT inputs -> Ta=")); Serial.print(Ta);
  Serial.print(F(" Tg=")); Serial.print(Tg);
  Serial.print(F(" va=")); Serial.print(va);
  Serial.print(F(" (bme1_fresh=")); Serial.print(bme680_1_fresh);
  Serial.print(F(", bme2_fresh=")); Serial.print(bme680_2_fresh);
  Serial.println(F(")"));

  float mrt_c;
  if (!calculate_mrt(Tg, Ta, va, MRT_GLOBE_DIAMETER_M, MRT_GLOBE_EMISSIVITY, &mrt_c)) {
    Serial.println(F("[warn]: MRT calculation failed"));
    return false;
  }

  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[144];
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, "gbt_ws", "MRT", mrt_c, "d2");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: MRT packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);

  Serial.print(F("[debug]: Exit mrt_measure_transmit, MRT=")); Serial.println(mrt_c);
  return true;
}

bool tmp117_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping TMP117 transmit"));
    return false;
  }
  Serial.println(F("[debug]: Enter tmp117_measure_transmit"));
  sensors_event_t temp;
  tmp117.getEvent(&temp);
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[144];
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, "tmp117", "tmp", temp.temperature, "i2");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: TMP117 packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);
  Serial.println(F("[debug]: Exit tmp117_measure_transmit"));
  return true;
}

bool ltr390_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping LTR390 transmit"));
    return false;
  }
  Serial.println(F("[debug]: Enter ltr390_measure_transmit"));
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[144];
  ltr390.setMode(LTR390_MODE_UVS);
  if (ltr390.newDataAvailable()) {
    doc["t"] = "F";
    add_common_json_fields(doc, timestamp, "ltr390", "uvs", ltr390.readUVS(), "i2");
    if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
      Serial.println(F("[error]: LTR390 UVS packet buffer overflow"));
    } else {
      rfm95_send(packet);
    }
  }
  ltr390.setMode(LTR390_MODE_ALS);
  if (ltr390.newDataAvailable()) {
    doc["t"] = "F";
    add_common_json_fields(doc, timestamp, "ltr390", "als", ltr390.readALS(), "i2");
    if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
      Serial.println(F("[error]: LTR390 ALS packet buffer overflow"));
    } else {
      rfm95_send(packet);
    }
  }
  Serial.println(F("[debug]: Exit ltr390_measure_transmit"));
  return true;
}

bool pm25aqi_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping PM25AQI transmit"));
    return false;
  }
  Serial.println(F("[debug]: Enter pm25aqi_measure_transmit"));
  PM25_AQI_Data data;
  if (!pm25aqi.read(&data)) {
    Serial.println(F("[warn]: Could not read from AQI"));
    return false;
  }
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[144];
  const char* measurements[] = {"pm10standard", "pm25standard", "pm100standard", "pm10env", "pm25env", "pm100env",
                                "partcount03um", "partcount05um", "partcount10um", "partcount25um", "partcount50um", "partcount100um"
                               };
  int values[] = {data.pm10_standard, data.pm25_standard, data.pm100_standard, data.pm10_env, data.pm25_env, data.pm100_env,
                  data.particles_03um, data.particles_05um, data.particles_10um, data.particles_25um, data.particles_50um, data.particles_100um
                 };
  for (int i = 0; i < 12; i++) {
    doc["t"] = "F";
    char buff[16];
    snprintf(buff, sizeof(buff), "pm%d", i);
    add_common_json_fields(doc, timestamp, "pmsa003i", buff, values[i], "i2");
    if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
      Serial.print(F("[error]: PM25AQI packet buffer overflow for ")); Serial.println(buff);
      continue;
    }
    rfm95_send(packet);
  }
  Serial.println(F("[debug]: Exit pm25aqi_measure_transmit"));
  return true;
}

bool gps_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping GPS transmit"));
    return false;
  }
  if (config.fixed_deployment && millis() - last_gps_sent < config.gps_fixed_interval) return false;
  Serial.println(F("[debug]: Enter gps_measure_transmit"));
  bool has_valid_data = false;
  mutex_enter_blocking(&state_mutex);
  gps_module = "default";
  if (pa1010d_connected) {
    while (sparkfun_GPS.available()) {
      gps.encode(sparkfun_GPS.read());
    }
    if (gps.location.isValid()) {
      latitude = gps.location.lat();
      longitude = gps.location.lng();
      has_valid_data = true;
      gps_module = "pa1010d";
    }
  }
  mutex_exit(&state_mutex);
  if (!has_valid_data) Serial.println(F("[info]: Using last recorded GPS coordinates"));
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[144];
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, gps_module.c_str(), "lat", latitude, "i2");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: GPS latitude packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, gps_module.c_str(), "lon", longitude, "i2");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: GPS longitude packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);
  last_gps_sent = millis();
  Serial.println(F("[debug]: Exit gps_measure_transmit"));
  return true;
}

bool wind_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping WS302 transmit"));
    return false;
  }
  Serial.println(F("[debug]: Enter wind_measure_transmit"));
  uint16_t regs[4];
  if (!wind_query_registers(WIND_REG_SPEED, 4, regs)) {
    Serial.println(F("[warn]: WS302 read failed"));
    return false;
  }

  uint32_t speed_bits = ((uint32_t)regs[3] << 16) | regs[2];
  float wind_speed_ms;
  memcpy(&wind_speed_ms, &speed_bits, sizeof(wind_speed_ms));
  float wind_dir_deg = (float)regs[1];

  last_wind_speed_ms = wind_speed_ms;
  last_wind_speed_valid = true;

  const float WIND_CALM_THRESHOLD_MS = 0.2f;  // tune against WS302 datasheet if it specifies one
  bool direction_valid = wind_speed_ms >= WIND_CALM_THRESHOLD_MS;

  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[144];

  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, "ws302", "ws", wind_speed_ms, "se");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: WS302 speed packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);

  if (direction_valid) {
    doc["t"] = "F";
    add_common_json_fields(doc, timestamp, "ws302", "wd", wind_dir_deg, "se");
    if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
      Serial.println(F("[error]: WS302 direction packet buffer overflow"));
      return false;
    }
    rfm95_send(packet);
  } else {
    Serial.println(F("[info]: WS302 calm — direction suppressed to avoid stuck value"));
  }

  Serial.println(F("[debug]: Exit wind_measure_transmit"));
  return true;
}

bool soil_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping SEN0600 transmit"));
    return false;
  }
  Serial.println(F("[debug]: Enter soil_measure_transmit"));
  uint16_t regs[2];
  if (!soil_query_registers(SOIL_REG_START, 2, regs)) {
    Serial.println(F("[warn]: SEN0600 read failed"));
    return false;
  }

  float moisture_pct = regs[0] / 10.0f;
  float temp_c = (float)((int16_t)regs[1]) / 10.0f;

  if (!isfinite(moisture_pct) || moisture_pct < 0.0f || moisture_pct > 100.0f ||
      !isfinite(temp_c) || temp_c < -40.0f || temp_c > 80.0f) {
    Serial.println(F("[warn]: SEN0600 out-of-range values, discarding"));
    return false;
  }

  last_soil_moisture_pct = moisture_pct;
  last_soil_temp_c = temp_c;
  last_soil_valid = true;

  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[144];

  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, "sen0600", "sm", moisture_pct, "se");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: SEN0600 moisture packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);

  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, "sen0600", "st", temp_c, "se");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: SEN0600 temperature packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);

  Serial.println(F("[debug]: Exit soil_measure_transmit"));
  return true;
}

bool scd40_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping SCD40 transmit"));
    return false;
  }
  Serial.println(F("[debug]: Enter scd40_measure_transmit"));
  uint16_t co2;
  float temperature, humidity;
  if (!scd40.readMeasurement()) return false;
  co2 = scd40.getCO2();
  temperature = scd40.getTemperature();
  humidity = scd40.getHumidity();
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[144];
  const char* measurements[] = {"CO2", "tmp", "rh"};
  float values[] = {(float)co2, temperature, humidity};
  for (int i = 0; i < 3; i++) {
    doc["t"] = "F";
    add_common_json_fields(doc, timestamp, "scd40", measurements[i], values[i], "i2");
    if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
      Serial.print(F("[error]: SCD40 packet buffer overflow for ")); Serial.println(measurements[i]);
      continue;
    }
    rfm95_send(packet);
  }
  Serial.println(F("[debug]: Exit scd40_measure_transmit"));
  return true;
}

void rg15_init_nonblocking() {
  static bool init_started = false;
  static uint32_t init_start_time = 0;
  if (!init_started) {
    Serial.println(F("[debug]: Initializing RG15 Rain Sensor"));
    init_started = true;
    init_start_time = millis();
    Serial1.begin(9600);
    Serial1.println("P");
    Serial1.println("M");
  }
  if (millis() - init_start_time >= 1000) {
    Serial1.println("R");
    delay(100);
    if (Serial1.available() > 0) {
      String response = Serial1.readString();
      if (response.indexOf("Acc") != -1) {
        Serial.println(F("[info]: RG15 Rain Sensor found ... OK"));
        rg15_connected = true;
        active_sensors++;
        Serial.print(F("[info]: Active sensors updated: ")); Serial.println(active_sensors);
      } else {
        Serial.println(F("[error]: RG15 communication failed"));
        rg15_connected = false;
      }
    } else {
      Serial.println(F("[error]: RG15 init failed - no response"));
      rg15_connected = false;
    }
    init_started = false;
  }
}

bool parse_rg15_response(String response) {
  rg15_acc_mm = 0.0;
  rg15_event_acc_mm = 0.0;
  rg15_total_acc_mm = 0.0;
  rg15_r_int_mm = 0.0;
  rg15_data_valid = false;
  int acc_pos = response.indexOf("Acc ");
  int event_pos = response.indexOf("EventAcc ");
  int total_pos = response.indexOf("TotalAcc ");
  int rint_pos = response.indexOf("RInt ");
  if (acc_pos != -1) {
    int start = acc_pos + 4;
    int end = response.indexOf(" mm", start);
    if (end != -1) {
      rg15_acc_mm = response.substring(start, end).toFloat();
    }
  }
  if (event_pos != -1) {
    int start = event_pos + 9;
    int end = response.indexOf(" mm", start);
    if (end != -1) {
      rg15_event_acc_mm = response.substring(start, end).toFloat();
    }
  }
  if (total_pos != -1) {
    int start = total_pos + 9;
    int end = response.indexOf(" mm", start);
    if (end != -1) {
      rg15_total_acc_mm = response.substring(start, end).toFloat();
    }
  }
  if (rint_pos != -1) {
    int start = rint_pos + 5;
    int end = response.indexOf(" mmph", start);
    if (end != -1) {
      rg15_r_int_mm = response.substring(start, end).toFloat();
    }
  }
  rg15_data_valid = (acc_pos != -1 || event_pos != -1 || total_pos != -1 || rint_pos != -1);
  return rg15_data_valid;
}
bool rg15_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping RG15 transmit"));
    return false;
  }
  if (!rg15_connected) {
    Serial.println(F("[warn]: RG15 not connected, skipping transmit"));
    return false;
  }
  Serial.println(F("[debug]: Enter rg15_measure_transmit"));
  while (Serial1.available() > 0) {
    Serial1.read();
  }
  Serial1.println("R");
  uint32_t start_time = millis();
  String response = "";
  while (millis() - start_time < 2000) {
    if (Serial1.available() > 0) {
      response += Serial1.readString();
      break;
    }
    delay(10);
  }
  if (response.length() == 0) {
    Serial.println(F("[error]: RG15 no response"));
    return false;
  }
  bool data_valid = parse_rg15_response(response);
  if (!data_valid) {
    Serial.println(F("[error]: RG15 invalid data"));
    return false;
  }
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[144];
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, "rg15", "ra", rg15_acc_mm, "se");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: RG15 accumulated rainfall packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, "rg15", "re", rg15_event_acc_mm, "se");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: RG15 event rainfall packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, "rg15", "rt", rg15_total_acc_mm, "se");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: RG15 total rainfall packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);
  doc["t"] = "F";
  add_common_json_fields(doc, timestamp, "rg15", "ri", rg15_r_int_mm, "se");
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: RG15 rain intensity packet buffer overflow"));
    return false;
  }
  rfm95_send(packet);
  Serial.println(F("[debug]: Exit rg15_measure_transmit"));
  return true;
}

void rg15_reset_counters(bool acc_only) {
  Serial.println(F("[debug]: Resetting RG15 counters"));
  if (!rg15_connected) {
    Serial.println(F("[error]: RG15 not connected, cannot reset counters"));
    return;
  }
  rg15Serial.write("O\r\n"); // Reset accumulated counter
  delay(100);
  if (!acc_only) {
    rg15Serial.write("K\r\n"); // Reset event counter (only if acc_only is false)
    delay(100);
  }
  rg15_acc_mm = 0.0;
  rg15_event_acc_mm = 0.0;
  rg15_data_valid = false;
  Serial.println(F("[info]: RG15 counters reset"));
}

// --- Setup and Loop ---
void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 10000);
  Serial.println(F("*** IoTwx-LoRa-RP2040 v0.1 ***"));
  Wire.begin();

  // Test two BME680 sensors
  // --- TEMPORARY I2C SCANNER - remove after testing ---
  Serial.println(F("Scanning I2C addresses..."));
  for (byte addr = 1; addr < 127; addr++) {
      Wire.beginTransmission(addr);
      byte error = Wire.endTransmission();
      if (error == 0) {
          Serial.print(F("Found device at 0x"));
          Serial.println(addr, HEX);
      }
  }
  // Serial.println(F("Scan complete"));
  // // --- END SCANNER ---

  rp2040.wdt_begin(15000);
  mutex_init(&radio_mutex);
  mutex_init(&state_mutex);
  mutex_init(&tx_queue_mutex);
  init_relay_queue();


  // if (!LittleFS.begin()) {
  //   Serial.println(F("[warn]: LittleFS mount failed, attempting format..."));
  //   if (LittleFS.format() && LittleFS.begin()) {
  //       Serial.println(F("[info]: LittleFS formatted and mounted OK"));
  //   } else {
  //       Serial.println(F("[fatal]: LittleFS format failed, halting"));
  //       while (1);
  //   }
  // }
  // Serial.println(F("[info]: LittleFS Initialized"));

  if (!LittleFS.begin()) {
      Serial.println(F("[fatal]: LittleFS mount failed. Flash config.uf2 first, then reflash firmware."));
      while (1);
  }
  Serial.println(F("[info]: LittleFS Initialized"));

  load_config();

  rfm95_start();
  rfm95_reset();
  if (!rfm95_init()) {
    Serial.println(F("[error]: RFM95 init failed"));
    while (1);
  }
  for (size_t i = 0; i < UniqueIDsize; i++) {
    sprintf(&device_id[i * 2], "%.2X", UniqueID[i]);
  }
  Serial.print(F("[info]: device_id ==> ")); Serial.println(device_id);
  mutex_enter_blocking(&state_mutex);
  pa1010d_connected = pa1010d_gps_init();
  mutex_exit(&state_mutex);
  if (pa1010d_connected) {
    active_sensors++;
    Serial.print(F("[info]: Active sensors updated: ")); Serial.println(active_sensors);
  }

  // Initialize BME680 sensors before starting Core 1
  Serial.println(F("[debug]: Initializing BME680 x2"));
  delay(1000);
  if (!bme680_1.begin(0x77)) {
    Serial.println(F("[error]: BME680 #1 not found at 0x77"));
  } else {
    bme680_1.setTemperatureOversampling(BME680_OS_8X);
    bme680_1.setHumidityOversampling(BME680_OS_2X);
    bme680_1.setPressureOversampling(BME680_OS_4X);
    bme680_1.setIIRFilterSize(BME680_FILTER_SIZE_3);
    bme680_1.setGasHeater(320, 150);
    bme680_1_connected = true;
    active_sensors++;
    Serial.println(F("[info]: BME680 #1 found at 0x77"));
  }
  delay(500);
  if (!bme680_2.begin(0x76)) {
    Serial.println(F("[error]: BME680 #2 not found at 0x76"));
  } else {
    bme680_2.setTemperatureOversampling(BME680_OS_8X);
    bme680_2.setHumidityOversampling(BME680_OS_2X);
    bme680_2.setPressureOversampling(BME680_OS_4X);
    bme680_2.setIIRFilterSize(BME680_FILTER_SIZE_3);
    bme680_2.setGasHeater(320, 150);
    bme680_2_connected = true;
    active_sensors++;
    Serial.println(F("[info]: BME680 #2 found at 0x76"));
  }

  Serial2.setRX(WIND_RX_PIN);
  Serial2.setTX(WIND_TX_PIN);
  Serial2.begin(WIND_BAUD, SERIAL_8E1);
  soilSerial.begin(SOIL_BAUD, SERIAL_8N1);
  pinMode(LED_BUILTIN, OUTPUT);
  multicore_launch_core1(core1_entry);
}


void loop() {
  rp2040.wdt_reset();
  static bool sensors_initialized = false;
  static uint32_t loop_start_time = 0;
  if (loop_start_time == 0) loop_start_time = millis();
  if (!sensors_initialized) {
    si7021_init_nonblocking();
    tmp117_init_nonblocking();
    ltr390_init_nonblocking();
    pm25aqi_init_nonblocking();
    scd40_init_nonblocking();
    rg15_init_nonblocking();
    wind_init_nonblocking();
    soil_init_nonblocking();

    if (millis() - loop_start_time >= 1500 &&
        (si7021_connected || bme680_1_connected || bme680_2_connected || tmp117_connected || ltr390_connected ||
        pm25aqi_connected || scd40_connected || rg15_connected || wind_connected || soil_connected)) {
      sensors_initialized = true;
      start_station_info();
    }
    return;
  }

  handle_blink_led();
  handle_continuous_pong();

  mutex_enter_blocking(&state_mutex);
  if (target_id[0] && millis() - last_connect >= config.connect_timeout) {
    Serial.println(F("[warn]: Keep-alive timeout, clearing target"));
    target_id[0] = '\0';
    has_pi_path = false;
    relay_count = 0;
    mutex_exit(&state_mutex);
  } else {
    mutex_exit(&state_mutex);
  }

  if (!target_id[0] && can_ping && !mutex_safe_get_waiting_for_pongs() && millis() - last_ping_attempt >= PING_MIN_INTERVAL) {
    start_ping();
  }

  static uint32_t last_station_info_start = 0;
  if (millis() - last_station_info_start >= config.station_info_interval) {
      if (start_station_info()) {
          last_station_info_start = millis();
      }
  }
  handle_station_info();
  process_relay_queue();

  if (millis() - last_sensor_transmit < config.sensor_transmit_delay || !can_transmit) return;

  mutex_enter_blocking(&state_mutex);
  if (rg15_connected && millis() - last_rg15_acc_reset >= RG15_ACC_INTERVAL) {
    Serial.println(F("[info]: 24-hour interval reached, resetting RG15 accumulated rainfall counter"));
    rg15_reset_counters(true);
    last_rg15_acc_reset = millis();
  }
  mutex_exit(&state_mutex);

  last_sensor_transmit = millis();
  update_station_load();

  bme680_1_fresh = false;
  bme680_2_fresh = false;

  bool transmit_ok;
  Serial.print(F("[info]: Transmitting sensors: "));
  Serial.print(F("Si7021 "));
  if (si7021_connected && (transmit_ok = si7021_measure_transmit())) start_blink_led();
  rp2040.wdt_reset();

  Serial.print(F("BME680 "));
  if ((bme680_1_connected || bme680_2_connected) && (transmit_ok = bme680_measure_transmit())) start_blink_led();
  rp2040.wdt_reset();

  Serial.print(F("TMP117 "));
  if (tmp117_connected && (transmit_ok = tmp117_measure_transmit())) start_blink_led();
  rp2040.wdt_reset();

  Serial.print(F("LTR390 "));
  if (ltr390_connected && (transmit_ok = ltr390_measure_transmit())) start_blink_led();
  rp2040.wdt_reset();

  Serial.print(F("PM25AQI "));
  if (pm25aqi_connected && (transmit_ok = pm25aqi_measure_transmit())) start_blink_led();
  rp2040.wdt_reset();

  Serial.print(F("PA1010D "));
  if (pa1010d_connected && (transmit_ok = gps_measure_transmit())) start_blink_led();
  rp2040.wdt_reset();

  Serial.print(F("SCD40 "));
  if (scd40_connected && (transmit_ok = scd40_measure_transmit())) start_blink_led();
  rp2040.wdt_reset();

  Serial.print(F("RG15 "));
  if (rg15_connected && (transmit_ok = rg15_measure_transmit())) start_blink_led();
  rp2040.wdt_reset();

  Serial.print(F("WS302 "));
  if (wind_connected && (transmit_ok = wind_measure_transmit())) start_blink_led();
  rp2040.wdt_reset();

  Serial.print(F("SEN0600 "));
  if (soil_connected && (transmit_ok = soil_measure_transmit())) start_blink_led();
  rp2040.wdt_reset();

  Serial.print(F("MRT "));
  if ((bme680_1_connected && bme680_2_connected) && (transmit_ok = mrt_measure_transmit())) start_blink_led();
  rp2040.wdt_reset();

  if (!(si7021_connected || bme680_1_connected || bme680_2_connected || tmp117_connected || ltr390_connected ||
        pm25aqi_connected || scd40_connected || rg15_connected || pa1010d_connected || wind_connected || soil_connected)) {
    Serial.print(F("None Connected"));
  }
  Serial.println();
}