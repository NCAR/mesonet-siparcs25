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
#include <TinyGPSPlus.h>
#include <SparkFun_I2C_GPS_Arduino_Library.h>
#include <SparkFun_SCD4x_Arduino_Library.h>
#include <ArduinoJson.h>
#include <pico/stdlib.h>
#include <pico/multicore.h>
#include <pico/sync.h>
#include <SoftwareSerial.h>
#include <Arduino.h> 

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
#define MAX_PACKET_SIZE 256
#define RG15_RX_PIN 1
#define RG15_TX_PIN 0
#define CONTINUOUS_TX_DURATION 6000 // 6 seconds for continuous transmission
#define CONTINUOUS_PONG_DELAY_MAX 1500 //1.5 seconds for random pong max delay



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
Adafruit_BME680 bme680;
Adafruit_TMP117 tmp117;
Adafruit_GPS pa1010d(&Wire);
I2CGPS sparkfun_GPS;
Adafruit_LTR390 ltr390;
Adafruit_PM25AQI pm25aqi;
TinyGPSPlus gps;
SCD4x scd40;
SoftwareSerial rg15Serial(RG15_RX_PIN, RG15_TX_PIN);

// --- RG15 Rain Sensor ---
bool rg15_connected = false;

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
  uint32_t keep_alive_timeout;
  float latitude;
  float longitude;
  float altitude;
  uint32_t station_info_interval;
  bool fixed_deployment;
  uint32_t gps_fixed_interval;
  uint32_t sensor_transmit_delay;
  String firstname;
  String lastname;
  String email;
  String organization;
  String device;
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

// --- Global Variables ---
uint32_t last_ping_attempt = 0;
char device_id[17] = {0};
char target_id[17] = {0};
bool has_pi_path = false;
uint8_t relay_count = 0;
uint8_t target_relay_count = 0;
uint32_t last_broadcast = 0;
uint32_t last_keep_alive_received = 0;
bool waiting_for_pongs = false;
uint32_t pong_start_time = 0;
uint32_t last_station_info_sent = 0;
uint32_t last_gps_sent = 0;
uint8_t active_sensors = 0;
uint8_t active_relays = 0;
uint32_t last_load_update = 0;
float station_load = 0.0;
bool si7021_connected = false;
bool bme680_connected = false;
bool tmp117_connected = false;
bool ltr390_connected = false;
bool pm25aqi_connected = false;
bool pa1010d_connected = false;
bool gps_connected = false;
bool scd40_connected = false;
double latitude;
double longitude;
double altitude;
String gps_timestamp;
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
uint32_t ping_min_interval = 15000UL;

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
  last_keep_alive_received = millis();
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
  } else if (!led_state && current_time - last_blink_time >= BLINK_LOW_DURATION) {
    mutex_exit(&state_mutex);
  }
  mutex_exit(&state_mutex);
}

String get_gps_timestamp() {
  if (!pa1010d_connected) return gps_timestamp;
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
  return gps_timestamp;
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
  if (bme680_connected) Serial.print(F("BME680 "));
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
    Serial.println(F("[error]: Failed to open /config.json"));
    return false;
  }
  StaticJsonDocument<512> doc;
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
  config.pong_timeout = doc["radio"]["pong_timeout"] | 10000UL;
  ping_min_interval = config.pong_timeout + 5000UL;
  config.keep_alive_timeout = doc["radio"]["keep_alive_timeout"] | 900000UL;
  config.latitude = doc["station_info"]["latitude"] | 0.0;
  config.longitude = doc["station_info"]["longitude"] | 0.0;
  config.altitude = doc["station_info"]["altitude"] | 0.0;
  config.firstname = doc["station_info"]["firstname"] | "";
  config.lastname = doc["station_info"]["lastname"] | "";
  config.email = doc["station_info"]["email"] | "";
  config.organization = doc["station_info"]["organization"] | "";
  config.device = doc["station_info"]["device"] | "";
  latitude = config.latitude;
  longitude = config.longitude;
  altitude = config.altitude;
  config.station_info_interval = doc["station_info"]["station_info_interval"] | 86400000UL;
  config.fixed_deployment = doc["station_info"]["fixed_deployment"] | false;
  config.sensor_transmit_delay = doc["station_info"]["sensor_transmit_delay"] | 60000UL;
  config.gps_fixed_interval = doc["station_info"]["gps_fixed_interval"] | 43200000UL;
  Serial.println(F("[info]: Loaded /config.json"));
  return true;
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
  mutex_enter_blocking(&state_mutex);
  if (target_id[0]) doc["to"] = target_id;
  doc["r"] = !target_id[0];
  mutex_exit(&state_mutex);
}

