/*

    IoTwx_Base.ino

    Atmospheric measurement node with
    the Adafruit chips:

      bme680   (thpvoc)
      rg15     (precipitation)
      sen0321  (ozone)
      ms8607   (thp)
      pmsa003i (air quality)
      scd4x    (true co2)
      ltr390   (uva+b)
      sht40    (th)

    ===
    This code sleeps for 60s, wakes up, takes a measurement,
    transmits and then goes back to sleep.

    copyright (c) 2020-2023 keith maull
    Website    :
    Author     : kmaull-ucar
    Create Time:
    Change Log :
      5/26 == removed seeed/grove code, inserted qwiic/adafruit

*/
#include <WiFi.h>
#include <SPI.h>
#include <Arduino.h>
#include <cmath>
#include "FS.h"
#include <LittleFS.h>
#include "SPIFFS.h"
#include <Adafruit_Sensor.h>
#include "Adafruit_BME680.h"
#include "Adafruit_MS8607.h"
#include "Adafruit_PM25AQI.h"
#include "Adafruit_LTR390.h"
#include <SensirionI2cScd4x.h>
#include "Adafruit_SHT4x.h"
#include <Adafruit_HDC302x.h>
#include "IoTwx.h"  /// https://github.com/ncar/esp32-atomlite-arduino-iotwx
#include <SoftwareSerial.h>
#include "rg15arduino.h"
#include "DFRobot_OzoneSensor.h"
#include "SparkFun_Qwiic_Relay.h"
#include <HTTPClient.h>
#include <NetworkClientSecure.h>
#include <ArduinoJson.h>

#define IOTWX_VERSION "2.0.4"
#define FORMAT_LITTLEFS_IF_FAILED true

// POE HAT GPIO PINS
#define SCK 22
#define MISO 23
#define MOSI 33
#define CS 19

#define HDC302X_IIC_ADDR uint8_t(0x44)
#define BMEX80_IIC_ADDR uint8_t(0x76)
#define SEN0321_IIC_ADDR uint8_t(0x73)
#define SEN0321_SAMPLES 20

#define SEALEVELPRESSURE_HPA (1013.25)
#define RELAY_ADDR 0x18  // Alternate address 0x19

// ATOMIC PortABC Extension Base — Port C (UART1) = Soil SEN0601, 8N1
#define SOIL_RX_PIN 19
#define SOIL_TX_PIN 22
#define SOIL_SLAVE_ADDR 0x01
#define SOIL_BAUD 9600

// ATOMIC PortABC Extension Base — Port B (UART2) = WS302 Wind, 8E1
#define WIND_RX_PIN 33
#define WIND_TX_PIN 23
#define WIND_SLAVE_ADDR 0x01   // confirm this matches your WS302's address
#define WIND_BAUD 9600

Qwiic_Relay aspirator_relay(RELAY_ADDR);

// FILE SCOPE
IoTwx node;
Adafruit_BME680 bme680;
Adafruit_PM25AQI aqi = Adafruit_PM25AQI();
SensirionI2cScd4x scd4x;
Adafruit_LTR390 ltr = Adafruit_LTR390();
Adafruit_SHT4x sht4 = Adafruit_SHT4x();
Adafruit_HDC302x hdc3022 = Adafruit_HDC302x();
SoftwareSerial atomUART;  // RX, TX
RG15Arduino rg15;
DFRobot_OzoneSensor sen0321;
Adafruit_MS8607 ms8607;

HardwareSerial soilSerial(1);   // UART1 -> Port C
HardwareSerial windSerial(2);   // UART2 -> Port B

unsigned long last_millis = 0;
unsigned long start_millis = 0;

// DEVICES ATTACHED
bool bme680_attached = false;
bool pm25aqi_attached = false;
bool scd4x_attached = false;
bool ltr390_attached = false;
bool sht4x_attached = false;
bool rg15_attached = false;
bool sen0321_attached = false;
bool ms8607_attached = false;
bool hdc3022_attached = false;
bool soil_attached = false;
bool wind_attached = false;

char *sensor;
char *topic;
char *atom_gpio_config;
int timezone;
int reset_interval;
int publish_interval;
int use_wifi;
int max_frequency = 80;
int aspirated;
int aspiration_spinup_time;
char *transfer_mode;


