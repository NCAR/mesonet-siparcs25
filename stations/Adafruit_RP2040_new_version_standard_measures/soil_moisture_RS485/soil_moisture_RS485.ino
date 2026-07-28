// soil moisture (SEN0601) for RP2040 Feather, via SerialPIO on A0/A1
// Grove RS485 TX -> A0, Grove RS485 RX -> A1 (physical wiring)

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

bool readSoilData(float* moisturePctOut, float* temperatureCOut,
                   uint16_t* conductivityOut, uint16_t* salinityOut,
                   uint16_t* tdsOut) {
  // Registers 0x0000-0x0004: moisture, temperature, conductivity, salinity, TDS
  constexpr uint8_t registerCount = 5;
  constexpr size_t expectedLength = 15; // addr+func+bytecount(3) + 5*2 data + 2 crc

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

  if (response[2] != 0x0A) {  // 5 registers * 2 bytes = 10 = 0x0A
    Serial.println("Incorrect Modbus byte count");
    return false;
  }

  const uint16_t receivedCrc =
      static_cast<uint16_t>(response[13]) |
      (static_cast<uint16_t>(response[14]) << 8);

  const uint16_t calculatedCrc =
      modbus_crc16(response, 13);

  if (receivedCrc != calculatedCrc) {
    Serial.print("CRC error. Received: 0x");
    Serial.print(receivedCrc, HEX);
    Serial.print(" Calculated: 0x");
    Serial.println(calculatedCrc, HEX);
    return false;
  }

  const uint16_t regMoisture =
      (static_cast<uint16_t>(response[3]) << 8) | response[4];

  const uint16_t regTempRaw =
      (static_cast<uint16_t>(response[5]) << 8) | response[6];

  const uint16_t regConductivity =
      (static_cast<uint16_t>(response[7]) << 8) | response[8];

  const uint16_t regSalinity =
      (static_cast<uint16_t>(response[9]) << 8) | response[10];

  const uint16_t regTds =
      (static_cast<uint16_t>(response[11]) << 8) | response[12];

  // Temperature register is a signed 16-bit value (two's complement),
  // e.g. 0xFF9B -> -101 -> -10.1 C
  const int16_t tempSigned = static_cast<int16_t>(regTempRaw);

  const float moisturePct = regMoisture / 10.0f;
  const float temperatureC = tempSigned / 10.0f;

  Serial.print("Register 0, moisture raw: ");
  Serial.println(regMoisture);

  Serial.print("Register 1, temperature raw: ");
  Serial.println(regTempRaw);

  Serial.print("Register 2, conductivity: ");
  Serial.println(regConductivity);

  Serial.print("Register 3, salinity: ");
  Serial.println(regSalinity);

  Serial.print("Register 4, TDS: ");
  Serial.println(regTds);

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
  *conductivityOut = regConductivity;
  *salinityOut = regSalinity;
  *tdsOut = regTds;

  return true;
}

void setup() {
  Serial.begin(115200);

  while (!Serial && millis() < 5000) {
  }

  // SEN0601 default: 9600 baud, 8 data bits, NO parity, 1 stop bit (8N1).
  // This differs from the WS302, which requires 8E1.
  soilSerial.begin(SOIL_BAUD, SERIAL_8N1);

  Serial.println();
  Serial.println("SEN0601 Grove RS485 test");
  Serial.println("Expected response: 15 bytes beginning 01 03 0A");
  delay(2000);
}

void loop() {
  float moisturePct = 0.0f;
  float temperatureC = 0.0f;
  uint16_t conductivity = 0;
  uint16_t salinity = 0;
  uint16_t tds = 0;

  if (readSoilData(&moisturePct, &temperatureC, &conductivity, &salinity, &tds)) {
    Serial.print("Soil moisture: ");
    Serial.print(moisturePct, 1);
    Serial.print(" % | Temp: ");
    Serial.print(temperatureC, 1);
    Serial.print(" C | EC: ");
    Serial.print(conductivity);
    Serial.print(" uS/cm | Salinity: ");
    Serial.print(salinity);
    Serial.print(" | TDS: ");
    Serial.println(tds);
  } else {
    Serial.println("Soil reading failed");
  }

  Serial.println();
  delay(1000);
}