// --- Network Communication ---
void start_ping() {
  Serial.println(F("[debug]: Enter start_ping"));
  StaticJsonDocument<64> doc;
  char packet[64];
  doc["sid"] = device_id;
  doc["t"] = "A";
  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: Ping packet buffer overflow"));
    return;
  }
  mutex_safe_set_waiting_for_pongs(true);
  mutex_enter_blocking(&state_mutex);
  pong_count = 0;
  mutex_exit(&state_mutex);
  rfm95_send(packet);
  mutex_enter_blocking(&state_mutex);
  pong_start_time = millis();
  last_ping_attempt = millis();
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
  // Add random initial delay
  static bool initial_delay_done = false;
  static uint32_t initial_delay_ms = 0;
  if (!initial_delay_done) {
    initial_delay_ms = random(0, (uint32_t)(CONTINUOUS_PONG_DELAY_MAX));
    Serial.print(F("[info]: Delaying continuous pong by ")); Serial.print(initial_delay_ms); Serial.println(F(" ms"));
    delay(initial_delay_ms);
    initial_delay_done = true;
  }
  StaticJsonDocument<96> pong_doc;
  char packet[96];
  pong_doc["sid"] = device_id;
  pong_doc["t"] = "B";
  pong_doc["ty"] = "2";
  pong_doc["l"] = station_load;
  pong_doc["rssi"] = rf95.lastRssi();
  pong_doc["rc"] = relay_count;
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
  Serial.println(F("[debug]: Starting/Extending continuous pong for 3 seconds"));
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
    current_state = IDLE;
    last_packet_time = millis();
    mutex_exit(&state_mutex);
    return;
  }
  mutex_exit(&state_mutex);

  File file = LittleFS.open("/config.json", "r");
  if (!file) {
    Serial.println(F("[error]: Failed to open /config.json for station_info"));
    mutex_enter_blocking(&state_mutex);
    current_state = IDLE;
    last_packet_time = millis();
    mutex_exit(&state_mutex);
    return;
  }
  StaticJsonDocument<256> cfg;
  DeserializationError error = deserializeJson(cfg, file);
  file.close();
  if (error) {
    Serial.print(F("[error]: JSON parse failed: ")); Serial.println(error.c_str());
    mutex_enter_blocking(&state_mutex);
    current_state = IDLE;
    last_packet_time = millis();
    mutex_exit(&state_mutex);
    return;
  }

  StaticJsonDocument<256> doc;
  char packet[256];
  mutex_enter_blocking(&state_mutex);
  doc["sid"] = device_id;
  doc["t"] = "E";
  doc["fn"] = cfg["station_info"]["firstname"] | "";
  doc["ln"] = cfg["station_info"]["lastname"] | "";
  doc["e"] = cfg["station_info"]["email"] | "";
  doc["o"] = cfg["station_info"]["organization"] | "";
  doc["de"] = cfg["station_info"]["device"] | "";
  doc["lat"] = latitude;
  doc["lon"] = longitude;
  doc["al"] = altitude;
  if (target_id[0]) doc["to"] = target_id;
  String gps_timestamp = get_gps_timestamp();
  if (!gps_timestamp.isEmpty()) doc["ts"] = gps_timestamp;
  mutex_exit(&state_mutex);

  if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
    Serial.println(F("[error]: Station info packet buffer overflow"));
    mutex_enter_blocking(&state_mutex);
    current_state = IDLE;
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

void start_station_info() {
  mutex_enter_blocking(&state_mutex);
  if (!has_pi_path || millis() - last_station_info_sent < config.station_info_interval) {
    mutex_exit(&state_mutex);
    return;
  }
  Serial.println(F("[debug]: Starting continuous station_info transmission for 3 seconds"));
  current_state = SENDING_STATION_INFO;
  last_station_info_sent = millis();
  last_packet_time = millis();
  mutex_exit(&state_mutex);
}

