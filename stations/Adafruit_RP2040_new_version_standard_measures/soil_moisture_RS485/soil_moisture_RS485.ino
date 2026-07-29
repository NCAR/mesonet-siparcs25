// soil moisture/temperature (SEN0600) for RP2040 Feather, via SerialPIO on A0/A1
// Grove RS485 TX -> A0, Grove RS485 RX -> A1 (physical wiring)
//
// NOTE: SEN0600 is a 2-in-1 sensor (humidity + temperature only).
// It does NOT measure conductivity, salinity, or TDS — that's the SEN0601,
// a different physical product. See DFRobot wiki: https://wiki.dfrobot.com/sen0600/

#include <cstring>
#include <cmath>
#include <SerialPIO.h>

#define SOIL_TX_PIN A1   // RP2040 transmits here -> goes to Grove RX
#define SOIL_RX_PIN A0   // RP2040 receives here <- comes from Grove TX
#define SOIL_SLAVE_ADDR 0x01
#define SOIL_BAUD 9600

// SerialPIO(txPin, rxPin)
SerialPIO soilSerial(SOIL_TX_PIN, SOIL_RX_PIN);

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
  // Registers 0x0000-0x0001: humidity, temperature (SEN0600 only exposes these two)
  constexpr uint8_t registerCount = 2;
  constexpr size_t expectedLength = 9; // addr+func+bytecount(3) + 2*2 data + 2 crc

  uint8_t request[8] = {
    SOIL_SLAVE_ADDR,
    0x03,
    0x00, 0x00,  // Starting register: 0
    0x00, registerCount,
    0x00, 0x00
  };

  const uint16_t requestCrc = modbus_crc16(request, 6);

  // Modbus CRC is transmitted low byte first.
  request[6] = static_cast<uint8_t>(requestCrc & 0xFF);
  request[7] = static_cast<uint8_t>((requestCrc >> 8) & 0xFF);

  // Remove any old bytes from the UART receive buffer.
  while (soilSerial.available() > 0) {
    soilSerial.read();
  }

  /*
    Grove RS485 has automatic direction control.
    Do not control DE or /RE manually.
  */
  soilSerial.write(request, sizeof(request));
  soilSerial.flush();

  uint8_t response[expectedLength] = {};
  size_t length = 0;
  const uint32_t startTime = millis();

  while ((millis() - startTime) < 400) {
    while (soilSerial.available() > 0 && length < expectedLength) {
      response[length++] =
          static_cast<uint8_t>(soilSerial.read());
    }

    if (length == expectedLength) {
      break;
    }

    // Modbus exception responses contain five bytes.
    if (length == 5 &&
        response[0] == SOIL_SLAVE_ADDR &&
        (response[1] & 0x80)) {
      break;
    }
  }

  Serial.print("RX (");
  Serial.print(length);
  Serial.print(" bytes): ");

  for (size_t i = 0; i < length; i++) {
    if (response[i] < 0x10) {
      Serial.print('0');
    }

    Serial.print(response[i], HEX);
    Serial.print(' ');
  }

  Serial.println();

  // Check for a Modbus exception response.
  if (length == 5 &&
      response[0] == SOIL_SLAVE_ADDR &&
      (response[1] & 0x80)) {

    const uint16_t receivedCrc =
        static_cast<uint16_t>(response[3]) |
        (static_cast<uint16_t>(response[4]) << 8);

    const uint16_t calculatedCrc =
        modbus_crc16(response, 3);

    if (receivedCrc == calculatedCrc) {
      Serial.print("Modbus exception code: 0x");

      if (response[2] < 0x10) {
        Serial.print('0');
      }

      Serial.println(response[2], HEX);
    } else {
      Serial.println("Invalid exception-response CRC");
    }

    return false;
  }

  if (length != expectedLength) {
    Serial.println("Incorrect response length");
    return false;
  }

  if (response[0] != SOIL_SLAVE_ADDR) {
    Serial.println("Incorrect slave address");
    return false;
  }

  if (response[1] != 0x03) {
    Serial.println("Incorrect Modbus function");
    return false;
  }

  if (response[2] != 0x04) {  // 2 registers * 2 bytes = 4 = 0x04
    Serial.println("Incorrect Modbus byte count");
    return false;
  }

  const uint16_t receivedCrc =
      static_cast<uint16_t>(response[7]) |
      (static_cast<uint16_t>(response[8]) << 8);

  const uint16_t calculatedCrc =
      modbus_crc16(response, 7);

  if (receivedCrc != calculatedCrc) {
    Serial.print("CRC error. Received: 0x");
    Serial.print(receivedCrc, HEX);
    Serial.print(" Calculated: 0x");
    Serial.println(calculatedCrc, HEX);
    return false;
  }

  // Per DFRobot SEN0600: register 0 = humidity, register 1 = temperature
  const uint16_t regHumidity =
      (static_cast<uint16_t>(response[3]) << 8) | response[4];

  const uint16_t regTempRaw =
      (static_cast<uint16_t>(response[5]) << 8) | response[6];

  // Temperature register is a signed 16-bit value (two's complement),
  // e.g. 0xFF9B -> -101 -> -10.1 C
  const int16_t tempSigned = static_cast<int16_t>(regTempRaw);

  const float moisturePct = regHumidity / 10.0f;
  const float temperatureC = tempSigned / 10.0f;

  Serial.print("Register 0, humidity raw: ");
  Serial.println(regHumidity);

  Serial.print("Register 1, temperature raw: ");
  Serial.println(regTempRaw);

  Serial.print("Decoded moisture: ");
  Serial.print(moisturePct, 1);
  Serial.println(" %RH");

  Serial.print("Decoded temperature: ");
  Serial.print(temperatureC, 1);
  Serial.println(" C");

  // Reject corrupted or unreasonable decoded values.
  if (!std::isfinite(moisturePct) ||
      moisturePct < 0.0f || moisturePct > 100.0f) {
    Serial.println("Invalid moisture value");
    return false;
  }

  if (!std::isfinite(temperatureC) ||
      temperatureC < -40.0f || temperatureC > 80.0f) {
    Serial.println("Invalid temperature value");
    return false;
  }

  *moisturePctOut = moisturePct;
  *temperatureCOut = temperatureC;

  return true;
}

void setup() {
  Serial.begin(115200);

  while (!Serial && millis() < 5000) {
  }

  // SEN0600 default: 9600 baud, 8 data bits, NO parity, 1 stop bit (8N1).
  // This differs from the WS302, which requires 8E1.
  soilSerial.begin(SOIL_BAUD, SERIAL_8N1);

  Serial.println();
  Serial.println("SEN0600 Grove RS485 test");
  Serial.println("Expected response: 9 bytes beginning 01 03 04");
  delay(2000);
}

void loop() {
  float moisturePct = 0.0f;
  float temperatureC = 0.0f;

  if (readSoilData(&moisturePct, &temperatureC)) {
    Serial.print("Soil moisture: ");
    Serial.print(moisturePct, 1);
    Serial.print(" % | Temp: ");
    Serial.print(temperatureC, 1);
    Serial.println(" C");
  } else {
    Serial.println("Soil reading failed");
  }

  Serial.println();
  delay(1000);
}