uint16_t modbus_crc16(const uint8_t* data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t position = 0; position < length; position++) {
    crc ^= static_cast<uint16_t>(data[position]);
    for (uint8_t bit = 0; bit < 8; bit++) {
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

bool readSoilData(float* moisturePctOut, float* temperatureCOut) {
  constexpr uint8_t registerCount = 2;
  constexpr size_t expectedLength = 9;  // addr+func+bytecount + 2*2 data + 2 crc

  uint8_t request[8] = {
    SOIL_SLAVE_ADDR, 0x03,
    0x00, 0x00,
    0x00, registerCount,
    0x00, 0x00
  };

  const uint16_t requestCrc = modbus_crc16(request, 6);
  request[6] = static_cast<uint8_t>(requestCrc & 0xFF);
  request[7] = static_cast<uint8_t>((requestCrc >> 8) & 0xFF);

  while (soilSerial.available() > 0) soilSerial.read();

  soilSerial.write(request, sizeof(request));
  soilSerial.flush();

  uint8_t response[expectedLength] = {};
  size_t length = 0;
  const uint32_t startTime = millis();

  while ((millis() - startTime) < 400) {
    while (soilSerial.available() > 0 && length < expectedLength) {
      response[length++] = static_cast<uint8_t>(soilSerial.read());
    }
    if (length == expectedLength) break;
    if (length == 5 && response[0] == SOIL_SLAVE_ADDR && (response[1] & 0x80)) break;
  }

  if (length != expectedLength || response[0] != SOIL_SLAVE_ADDR ||
      response[1] != 0x03 || response[2] != 0x04) {
    Serial.println("[warn]: soil sensor bad response");
    return false;
  }

  const uint16_t receivedCrc = static_cast<uint16_t>(response[7]) | (static_cast<uint16_t>(response[8]) << 8);
  const uint16_t calculatedCrc = modbus_crc16(response, 7);
  if (receivedCrc != calculatedCrc) {
    Serial.println("[warn]: soil sensor CRC mismatch");
    return false;
  }

  // Per DFRobot SEN0600: register 0 = humidity, register 1 = temperature
  const uint16_t regHumidity = (static_cast<uint16_t>(response[3]) << 8) | response[4];
  const uint16_t regTempRaw  = (static_cast<uint16_t>(response[5]) << 8) | response[6];

  const int16_t tempSigned = static_cast<int16_t>(regTempRaw);
  const float moisturePct = regHumidity / 10.0f;
  const float temperatureC = tempSigned / 10.0f;

  if (!isfinite(moisturePct) || moisturePct < 0.0f || moisturePct > 100.0f) return false;
  if (!isfinite(temperatureC) || temperatureC < -40.0f || temperatureC > 80.0f) return false;

  *moisturePctOut = moisturePct;
  *temperatureCOut = temperatureC;

  return true;
}

void publish_soil_measurements() {
  char s[strlen(sensor) + 64];
  float moisturePct, temperatureC;

  if (readSoilData(&moisturePct, &temperatureC)) {
    Serial.print("[info]: soil moisture=");
    Serial.print(moisturePct, 1);
    Serial.print("% temp=");
    Serial.print(temperatureC, 1);
    Serial.println("C");

    strcpy(s, sensor); strcat(s, "/sen0600/moisture");
    node.publishMQTTMeasurement(topic, s, moisturePct, 0);

    strcpy(s, sensor); strcat(s, "/sen0600/temperature");
    node.publishMQTTMeasurement(topic, s, temperatureC, 0);
  } else {
    Serial.println("[error]: soil measurement failed");
  }
}

bool readWindData(float* speedMs, uint16_t* directionDeg) {
  constexpr uint8_t registerCount = 4;
  constexpr size_t expectedLength = 13;

  uint8_t request[8] = {
    WIND_SLAVE_ADDR, 0x03,
    0x00, 0x00,
    0x00, registerCount,
    0x00, 0x00
  };

  const uint16_t requestCrc = modbus_crc16(request, 6);
  request[6] = static_cast<uint8_t>(requestCrc & 0xFF);
  request[7] = static_cast<uint8_t>((requestCrc >> 8) & 0xFF);

  while (windSerial.available() > 0) windSerial.read();

  windSerial.write(request, sizeof(request));
  windSerial.flush();

  uint8_t response[expectedLength] = {};
  size_t length = 0;
  const uint32_t startTime = millis();

  while ((millis() - startTime) < 400) {
    while (windSerial.available() > 0 && length < expectedLength) {
      response[length++] = static_cast<uint8_t>(windSerial.read());
    }
    if (length == expectedLength) break;
    if (length == 5 && response[0] == WIND_SLAVE_ADDR && (response[1] & 0x80)) break;
  }

  Serial.print("[debug]: wind RX (");
  Serial.print(length);
  Serial.print(" bytes): ");
  for (size_t i = 0; i < length; i++) {
    if (response[i] < 0x10) Serial.print('0');
    Serial.print(response[i], HEX);
    Serial.print(' ');
  }
  Serial.println();

  if (length != expectedLength || response[0] != WIND_SLAVE_ADDR ||
      response[1] != 0x03 || response[2] != 0x08) {
    Serial.println("[warn]: wind sensor bad response");
    return false;
  }

  const uint16_t receivedCrc = static_cast<uint16_t>(response[11]) | (static_cast<uint16_t>(response[12]) << 8);
  const uint16_t calculatedCrc = modbus_crc16(response, 11);
  if (receivedCrc != calculatedCrc) {
    Serial.println("[warn]: wind sensor CRC mismatch");
    return false;
  }

  const uint16_t reg1 = (static_cast<uint16_t>(response[5]) << 8) | response[6];
  const uint16_t reg2 = (static_cast<uint16_t>(response[7]) << 8) | response[8];
  const uint16_t reg3 = (static_cast<uint16_t>(response[9]) << 8) | response[10];

  const uint32_t speedBits = (static_cast<uint32_t>(reg3) << 16) | static_cast<uint32_t>(reg2);

  float decodedSpeed = 0.0f;
  memcpy(&decodedSpeed, &speedBits, sizeof(decodedSpeed));

  if (!isfinite(decodedSpeed) || decodedSpeed < 0.0f || decodedSpeed > 100.0f) {
    Serial.println("[warn]: invalid wind-speed value");
    return false;
  }

  if (reg1 > 359) {
    Serial.println("[warn]: invalid wind-direction value");
    return false;
  }

  *speedMs = decodedSpeed;
  *directionDeg = reg1;

  return true;
}

void publish_wind_measurements() {
  char s[strlen(sensor) + 64];
  float speedMs = 0.0f;
  uint16_t directionDeg = 0;

  if (readWindData(&speedMs, &directionDeg)) {
    Serial.print("[info]: wind speed=");
    Serial.print(speedMs, 3);
    Serial.print("m/s dir=");
    Serial.println(directionDeg);
    strcpy(s, sensor); strcat(s, "/ws302/speed");
    node.publishMQTTMeasurement(topic, s, speedMs, 0);

    // calm-wind suppression, same convention as your mesonet firmware
    if (speedMs >= 0.2f) {
      strcpy(s, sensor); strcat(s, "/ws302/direction");
      node.publishMQTTMeasurement(topic, s, directionDeg, 0);
    }
  } else {
    Serial.println("[error]: wind measurement failed");
  }
}

void publish_ltr390_measurements() {
  char s[strlen(sensor) + 64];

  if (ltr.newDataAvailable()) {
    strcpy(s, sensor);
    strcat(s, "/ltr390/uvs");
    node.publishMQTTMeasurement(topic, s, ltr.readUVS(), 0);
  }
}


void publish_hdc3022_measurements() {
  char s[strlen(sensor) + 64];

  double temp = -999;
  double humidity = -999;

  hdc3022.readTemperatureHumidityOnDemand(temp, humidity, TRIGGERMODE_LP0);

  if (temp != -999) {
    strcpy(s, sensor);
    strcat(s, "/hdc3022/temperature");
    node.publishMQTTMeasurement(topic, s, temp, 0);
  }

  if (humidity != -999) {
    strcpy(s, sensor);
    strcat(s, "/hdc3022/humidity");
    node.publishMQTTMeasurement(topic, s, humidity, 0);
  }

}


void publish_scd4x_measurements() {
  char s[strlen(sensor) + 64];
  uint16_t co2;
  float temperature;
  float humidity;
  uint16_t scd4x_error;

  scd4x.begin(Wire, SCD41_I2C_ADDR_62);
  delay(5000);
  scd4x_error = scd4x.readMeasurement(co2, temperature, humidity);

  if (scd4x_error) {
    Serial.print("[error]: scd4x error trying to execute readMeasurement(): ");
  } else if (co2 == 0) {
    Serial.println("[warn]: scd4x invalid sample detected, skipping.");
  } else {
    strcpy(s, sensor);
    strcat(s, "/scd4x/co2");
    node.publishMQTTMeasurement(topic, s, co2, 0);

    strcpy(s, sensor);
    strcat(s, "/scd4x/temperature");
    node.publishMQTTMeasurement(topic, s, temperature, 0);

    strcpy(s, sensor);
    strcat(s, "/scd4x/humidity");
    node.publishMQTTMeasurement(topic, s, humidity, 0);
  }
}


void publish_rg15_measurements() {
  char s[strlen(sensor) + 64];

  delay(5000);

  if (rg15.poll()) {
    strcpy(s, sensor);
    strcat(s, "/rg15/acc");
    node.publishMQTTMeasurement(topic, s, rg15.acc, 0);

    strcpy(s, sensor);
    strcat(s, "/rg15/acc_evt");
    node.publishMQTTMeasurement(topic, s, rg15.eventAcc, 0);

    strcpy(s, sensor);
    strcat(s, "/rg15/acc_tot");
    node.publishMQTTMeasurement(topic, s, rg15.totalAcc, 0);

    strcpy(s, sensor);
    strcat(s, "/rg15/iph");
    node.publishMQTTMeasurement(topic, s, rg15.rInt, 0);
  } else {
    Serial.println("[error]: RG15 measurement timeout, no measurement obtained");
  }
}


void publish_sht4x_measurements() {
  char s[strlen(sensor) + 64];
  sensors_event_t humidity, temp;

  delay(1500);

  sht4.getEvent(&humidity, &temp);

  strcpy(s, sensor);
  strcat(s, "/sht4x/temperature");
  node.publishMQTTMeasurement(topic, s, temp.temperature, 0);

  strcpy(s, sensor);
  strcat(s, "/sht4x/humidity");
  node.publishMQTTMeasurement(topic, s, humidity.relative_humidity, 0);
  //     } else {
  //       Serial.println("[error]: SHT4x sensor data invalid or not ready");
  //     }
  //   } else {
  //     Serial.println("[error]: SHT4x sensor failed to read data");
  //   }
}


void publish_pmsa0031_measurements() {
  PM25_AQI_Data data;
  char s[strlen(sensor) + 64];

  if (!aqi.read(&data)) {
    Serial.println("[warn] could not read from AQI");
    delay(500);
    return;
  }

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/pm10standard");
  node.publishMQTTMeasurement(topic, s, data.pm10_standard, 0);

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/pm25standard");
  node.publishMQTTMeasurement(topic, s, data.pm25_standard, 0);

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/pm100standard");
  node.publishMQTTMeasurement(topic, s, data.pm100_standard, 0);

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/pm10env");
  node.publishMQTTMeasurement(topic, s, data.pm10_env, 0);

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/pm25env");
  node.publishMQTTMeasurement(topic, s, data.pm25_env, 0);

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/pm100env");
  node.publishMQTTMeasurement(topic, s, data.pm100_env, 0);

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/partcount03um");
  node.publishMQTTMeasurement(topic, s, data.particles_03um, 0);

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/partcount05um");
  node.publishMQTTMeasurement(topic, s, data.particles_05um, 0);

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/partcount10um");
  node.publishMQTTMeasurement(topic, s, data.particles_10um, 0);

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/partcount25um");
  node.publishMQTTMeasurement(topic, s, data.particles_25um, 0);

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/partcount50um");
  node.publishMQTTMeasurement(topic, s, data.particles_50um, 0);

  strcpy(s, sensor);
  strcat(s, "/pmsa003i/partcount100um");
  node.publishMQTTMeasurement(topic, s, data.particles_100um, 0);
}


void publish_sen0321_measurements() {
  char s[strlen(sensor) + 64];

  int16_t ozoneConcentration = sen0321.readOzoneData(SEN0321_SAMPLES);

  strcpy(s, sensor);
  strcat(s, "/sen031/ozone");
  node.publishMQTTMeasurement(topic, s, ozoneConcentration, 0);
}


void publish_ms8607_measurements() {
  sensors_event_t temp, pressure, humidity;
  char s[strlen(sensor) + 64];

  ms8607.getEvent(&pressure, &temp, &humidity);

  strcpy(s, sensor);
  strcat(s, "/ms8607/temperature");
  node.publishMQTTMeasurement(topic, s, temp.temperature, 0);

  strcpy(s, sensor);
  strcat(s, "/ms8607/humidity");
  node.publishMQTTMeasurement(topic, s, humidity.relative_humidity, 0);

  strcpy(s, sensor);
  strcat(s, "/ms8607/pressure");
  node.publishMQTTMeasurement(topic, s, pressure.pressure, 0);
}


void publish_bme680_measurements() {
  char s[strlen(sensor) + 64];

  if (!bme680.performReading()) {
    Serial.println("[FAIL] Failed to perform BME680 reading.");
    blink_led(LED_FAIL, LED_FAST);
    return;
  }

  strcpy(s, sensor);
  strcat(s, "/bme680/temperature");
  node.publishMQTTMeasurement(topic, s, bme680.temperature, 0);

  strcpy(s, sensor);
  strcat(s, "/bme680/pressure");
  node.publishMQTTMeasurement(topic, s, bme680.pressure, 0);

  strcpy(s, sensor);
  strcat(s, "/bme680/humidity");
  node.publishMQTTMeasurement(topic, s, bme680.humidity, 0);

  strcpy(s, sensor);
  strcat(s, "/bme680/voc");
  node.publishMQTTMeasurement(topic, s, bme680.gas_resistance, 0);

  strcpy(s, sensor);
  strcat(s, "/bme680/altitude");
  node.publishMQTTMeasurement(topic, s, bme680.readAltitude(SEALEVELPRESSURE_HPA), 0);

  delay(2000);
}


void start_aspiration() {
  aspirator_relay.turnRelayOn();
  delay(aspiration_spinup_time * 1000);
}


void stop_aspiration() {
  delay(2000);
  aspirator_relay.turnRelayOff();
}


void setup() {
  File file;
  StaticJsonDocument<1024> doc;
  char uuid[32];
  uint16_t scd4x_error;
  bool i2c_device_connected = false;
  bool rg15_poe_bypass = false;
  String mac = String((uint32_t)ESP.getEfuseMac(), HEX);

  strcpy(uuid, "ESP32P_AtomLite_");
  strcat(uuid, (const char *)mac.c_str());

  // initialize serial
  Serial.begin(115200);

  Serial.println();
  Serial.println();
  Serial.println();
  Serial.print("[info] This is the IoTwx v");
  Serial.println(IOTWX_VERSION);
  delay(500);
  Serial.println("[info] initializing now ...");

  start_millis = millis();
  init_led();  // set up AtomLite LED

  if (!LittleFS.begin(FORMAT_LITTLEFS_IF_FAILED)) {
    Serial.println("[info] LittleFS mount failed ... HALTING");
    while (1) {
      delay(15000);
      blink_led(LED_FAIL, LED_FAST);
	 	  // reboot
	};
  }


  ///////////////////////////////////////////////////////////////////////////
  // Serial.println("[info] LittleFS Mounted Successfully");
  // file = LittleFS.open("/config.json", FILE_READ);

  // if (file) {
  //   deserializeJson(doc, file);
  //   file.close();

  //   String output;
  //   serializeJson(doc, output);
  //   Serial.println("[info]: reading serialized json");
  //   Serial.println(output);

  //   if (output == "null") {
  //     Serial.println("[error]: config.json was empty: HALTING");
  //     while(1) {
  //       delay(15000);
  //       blink_led(LED_FAIL, LED_FAST);
  //       // reboot
  //     };
  //   } else if (doc.containsKey("iotwx_local_config")) {
	  // CONSIDER -> if the data already exists, don't store it again
    /////////////////////////////////////////////////////////////////////////

  Serial.println("[info] LittleFS Mounted Successfully");

  // --- TEMPORARY TEST HARDCODE: bypass config.json file read ---
  const char* test_config = R"({
    "iotwx_gpio_config": "A",
    "iotwx_use_wifi": "1",
    "iotwx_poe_mac": "0xFFFFFFFFFFFF",
    "iotwx_local_config": "1",
    "iotwx_id": "m5atom/esp32/aabbffee",
    "iotwx_mq_ip": "iotwx.ucar.edu",
    "iotwx_mq_port": "1883",
    "iotwx_publish_interval": "2",
    "iotwx_reset_interval": "360",
    "iotwx_sensor": "grove/i2c",
    "iotwx_timezone": "21600",
    "iotwx_wifi_pwd": "MaRTiny123",
    "iotwx_wifi_ssid": "Pouya's iPhone",
    "iotwx_topic": "ncar/iotwx/co/boulder/ML_test_000",
    "iotwx_max_frequency": "80",
    "iotwx_aspiration_spinup_time": "10"
  })";

  deserializeJson(doc, test_config);
  bool file_ok = true;
  // --- END TEMPORARY TEST HARDCODE ---

  if (file_ok) {
    String output;
    serializeJson(doc, output);
    Serial.println("[info]: reading serialized json");
    Serial.println(output);

    if (output == "null") {
        Serial.println("[error]: config.json was empty: HALTING");
        while(1) {
            delay(15000);
            blink_led(LED_FAIL, LED_FAST);
        };
    } else if (doc.containsKey("iotwx_local_config")) {
      Serial.println("[info] LOCAL config storing to NVS");
      store_data_to_nvs("iotwx_mq_port", (const char *)doc["iotwx_mq_port"]);
      store_data_to_nvs("iotwx_mq_ip", (const char *)doc["iotwx_mq_ip"]);
      store_data_to_nvs("iotwx_wifi_ssid", (const char *)doc["iotwx_wifi_ssid"]);
      store_data_to_nvs("iotwx_wifi_pwd", (const char *)doc["iotwx_wifi_pwd"]);
      store_data_to_nvs("iotwx_id", (const char *)doc["iotwx_id"]);
      Serial.println("[info]: LOCAL config stored to NVS");

	  // initialize the node
	  node = IoTwx(true);
      Serial.println("[info]: IoTwx node initialized");
    }

	Serial.println("[info]: reading deserialized data");
	timezone = atoi((const char *)doc["iotwx_timezone"]);
	sensor = strdup((const char *)doc["iotwx_sensor"]);
	topic = strdup((const char *)doc["iotwx_topic"]);
	reset_interval = 1000 * 60 * atoi((const char *)doc["iotwx_reset_interval"]);
	publish_interval = atoi((const char *)doc["iotwx_publish_interval"]);
	max_frequency = atoi((const char *)doc["iotwx_max_frequency"]);
	atom_gpio_config = strdup((const char *)doc["iotwx_gpio_config"]);
	use_wifi = atoi((const char *)doc["iotwx_use_wifi"]);
	aspiration_spinup_time = atoi((const char *)doc["iotwx_aspiration_spinup_time"]);

    // set wifi or POE
    node.setWifi(use_wifi == 1);

    if (!use_wifi) {
      byte poe_mac[] = { 0x02, 0xAD, 0x74, 0x7B, 0xED, 0x2B };
      node.setPoEMAC(poe_mac);
      Serial.print("[info]: POE mode with MAC (");
      Serial.print("");
      Serial.println(")");
    }

    Serial.println();

    // initialize the I2C bus
    if (strcmp(atom_gpio_config, "A") == 0) {
      atomUART.begin(9600, SWSERIAL_8N1, 32, 26);
      rg15.setStream(&atomUART);

      Serial.println("[info]: GPIO_config is A\n[info]: OK Found RG15 on Grove, using pins 21,25 for I2C");
      blink_led(LED_OK, LED_SLOW);
      rg15_attached = true;

      // we can allow rg15 connectivity to be a bypass condition
      if (!use_wifi) {
        rg15_poe_bypass = true;
      }
      Serial.print("[info]: M5Stack POE bypass (RG15) : ");
      Serial.println(rg15_poe_bypass);

      // set i2c to other pins on gpio
      Wire.begin(25, 21, 10000);
    } else {
      Serial.println("[info]: GPIO_config is not A, using pins 26,32 (Grove) for I2C");

      Wire.begin(26, 32, 10000);
      Serial.println("");
    }

    // set up aspiration fan
    aspirated = aspirator_relay.begin();
    if (aspirated) stop_aspiration();
    if (aspirated) Serial.println("[info]: OK aspiration fan found");

    // check for i2c device connectivity, once then check for rg15 bypass
    do {
      /// Adafruit bme680 TPHVOC >> https://www.adafruit.com/product/3660
      if (!bme680.begin()) {
        Serial.println("[warn]: Could not find Adafruit BME680 sensor. Check your connections and verify the address 0x76 is correct.");
        blink_led(LED_FAIL, LED_FAST);
      } else {
        bme680_attached = true;
        i2c_device_connected = true;

        Serial.println("[info]: OK Found Adafruit BME680");
        blink_led(LED_OK, LED_SLOW);

        // Set up oversampling and filter initialization
        bme680.setTemperatureOversampling(BME680_OS_8X);
        bme680.setHumidityOversampling(BME680_OS_2X);
        bme680.setPressureOversampling(BME680_OS_4X);
        bme680.setIIRFilterSize(BME680_FILTER_SIZE_3);
        bme680.setGasHeater(320, 150);  // 320*C for 150 ms
      }

      /// Adafruit ms8607 TPH >> https://www.adafruit.com/product/4716
      if (bme680_attached || !ms8607.begin()) {
        Serial.println("[warn]: Could not find Adafruit MS8607 sensor or BME680 is attached already on address 0x76. Check your connections and verify the address 0x76 is correct.");
        blink_led(LED_FAIL, LED_FAST);
      } else {
        ms8607_attached = true;
        i2c_device_connected = true;

        Serial.println("[info]: OK Found Adafruit MS8607");
        blink_led(LED_OK, LED_SLOW);

        ms8607.setHumidityResolution(MS8607_HUMIDITY_RESOLUTION_OSR_12b);
        ms8607.setPressureResolution(MS8607_PRESSURE_RESOLUTION_OSR_4096);
      }

      /// Adafruit hdc3022 TH >> https://www.adafruit.com/product/5989
      if (!hdc3022.begin(HDC302X_IIC_ADDR, &Wire)) {
        Serial.println("[warn]: Could not find HDC3022 sensor. Check your connections and verify the address 0x44 is correct.");
        blink_led(LED_FAIL, LED_FAST);
      } else {
          hdc3022_attached = true;
          i2c_device_connected = true;

          Serial.println("[info]: OK Found Adafruit HDC3022");
          blink_led(LED_OK, LED_SLOW);
      }

      /// Adafruit sht41 TH >> https://www.adafruit.com/product/5776
      if (hdc3022_attached || !sht4.begin()) {
        Serial.println("[warn]: Could not find Adafruit SHT4X Adafruit Temp/Humidity sensor or HDC3022 is already attached on Address 0x44. Check your connections and verify the address 0x44 is correct.");
        blink_led(LED_FAIL, LED_FAST);
      } else {
        sht4.setHeater(SHT4X_NO_HEATER);
        sht4.setPrecision(SHT4X_HIGH_PRECISION);

        sht4x_attached = true;
        i2c_device_connected = true;

        Serial.println("[info]: OK Found Adafruit SHT4x");
        blink_led(LED_OK, LED_SLOW);
      }

      /// Adafruit pmsa003i pm25/aqi >> https://www.adafruit.com/product/4632
      if (!aqi.begin_I2C()) {
        Serial.println("[warn]: Could not find Adafruit PMSA003I AQ sensor. Check your connections and verify the address 0x12 is correct.");
        blink_led(LED_FAIL, LED_FAST);
      } else {
        pm25aqi_attached = true;
        i2c_device_connected = true;

        Serial.println("[info]: OK Found Adafruit PM25AQI");
        blink_led(LED_OK, LED_SLOW);
      }

      /// Adafruit scd41 CO2 >> https://www.adafruit.com/product/5190
      scd4x.begin(Wire, SCD41_I2C_ADDR_62);
      scd4x_error = scd4x.stopPeriodicMeasurement();
      if (scd4x_error) {
        Serial.println("[error]: Error trying to execute stopPeriodicMeasurement(): ");
        blink_led(LED_FAIL, LED_FAST);
      } else {
        scd4x_attached = true;
        i2c_device_connected = true;

        Serial.println("[info]: OK Found Adafruit SCD4x");
        blink_led(LED_OK, LED_SLOW);
      }

      /// Adafruit ltr390 uv300-350nm >> https://www.adafruit.com/product/4831
      if (!ltr.begin()) {
        Serial.println("[error]: Couldn't find LTR390 sensor!");
        blink_led(LED_FAIL, LED_FAST);
      } else {
        Serial.println("[info]: OK Found LTR390 sensor");
        ltr.setResolution(LTR390_RESOLUTION_16BIT);
        ltr.setGain(LTR390_GAIN_3);
        ltr.setMode(LTR390_MODE_UVS);
        ltr.setThresholds(100, 1000);

        ltr390_attached = true;
        i2c_device_connected = true;
      }

      /// DF Robot sen0321 ozone >> https://wiki.dfrobot.com/Gravity_IIC_Ozone_Sensor_(0-10ppm)%20SKU_SEN0321
      int retry_count = 0;
      while (true) {
        if (retry_count < 5) {
          if (!sen0321.begin(SEN0321_IIC_ADDR)) {
            delay(1000);
            retry_count++;
          } else {
            sen0321_attached = true;
            i2c_device_connected = true;

            Serial.println("[info]: OK Found SEN0321 sensor");
            sen0321.setModes(MEASURE_MODE_PASSIVE);
            break;
          }
        } else {
          Serial.println("[warn]: Could not found SEN0321 sensor");
          break;
        }
      }
    } while (false);


    soilSerial.begin(SOIL_BAUD, SERIAL_8N1, SOIL_RX_PIN, SOIL_TX_PIN);
    soil_attached = true;
    Serial.println("[info]: OK soil sensor UART initialized on Port C");


    windSerial.begin(WIND_BAUD, SERIAL_8E1, WIND_RX_PIN, WIND_TX_PIN);
    wind_attached = true;
    Serial.println("[info]: OK wind sensor UART initialized on Port B");


    delay(1000);

    // begin shutdown sequence, downthrottle, shutdown wifi and BT
    btStop();
    Serial.println("[info]: BT disconnected for power reduction");
    setCpuFrequencyMhz(max_frequency);
    Serial.println();
    Serial.print("[info] CPU downthrottled to ");
    Serial.print(max_frequency);
    Serial.println("Mhz for power reduction");
    WiFi.mode(WIFI_OFF);
    Serial.println("[info] Wifi shut off for power reduction");
	  delay(1500);
  } else {
    Serial.println("[halt]: halting > configuration corrupt or missing");
    while (1){
		delay(15000);
		// RESTART
	}
   }
}