void send_disconnect() {
  mutex_enter_blocking(&state_mutex);
  Serial.println(F("[debug]: Sending disconnect to dependents"));
  StaticJsonDocument<48> doc;
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
  if (!pong_count) {
    target_id[0] = '\0';
    has_pi_path = false;
    relay_count = 0;
    mutex_exit(&state_mutex);
    send_disconnect();
    Serial.println(F("[warn]: No pongs received, broadcasting without target"));
    return;
  }

  float best_pi_score = -1.0;
  char best_pi_id[17] = {0};
  uint8_t best_pi_relay_count = 255;
  float best_station_score = -1.0;
  char best_station_id[17] = {0};
  uint8_t best_station_relay_count = 255;

  // Evaluate all pongs
  for (uint8_t i = 0; i < pong_count; i++) {
    float norm_rssi = (pongs[i].rssi + 120.0f) / 70.0;
    norm_rssi = constrain(norm_rssi, 0.0, 1.0);
    float type_bonus = (strcmp(pongs[i].type, "1") == 0) ? 1.0 : 0.0; // Bonus for Pi
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

    // Track best Pi and best station separately
    if (strcmp(pongs[i].type, "1") == 0) { // Pi
      if (score > best_pi_score) {
        best_pi_score = score;
        strlcpy(best_pi_id, pongs[i].id, sizeof(best_pi_id));
        best_pi_relay_count = pongs[i].relay_count;
      }
    } else { // Station
      if (score > best_station_score) {
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
    last_station_info_sent = millis() - config.station_info_interval - 1;
    mutex_exit(&state_mutex);
    start_station_info();
    mutex_enter_blocking(&state_mutex);
  }
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
  rf95.setPreambleLength(6);
  Serial.println(F("[info]: RFM95 configured: BW=125kHz, CR=4/5, SF=7, Preamble=6"));
  return true;
}

void rfm95_send(const char* packet) {
  uint8_t len = strlen(packet) + 1;
  if (len > MAX_PACKET_SIZE) {
    Serial.println(F("[error]: Packet too large for FIFO"));
    return;
  }
  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, packet);
  if (error) {
    Serial.print(F("[error]: Invalid JSON packet: ")); Serial.println(packet);
    return;
  }
  Serial.print(F("[debug]: Preparing to send packet: ")); Serial.println(packet);
  multicore_fifo_push_blocking(len);
  for (uint8_t i = 0; i < len; i++) {
    multicore_fifo_push_blocking(packet[i]);
  }
}

void core1_entry() {
  mutex_init(&radio_mutex);
  
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
        StaticJsonDocument<255> doc;
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
          handle_continuous_pong();
        } else if (doc["t"] == "B" && mutex_safe_get_waiting_for_pongs()) {
          mutex_safe_update_pong(station_id, doc["ty"] | "2", doc["l"] | 0.0f, doc["rssi"] | 0, doc["rc"] | 0);
          Serial.println(F("[info]: Stored pong"));
        } else if (doc["t"] == "D" && !strcmp(doc["to"] | "", device_id)) {
          mutex_safe_clear_target();
          send_disconnect();
          Serial.println(F("[info]: Received disconnect, cleared target and sent disconnect to dependents"));
          start_ping();
        } else if (doc["t"] == "F" && !strcmp(doc["to"] | "", device_id)) {
          add_dependent(station_id);
          mutex_enter_blocking(&state_mutex);
          if (target_id[0] && station_load <= config.overload_threshold) {
            doc["to"] = target_id;
            char packet[255];
            if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
              mutex_exit(&state_mutex);
              Serial.println(F("[error]: Relay packet buffer overflow"));
            } else {
              mutex_exit(&state_mutex);
              rfm95_send(packet);
              active_relays++;
              Serial.println(F("[info]: Relayed type F packet"));
            }
          } else {
            mutex_exit(&state_mutex);
          }
        } 
      }
      mutex_exit(&radio_mutex);
    }
    
    mutex_enter_blocking(&state_mutex);
    if (waiting_for_pongs && pong_count > 0 && millis() - pong_start_time >= config.pong_timeout) {
      waiting_for_pongs = false;
      mutex_exit(&state_mutex);
      select_best_target();
      Serial.print(F("[info]: Target assigned: ")); Serial.println(target_id[0] ? target_id : "None");
    } else {
      mutex_exit(&state_mutex);
    }
    
    if (multicore_fifo_rvalid()) {
      mutex_enter_blocking(&radio_mutex);
      uint8_t len = multicore_fifo_pop_blocking();
      char packet[MAX_PACKET_SIZE];
      for (uint8_t i = 0; i < len; i++) {
        packet[i] = (char)multicore_fifo_pop_blocking();
      }
      Serial.print(F("[debug]: Core1 Sending packet >> ")); Serial.println(packet);
      if (!rf95.send((uint8_t*)packet, len - 1)) {
        Serial.println(F("[error]: rf95.send failed"));
      } else if (!rf95.waitPacketSent()) {
        Serial.println(F("[error]: rf95.waitPacketSent timed out"));
      } else {
        Serial.print(F("[debug]: Packet sent successfully, length: ")); Serial.print(len - 1);
        Serial.print(F(", content: ")); Serial.println(packet);
      }
      delay(10);
      mutex_exit(&radio_mutex);
    }
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
    Serial.println(F("[debug]: Initializing BME680"));
    init_started = true;
    init_start_time = millis();
  }
  if (millis() - init_start_time >= 500) {
    if (!bme680.begin()) {
      Serial.println(F("[error]: BME680 init failed"));
      bme680_connected = false;
    } else {
      bme680.setTemperatureOversampling(BME680_OS_8X);
      bme680.setHumidityOversampling(BME680_OS_2X);
      bme680.setPressureOversampling(BME680_OS_4X);
      bme680.setIIRFilterSize(BME680_FILTER_SIZE_3);
      bme680.setGasHeater(320, 150);
      Serial.println(F("[info]: Adafruit BME680 qwiic sensor found ... OK"));
      bme680_connected = true;
      active_sensors++;
      Serial.print(F("[info]: Active sensors updated: ")); Serial.println(active_sensors);
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
bool si7021_measure_transmit() {
  if (!has_pi_path) {
    Serial.println(F("[warn]: No Pi path, skipping Si7021 transmit"));
    return false;
  }
  Serial.println(F("[debug]: Enter si7021_measure_transmit"));
  String timestamp = get_gps_timestamp();
  StaticJsonDocument<96> doc;
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
  if (!bme680.performReading()) {
    Serial.println(F("[error]: Failed to perform reading"));
    return false;
  }
  String timestamp = get_gps_timestamp();
  StaticJsonDocument<96> doc;
  char packet[144];
  const char* measurements[] = {"tmp", "rh", "pre", "gr", "al"};
  altitude = bme680.readAltitude(SEALEVELPRESSURE_HPA);
  float values[] = {bme680.temperature, bme680.humidity, bme680.pressure / 100.0,
                    bme680.gas_resistance / 1000.0, altitude};
  for (int i = 0; i < 5; i++) {
    doc["t"] = "F";
    add_common_json_fields(doc, timestamp, "bme680", measurements[i], values[i], "i2");
    if (serializeJson(doc, packet, sizeof(packet)) >= sizeof(packet)) {
      Serial.print(F("[error]: BME680 packet buffer overflow for ")); Serial.println(measurements[i]);
      continue;
    }
    rfm95_send(packet);
  }
  Serial.println(F("[debug]: Exit bme680_measure_transmit"));
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
  StaticJsonDocument<96> doc;
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
  StaticJsonDocument<96> doc;
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
  StaticJsonDocument<96> doc;
  char packet[144];
  const char* measurements[] = {"pm10standard", "pm25standard", "pm100standard", "pm10env", "pm25env", "pm100env",
                               "partcount03um", "partcount05um", "partcount10um", "partcount25um", "partcount50um", "partcount100um"};
  int values[] = {data.pm10_standard, data.pm25_standard, data.pm100_standard, data.pm10_env, data.pm25_env, data.pm100_env,
                  data.particles_03um, data.particles_05um, data.particles_10um, data.particles_25um, data.particles_50um, data.particles_100um};
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
  String gps_module = "default";
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
  if (!has_valid_data) Serial.println(F("[info]: Using last recorded GPS coordinates"));
  String timestamp = get_gps_timestamp();
  StaticJsonDocument<96> doc;
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
  StaticJsonDocument<96> doc;
  char packet[144];
  const char* measurements[] = {"CO2", "tmp", "rh"};
  float values[] = {co2, temperature, humidity};
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

float rg15_acc_mm = 0.0;
float rg15_event_acc_mm = 0.0;
float rg15_total_acc_mm = 0.0;
float rg15_r_int_mm = 0.0;
bool rg15_data_valid = false;

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
  StaticJsonDocument<96> doc;
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

void rg15_reset_counters() {
  if (!rg15_connected) {
    Serial.println(F("[warn]: RG15 not connected, cannot reset"));
    return;
  }
  Serial.println(F("[debug]: Resetting RG15 counters"));
  Serial1.println("O");
  delay(100);
  Serial1.println("K");
  delay(100);
}

// --- Setup and Loop ---
void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 10000);
  Serial.println(F("*** IoTwx-LoRa-RP2040 v0.1 ***"));
  Wire.begin();
  rp2040.wdt_begin(15000);
  mutex_init(&state_mutex);
  if (!LittleFS.begin()) {
    Serial.println(F("[error]: LittleFS init failed"));
    while (1);
  }
  Serial.println(F("[info]: LittleFS Initialized"));
  if (!load_config()) {
    Serial.println(F("[error]: Config load failed, using defaults"));
    config = {
      0.85f, 10.0f, 0.2f, 5.0f, 0.5f, 0.7f, 0.3f,
      0.35f, 0.35f, 0.2f, 0.1f, 1.0f,
      12000UL, 60000UL,
      0.0, 0.0, 0.0, 86400000UL, true, 43200000UL,
      60000UL, "", "", "", "", "adafruit RP2040 RFM95 LoRa"
    };
    latitude = config.latitude;
    longitude = config.longitude;
    altitude = config.altitude;
  }
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
  pa1010d_connected = pa1010d_gps_init();
  if (pa1010d_connected) {
    active_sensors++;
    Serial.print(F("[info]: Active sensors updated: ")); Serial.println(active_sensors);
  }
  pinMode(LED_BUILTIN, OUTPUT);
  multicore_launch_core1(core1_entry);
}

void loop() {
  rp2040.wdt_reset();
  static bool sensors_initialized = false;
  if (!sensors_initialized) {
    si7021_init_nonblocking();
    bme680_init_nonblocking();
    tmp117_init_nonblocking();
    ltr390_init_nonblocking();
    pm25aqi_init_nonblocking();
    scd40_init_nonblocking();
    rg15_init_nonblocking();
    if (si7021_connected || bme680_connected || tmp117_connected || ltr390_connected ||
        pm25aqi_connected || scd40_connected || rg15_connected) {
      sensors_initialized = true;
      start_station_info();
    }
    return;
  }
  handle_blink_led();
  handle_continuous_pong();
  handle_station_info();
  mutex_enter_blocking(&state_mutex);
  if (target_id[0] && millis() - last_keep_alive_received >= config.keep_alive_timeout) {
    Serial.println(F("[warn]: Keep-alive timeout, clearing target"));
    target_id[0] = '\0';
    has_pi_path = false;
    relay_count = 0;
    mutex_exit(&state_mutex);
    send_disconnect();
  } else {
    mutex_exit(&state_mutex);
  }
  if (!target_id[0] && millis() - last_ping_attempt >= ping_min_interval) {
    start_ping();
  }
  start_station_info();
  static uint32_t last_sensor_transmit = 0;
  if (millis() - last_sensor_transmit < config.sensor_transmit_delay) return;
  last_sensor_transmit = millis();
  update_station_load();
  bool transmit_ok;
  Serial.print(F("[info]: Transmitting sensors: "));
  if (si7021_connected && (transmit_ok = si7021_measure_transmit())) {
    start_blink_led();
    Serial.print(F("Si7021 "));
  }
  if (bme680_connected && (transmit_ok = bme680_measure_transmit())) {
    start_blink_led();
    Serial.print(F("BME680 "));
  }
  if (tmp117_connected && (transmit_ok = tmp117_measure_transmit())) {
    start_blink_led();
    Serial.print(F("TMP117 "));
  }
  if (ltr390_connected && (transmit_ok = ltr390_measure_transmit())) {
    start_blink_led();
    Serial.print(F("LTR390 "));
  }
  if (pm25aqi_connected && (transmit_ok = pm25aqi_measure_transmit())) {
    start_blink_led();
    Serial.print(F("PM25AQI "));
  }
  if (pa1010d_connected && (transmit_ok = gps_measure_transmit())) {
    start_blink_led();
    Serial.print(F("PA1010D "));
  }
  if (scd40_connected && (transmit_ok = scd40_measure_transmit())) {
    start_blink_led();
    Serial.print(F("SCD40 "));
  }
  if (rg15_connected && (transmit_ok = rg15_measure_transmit())) {
    start_blink_led();
    Serial.print(F("RG15 "));
  }
  if (!(si7021_connected || bme680_connected || tmp117_connected || ltr390_connected ||
        pm25aqi_connected || scd40_connected || rg15_connected || pa1010d_connected)) {
    Serial.print(F("None"));
  }
  Serial.println();
}