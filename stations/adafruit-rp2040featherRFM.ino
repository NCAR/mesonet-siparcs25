// Feather9x_TX: LoRa transmitter for Adafruit Feather RP2040 RFM
// Sends sensor data with unique device_id, uses GPS time for timestamps when available
#include <SPI.h>
#include <RH_RF95.h>  // LoRa radio library
#include <Adafruit_Sensor.h>
#include "Adafruit_BME680.h"  // BME680 sensor
#include <Adafruit_TMP117.h>  // TMP117 sensor
#include "Adafruit_Si7021.h"  // Si7021 sensor
#include <ArduinoUniqueID.h>  // Unique device ID
#include "Adafruit_LTR390.h"  // LTR390 UV sensor
#include "Adafruit_PM25AQI.h" // PM25 air quality sensor
#include <SparkFun_I2C_GPS_Arduino_Library.h> // GPS module
#include <TinyGPSPlus.h>      // GPS parsing
#include <ArduinoJson.h>      // JSON formatting
#include <SensirionI2CScd4x.h> // SCD4x CO2 sensor

// Pin definitions for Feather RP2040 RFM
#define RFM95_CS   16  // Chip select for RFM95 LoRa
#define RFM95_INT  21  // Interrupt pin
#define RFM95_RST  17  // Reset pin

#define RF95_FREQ 915.0  // LoRa frequency (MHz)
#define SEALEVELPRESSURE_HPA (1013.25)  // Reference pressure for BME680
const double DEFAULT_LATITUDE = 39.97840783130492;
const double DEFAULT_LONGITUDE = -105.274898978223431;

// Hardware objects
RH_RF95 rf95(RFM95_CS, RFM95_INT);  // LoRa radio
Adafruit_Si7021 si7021;              // Si7021 sensor
Adafruit_BME680 bme680;              // BME680 sensor
Adafruit_TMP117 tmp117;              // TMP117 sensor
Adafruit_LTR390 ltr390;              // LTR390 sensor
Adafruit_PM25AQI pm25aqi;            // PM25 sensor
I2CGPS sparkfun_GPS;                 // GPS module
TinyGPSPlus gps;                    // GPS parser
SensirionI2CScd4x scd40;             // SCD40 sensor

// State variables
char device_id[64] = {0};            // Unique ID from ArduinoUniqueID
char assigned_edge_id[16] = {0};     // Assigned Pi's edge_id (e.g., "pi1")
unsigned long last_broadcast = 0;     // Last broadcast time for timeout

int led = LED_BUILTIN;               // Status LED
bool si7021_connected = false;       // Sensor connection flags
bool bme680_connected = false;
bool tmp117_connected = false;
bool ltr390_connected = false;
bool pm25aqi_connected = false;
bool sf_xa1110_connected = false;
bool scd40_connected = false;        // SCD40 connection flag

String get_gps_timestamp() {
  if (sf_xa1110_connected) {
    unsigned long start = millis();
    while (millis() - start < 500) {
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
      delay(50);
    }
  }
  return "";
}


// Initialize Sparkfun XA1110 GPS
bool sf_xa1110_gps_init() {
  if (!sparkfun_GPS.begin()) {
    Serial.println("[warn] Sparkfun XA1110 GPS Module not found.");
    return false;
  }
  Serial.println("[info] Sparkfun XA1110 GPS module found");
  return true;
}

// Initialize PM25AQI sensor
bool pm25aqi_init() {
  if (!pm25aqi.begin_I2C()) {
    Serial.println("[warn]: Couldn't find Adafruit PMSA003I AQ sensor.");
    return false;
  }
  Serial.println("[info]: Adafruit PM25AQI found ... OK");
  return true;
}