void loop() {
  if (millis() - last_millis > publish_interval * 60 * 1000) {
    Serial.println("[info]: measuring");

    last_millis = millis();

    // start measurements
    if (aspirated) start_aspiration();

    // connect to internet -> NOTE: ASPIRATION MUST OCCUR BEFORE THIS; MESSAGES WILL NOT RELAY; UNSURE WHY
    node.establishCommunications();

    // start measurements
    if (bme680_attached) publish_bme680_measurements();
    if (ms8607_attached) publish_ms8607_measurements();
    if (sht4x_attached) publish_sht4x_measurements();
    if (hdc3022_attached) publish_hdc3022_measurements();

    // stop fan
    if (aspirated) stop_aspiration();

    if (pm25aqi_attached) publish_pmsa0031_measurements();
    if (scd4x_attached) publish_scd4x_measurements();
    if (ltr390_attached) publish_ltr390_measurements();
    if (rg15_attached) publish_rg15_measurements();
    if (sen0321_attached) publish_sen0321_measurements();
    if (soil_attached) publish_soil_measurements();
    if (wind_attached) publish_wind_measurements();

    // cleanly disconnect MQTT before radio shutdown
    node.disconnectMQTT();

    // configure the timer to wake us up!
    delay(1000);
  }

  if (millis() - start_millis > reset_interval) esp_restart();

  Serial.println("[info]: sleeping");
  esp_sleep_enable_timer_wakeup(publish_interval * 60L * 1000000L);
  esp_light_sleep_start();
}
