#include <cstring>

#define WIND_TX_PIN 24
#define WIND_RX_PIN 25
#define WIND_DE_PIN A0
#define WIND_SLAVE_ADDR 0x01
#define WIND_BAUD 9600

uint16_t modbus_crc16(const uint8_t* buf, int len) {
  uint16_t crc = 0xFFFF;

  for (int pos = 0; pos < len; pos++) {
    crc ^= static_cast<uint16_t>(buf[pos]);

    for (int i = 0; i < 8; i++) {
      if (crc & 1) {
        crc >>= 1;
        crc ^= 0xA001;
      } else {
        crc >>= 1;
      }
    }
  }

  return crc;
}

void rs485Transmit(bool enabled) {
  digitalWrite(WIND_DE_PIN, enabled ? HIGH : LOW);
  delayMicroseconds(50);
}

bool readWindData(float* speedMs, uint16_t* directionDeg) {
  constexpr uint8_t registerCount = 4;
  constexpr uint8_t expectedLength = 13;

  uint8_t request[8] = {
    WIND_SLAVE_ADDR,
    0x03,
    0x00, 0x00,  // Start at register 0
    0x00, registerCount,
    0x00, 0x00
  };

  uint16_t requestCrc = modbus_crc16(request, 6);
  request[6] = static_cast<uint8_t>(requestCrc & 0xFF);
  request[7] = static_cast<uint8_t>(requestCrc >> 8);

  while (Serial2.available()) {
    Serial2.read();
  }

  rs485Transmit(true);
  Serial2.write(request, sizeof(request));
  Serial2.flush();
  delayMicroseconds(200);
  rs485Transmit(false);

  uint8_t response[expectedLength];
  uint8_t length = 0;
  uint32_t start = millis();

  while ((millis() - start < 400) && length < expectedLength) {
    if (Serial2.available()) {
      response[length++] = static_cast<uint8_t>(Serial2.read());
    }
  }

  Serial.print("RX: ");

  for (uint8_t i = 0; i < length; i++) {
    if (response[i] < 0x10) {
      Serial.print('0');
    }

    Serial.print(response[i], HEX);
    Serial.print(' ');
  }

  Serial.println();

  if (length != expectedLength) {
    Serial.println("Incorrect response length");
    return false;
  }

  if (response[0] != WIND_SLAVE_ADDR ||
      response[1] != 0x03 ||
      response[2] != 0x08) {
    Serial.println("Invalid Modbus response");
    return false;
  }

  uint16_t receivedCrc =
      static_cast<uint16_t>(response[11]) |
      (static_cast<uint16_t>(response[12]) << 8);

  uint16_t calculatedCrc = modbus_crc16(response, 11);

  if (receivedCrc != calculatedCrc) {
    Serial.println("CRC error");
    return false;
  }

  uint16_t reg0 =
      (static_cast<uint16_t>(response[3]) << 8) |
      response[4];

  uint16_t reg1 =
      (static_cast<uint16_t>(response[5]) << 8) |
      response[6];

  uint16_t reg2 =
      (static_cast<uint16_t>(response[7]) << 8) |
      response[8];

  uint16_t reg3 =
      (static_cast<uint16_t>(response[9]) << 8) |
      response[10];

  /*
    The scan suggests the float uses:
    high word = register 3
    low word  = register 2
  */
  uint32_t speedBits =
      (static_cast<uint32_t>(reg3) << 16) |
      static_cast<uint32_t>(reg2);

  float decodedSpeed;
  memcpy(&decodedSpeed, &speedBits, sizeof(decodedSpeed));

  Serial.print("Reg 0: ");
  Serial.println(reg0);

  Serial.print("Direction: ");
  Serial.println(reg1);

  Serial.print("Reg 2: 0x");
  Serial.println(reg2, HEX);

  Serial.print("Reg 3: 0x");
  Serial.println(reg3, HEX);

  Serial.print("Decoded float speed: ");
  Serial.println(decodedSpeed, 4);

  *speedMs = decodedSpeed;
  *directionDeg = reg1;

  return true;
}

void setup() {
  Serial.begin(115200);

  while (!Serial && millis() < 5000) {
  }

  pinMode(WIND_DE_PIN, OUTPUT);
  digitalWrite(WIND_DE_PIN, LOW);

  Serial2.setTX(WIND_TX_PIN);
  Serial2.setRX(WIND_RX_PIN);
  Serial2.begin(WIND_BAUD, SERIAL_8E1);

  Serial.println("WS302 four-register wind test");
  delay(2000);
}

void loop() {
  float speed;
  uint16_t direction;

  if (readWindData(&speed, &direction)) {
    Serial.print("Wind speed: ");
    Serial.print(speed, 3);
    Serial.print(" m/s | Direction: ");
    Serial.print(direction);
    Serial.println(" deg");
  } else {
    Serial.println("Read failed");
  }

  delay(500);
}