// Initialize BME680 sensor
bool bme680_init() {
  delay(500);
  if (!bme680.begin()) {
    Serial.println("[warn]: Couldn't find BME680 sensor");
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

// Initialize TMP117 sensor
bool tmp117_init() {
  delay(500);
  if (!tmp117.begin()) {
    Serial.println("[error]: Adafruit TMP117 qwiic sensor not found");
    return false;
  }
  Serial.println("[info]: Adafruit TMP117 qwiic sensor found ... OK");
  return true;
}

// Initialize Si7021 sensor
bool si7021_init() {
  delay(500);
  if (!si7021.begin()) {
    Serial.println("[error]: Adafruit si7021 qwiic sensor not found");
    return false;
  }
  Serial.print("[info]: Adafruit si7021 qwiic sensor found ... OK: model >>");
  switch (si7021.getModel()) {
    case SI_Engineering_Samples: Serial.print("SI engineering samples"); break;
    case SI_7013: Serial.print("Si7013"); break;
    case SI_7020: Serial.print("Si7020"); break;
    case SI_7021: Serial.print("Si7021"); break;
    default: Serial.print("Unknown");
  }
  Serial.print(" Rev("); Serial.print(si7021.getRevision()); Serial.print(")");
  Serial.print(" Serial #"); Serial.print(si7021.sernum_a, HEX); Serial.println(si7021.sernum_b, HEX);
  return true;
}

// Initialize LTR390 UV sensor
bool ltr390_init() {
  if (!ltr390.begin()) {
    Serial.println("[error]: Adafruit LTR390 qwiic sensor not found");
    return false;
  }
  Serial.println("[info]: Adafruit LTR390 qwiic sensor found ... OK");
  ltr390.setMode(LTR390_MODE_UVS);
  ltr390.setGain(LTR390_GAIN_3);
  ltr390.setResolution(LTR390_RESOLUTION_16BIT);
  ltr390.setThresholds(100, 1000);
  ltr390.configInterrupt(true, LTR390_MODE_UVS);
  return true;
}

// Initialize SCD40 CO2 sensor (Modified for single-shot mode)
bool scd40_init() {
  delay(100);
  scd40.begin(Wire);
  uint16_t error = scd40.stopPeriodicMeasurement(); // Ensure periodic mode is off
  if (error) {
    Serial.print("[warn]: Error stopping SCD40 periodic measurement: ");
    Serial.println(error);
  }
  Serial.println("[info]: Sensirion SCD40 sensor found ... OK (Single-shot mode)");
  return true;
}

// Blink LED for successful transmission
void blink_led() {
  digitalWrite(led, HIGH);
  delay(500);
  digitalWrite(led, LOW);
  delay(500);
}

// Initialize RFM95 LoRa pins
void rfm95_start() {
  pinMode(RFM95_RST, OUTPUT);
  pinMode(led, OUTPUT);
  digitalWrite(RFM95_RST, HIGH);
}

// Reset RFM95 radio
void rfm95_reset() {
  digitalWrite(RFM95_RST, LOW);
  delay(10);
  digitalWrite(RFM95_RST, HIGH);
  delay(10);
}

// Initialize RFM95 radio
bool rfm95_init() {
  if (!rf95.init()) {
    Serial.println("[warn]: LoRa radio init failed");
    return false;
  }
  Serial.println("[info] Adafruit RP2040-LoRa radio init OK!");
  if (!rf95.setFrequency(RF95_FREQ)) {
    Serial.println("[error] radio setFrequency() failed");
    while (1);
  }
  Serial.print("[info] radio frequency set to: "); Serial.println(RF95_FREQ);
  rf95.setTxPower(23, false);
  return true;
}

// Send LoRa packet
void rfm95_send(const char* packet) {
  Serial.print("[info]: sending packet >> "); Serial.println(packet);
  rf95.send((uint8_t*)packet, strlen(packet));
  rf95.waitPacketSent();
}

// Receive LoRa assignment messages
void rfm95_receive() {
  if (rf95.available()) {
    uint8_t buf[RH_RF95_MAX_MESSAGE_LEN];
    uint8_t len = sizeof(buf);
    if (rf95.recv(buf, &len)) {
      buf[len] = '\0';
      Serial.print("[info]: Received packet >> "); Serial.println((char*)buf);
      JsonDocument doc;
      DeserializationError error = deserializeJson(doc, (char*)buf);
      if (!error && doc["station_id"] == device_id && !doc["assigned_edge"].isNull()) {
        strncpy(assigned_edge_id, doc["assigned_edge"], sizeof(assigned_edge_id) - 1);
        assigned_edge_id[sizeof(assigned_edge_id) - 1] = '\0';
        Serial.print("[info]: Assigned to edge: "); Serial.println(assigned_edge_id);
        last_broadcast = millis();
      }
    }
  }
}

// Transmit PM25AQI measurements
bool pm25aqi_measure_transmit() {
  PM25_AQI_Data data;
  if (!pm25aqi.read(&data)) {
    Serial.println("[warn] could not read from AQI");
    return false;
  }
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[256];
  const char* measurements[] = {"pm10standard", "pm25standard", "pm100standard", "pm10env", "pm25env", "pm100env",
                               "partcount03um", "partcount05um", "partcount10um", "partcount25um", "partcount50um", "partcount100um"};
  int values[] = {data.pm10_standard, data.pm25_standard, data.pm100_standard, data.pm10_env, data.pm25_env, data.pm100_env,
                  data.particles_03um, data.particles_05um, data.particles_10um, data.particles_25um, data.particles_50um, data.particles_100um};
  for (int i = 0; i < 12; i++) {
    doc.clear();
    doc["station_id"] = device_id;
    if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
    doc["sensor"] = "pmsa003i";
    doc["measurement"] = measurements[i];
    doc["data"] = values[i];
    if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)) {
      doc["to_edge_id"] = assigned_edge_id;
    } 
    serializeJson(doc, packet);
    rfm95_send(packet);
    delay(50);
  }
  return true;
}

// Transmit LTR390 UV measurement
bool ltr390_measure_transmit() {
  if (!ltr390.newDataAvailable()) return false;
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[256];
  doc["station_id"] = device_id;
  if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
  doc["sensor"] = "ltr390";
  doc["measurement"] = "uv";
  doc["data"] = ltr390.readUVS();
  if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)) {
    doc["to_edge_id"] = assigned_edge_id;
  }
  serializeJson(doc, packet);
  rfm95_send(packet);
  return true;
}

// Transmit TMP117 temperature measurement
bool tmp117_measure_transmit() {
  sensors_event_t temp;
  tmp117.getEvent(&temp);
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[256];
  doc["station_id"] = device_id;
  if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
  doc["sensor"] = "tmp117";
  doc["measurement"] = "temperature";
  doc["data"] = temp.temperature;
  if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)) {
    doc["to_edge_id"] = assigned_edge_id;
  } 
  serializeJson(doc, packet);
  rfm95_send(packet);
  return true;
}

// Transmit Si7021 measurements
bool si7021_measure_transmit() {
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[256];
  doc["station_id"] = device_id;
  if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
  doc["sensor"] = "si7021";
  doc["measurement"] = "temperature";
  doc["data"] = si7021.readTemperature();
  if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)) {
    doc["to_edge_id"] = assigned_edge_id;
  } 
  serializeJson(doc, packet);
  rfm95_send(packet);
  delay(50);
  doc.clear();
  doc["station_id"] = device_id;
  if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
  doc["sensor"] = "si7021";
  doc["measurement"] = "humidity";
  doc["data"] = si7021.readHumidity();
  if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)) {
    doc["to_edge_id"] = assigned_edge_id;
  } 
  serializeJson(doc, packet);
  rfm95_send(packet);
  return true;
}

// Transmit BME680 measurements
bool bme680_measure_transmit() {
  if (!bme680.performReading()) {
    Serial.println("[error]: Failed to perform reading :(");
    return false;
  }
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[256];
  doc["station_id"] = device_id;
  if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
  doc["sensor"] = "bme680";
  doc["measurement"] = "temperature";
  doc["data"] = bme680.temperature;
  if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)) {
    doc["to_edge_id"] = assigned_edge_id;
  } 
  serializeJson(doc, packet);
  rfm95_send(packet);
  delay(50);
  doc.clear();
  doc["station_id"] = device_id;
  if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
  doc["sensor"] = "bme680";
  doc["measurement"] = "humidity";
  doc["data"] = bme680.humidity;
  if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)) {
    doc["to_edge_id"] = assigned_edge_id;
  } 
  serializeJson(doc, packet);
  rfm95_send(packet);
  delay(50);
  doc.clear();
  doc["station_id"] = device_id;
  if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
  doc["sensor"] = "bme680";
  doc["measurement"] = "pressure";
  doc["data"] = bme680.pressure / 100.0;
  if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)) {
    doc["to_edge_id"] = assigned_edge_id;
  } 
  serializeJson(doc, packet);
  rfm95_send(packet);
  return true;
}

// Transmit GPS measurement
bool sf_xa1110_measure_transmit() {
  while (sparkfun_GPS.available()) {
    gps.encode(sparkfun_GPS.read());
  }
  if (!gps.location.isValid()) {
    Serial.println(F("Location not yet valid"));
    return false;
  }
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[256];
  doc["station_id"] = device_id;
  if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
  doc["sensor"] = "sfxa1110";
  doc["measurement"] = "gps";
  if (sf_xa1110_connected && gps.location.isValid()) {
    doc["data"][0] = gps.location.lat();
    doc["data"][1] = gps.location.lng();
    doc["gps_module"] = "sf_xa1110";
    doc["gps_fix"] = true;
  } 
  else {
    doc["data"][0] = DEFAULT_LATITUDE;
    doc["data"][1] = DEFAULT_LONGITUDE;
    doc["gps_fix"] = false;
    doc["gps_module"] = "default";
  }
  if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)) {
    doc["to_edge_id"] = assigned_edge_id;
  }
  serializeJson(doc, packet);
  rfm95_send(packet);
  return true;
}


// State variables for SCD40 single-shot
uint32_t scd40_measure_start = 0;
bool scd40_measure_triggered = false;
const uint32_t SCD40_MEASURE_TIME = 5000; // 5 seconds

// Transmit SCD40 measurements (Non-blocking single-shot mode)
bool scd40_measure_transmit() {
  if (!scd40_measure_triggered) {
    uint16_t error = scd40.measureSingleShot();
    if (error) {
      Serial.print("[error]: Failed to trigger SCD40 measurement: ");
      Serial.println(error);
      return false;
    }
    scd40_measure_start = millis();
    scd40_measure_triggered = true;
    return false;
  }
  // Check if 5 seconds have passed
  if (millis() - scd40_measure_start < SCD40_MEASURE_TIME) {
    return false;
  }
  // Read measurement
  uint16_t co2 = 0;
  float temperature = 0.0f;
  float humidity = 0.0f;
  uint16_t error = scd40.readMeasurement(co2, temperature, humidity);
  if (error || co2 == 0) {
    Serial.print("[error]: Failed to read SCD40 measurement: ");
    Serial.println(error);
    scd40_measure_triggered = false;
    return true;
  }
  // Reset state
  scd40_measure_triggered = false;
  // Transmit data
  String timestamp = get_gps_timestamp();
  JsonDocument doc;
  char packet[256];
  // CO2 measurement
  doc["station_id"] = device_id;
  if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
  doc["sensor"] = "scd40";
  doc["measurement"] = "co2";
  doc["data"] = co2;
  if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)){
    doc["to_edge_id"] = assigned_edge_id;
  } 
  serializeJson(doc, packet);
  rfm95_send(packet);
  doc.clear();
  // Temperature measurement
  doc["station_id"] = device_id;
  if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
  doc["sensor"] = "scd40";
  doc["measurement"] = "temperature";
  doc["data"] = temperature;
  if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)){
    doc["to_edge_id"] = assigned_edge_id;
  } 
  serializeJson(doc, packet);
  rfm95_send(packet);
  doc.clear();
  // Humidity measurement
  doc["station_id"] = device_id;
  if (!timestamp.isEmpty()) doc["timestamp"] = timestamp;
  doc["sensor"] = "scd40";
  doc["measurement"] = "humidity";
  doc["data"] = humidity;
  if (strlen(assigned_edge_id) > 0 && (millis() - last_broadcast < 30000)){
    doc["to_edge_id"] = assigned_edge_id;
  } 
  serializeJson(doc, packet);
  rfm95_send(packet);
  return true;
}

// Setup: Initialize hardware and sensors
void setup() {
  delay(5000);
  Serial.begin(115200);
  delay(100);
  Serial.println("*** This is IoTwx-LoRa-RP2040 v0.1 ...");

  rfm95_start();
  rfm95_reset();
  rfm95_init();

  for (size_t i = 0; i < UniqueIDsize; i++) {
    sprintf(&device_id[i * 2], "%.2X", UniqueID[i]);
  }
  Serial.print("[info]: device_id ==> "); Serial.println(device_id);

  sf_xa1110_connected = sf_xa1110_gps_init();
  si7021_connected = si7021_init();
  bme680_connected = bme680_init();
  tmp117_connected = tmp117_init();
  ltr390_connected = ltr390_init();
  pm25aqi_connected = pm25aqi_init();
  scd40_connected = scd40_init();
}

// Loop: Check assignments, transmit sensor data
void loop() {
  rfm95_receive();
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
  if (sf_xa1110_connected) {
    transmit_ok = sf_xa1110_measure_transmit();
    if (transmit_ok) blink_led();
  }
  if (scd40_connected) {
    transmit_ok = scd40_measure_transmit();
    if (transmit_ok) blink_led();
  }
  delay(1000);
}