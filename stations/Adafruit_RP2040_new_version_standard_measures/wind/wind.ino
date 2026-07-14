// // #define WIND_TX_PIN 24
// // #define WIND_RX_PIN 25
// // #define WIND_DE_PIN A0
// // #define WIND_SLAVE_ADDR 0x01
// // #define WIND_BAUD 9600

// // uint16_t modbus_crc16(const uint8_t* buf, int len) {
// //   uint16_t crc = 0xFFFF;
// //   for (int pos = 0; pos < len; pos++) {
// //     crc ^= (uint16_t)buf[pos];
// //     for (int i = 0; i < 8; i++) {
// //       if (crc & 1) { crc >>= 1; crc ^= 0xA001; }
// //       else crc >>= 1;
// //     }
// //   }
// //   return crc;
// // }

// // void rs485_transmit(bool en) {
// //   digitalWrite(WIND_DE_PIN, en ? HIGH : LOW);
// //   delayMicroseconds(50);
// // }

// // bool readWindData(float* speed_ms, uint16_t* direction_deg) {
// //   const uint8_t expectedLength = 9;

// //   uint8_t req[8] = {
// //     WIND_SLAVE_ADDR,
// //     0x03,
// //     0x00, 0x00,  // Starting register: 0
// //     0x00, 0x02,  // Number of registers: 2
// //     0x00, 0x00   // CRC placeholders
// //   };

// //   uint16_t requestCrc = modbus_crc16(req, 6);
// //   req[6] = requestCrc & 0xFF;
// //   req[7] = (requestCrc >> 8) & 0xFF;

// //   // Remove any old bytes.
// //   while (Serial2.available()) {
// //     Serial2.read();
// //   }

// //   // Transmit request.
// //   rs485_transmit(true);
// //   Serial2.write(req, sizeof(req));
// //   Serial2.flush();

// //   // Allow the last stop bit to leave the UART before disabling the driver.
// //   delayMicroseconds(200);
// //   rs485_transmit(false);

// //   uint8_t buf[expectedLength];
// //   uint8_t idx = 0;
// //   uint32_t start = millis();

// //   while ((millis() - start < 400) && (idx < expectedLength)) {
// //     if (Serial2.available()) {
// //       buf[idx++] = static_cast<uint8_t>(Serial2.read());
// //     }
// //   }

// //   Serial.print("RX bytes (");
// //   Serial.print(idx);
// //   Serial.print("): ");

// //   for (uint8_t i = 0; i < idx; i++) {
// //     if (buf[i] < 0x10) {
// //       Serial.print('0');
// //     }

// //     Serial.print(buf[i], HEX);
// //     Serial.print(' ');
// //   }

// //   Serial.println();

// //   if (idx != expectedLength) {
// //     Serial.println("Error: incorrect response length");
// //     return false;
// //   }

// //   if (buf[0] != WIND_SLAVE_ADDR) {
// //     Serial.println("Error: incorrect slave address");
// //     return false;
// //   }

// //   if (buf[1] & 0x80) {
// //     Serial.print("Modbus exception code: ");
// //     Serial.println(buf[2], HEX);
// //     return false;
// //   }

// //   if (buf[1] != 0x03) {
// //     Serial.println("Error: incorrect function code");
// //     return false;
// //   }

// //   if (buf[2] != 0x04) {
// //     Serial.println("Error: incorrect byte count");
// //     return false;
// //   }

// //   uint16_t receivedCrc =
// //       static_cast<uint16_t>(buf[7]) |
// //       (static_cast<uint16_t>(buf[8]) << 8);

// //   uint16_t calculatedCrc = modbus_crc16(buf, 7);

// //   if (receivedCrc != calculatedCrc) {
// //     Serial.print("CRC error. Received: 0x");
// //     Serial.print(receivedCrc, HEX);
// //     Serial.print(", calculated: 0x");
// //     Serial.println(calculatedCrc, HEX);
// //     return false;
// //   }

// //   uint16_t speedRaw =
// //       (static_cast<uint16_t>(buf[3]) << 8) |
// //       static_cast<uint16_t>(buf[4]);

// //   uint16_t directionRaw =
// //       (static_cast<uint16_t>(buf[5]) << 8) |
// //       static_cast<uint16_t>(buf[6]);

// //   Serial.print("Raw speed: ");
// //   Serial.print(speedRaw);
// //   Serial.print(" | Raw direction: ");
// //   Serial.println(directionRaw);

// //   *speed_ms = static_cast<float>(speedRaw) / 10.0f;
// //   *direction_deg = directionRaw;

// //   return true;
// // }

// // void setup() {
// //   Serial.begin(115200);
// //   while (!Serial && millis() < 5000);
// //   pinMode(WIND_DE_PIN, OUTPUT);
// //   digitalWrite(WIND_DE_PIN, LOW);
// //   Serial2.setTX(WIND_TX_PIN);
// //   Serial2.setRX(WIND_RX_PIN);
// //   Serial2.begin(WIND_BAUD, SERIAL_8E1);
// //   Serial.println("WS302 live wind reading test");
// //   delay(2000);
// // }

// // void loop() {
// //   float speed;
// //   uint16_t direction;

// //   if (readWindData(&speed, &direction)) {
// //     Serial.print("Wind speed: ");
// //     Serial.print(speed, 1);
// //     Serial.print(" m/s   |   Direction: ");
// //     Serial.print(direction);
// //     Serial.println(" deg");
// //   } else {
// //     Serial.println("Read failed - no valid response");
// //   }

// //   delay(500); // twice a second - fast enough to watch live changes
// // }




// #define WIND_TX_PIN 24
// #define WIND_RX_PIN 25
// #define WIND_DE_PIN A0

// #define WIND_SLAVE_ADDR 0x01
// #define WIND_BAUD 9600

// #define FIRST_REGISTER 0
// #define LAST_REGISTER 99

// uint16_t modbus_crc16(const uint8_t* data, size_t length) {
//   uint16_t crc = 0xFFFF;

//   for (size_t position = 0; position < length; position++) {
//     crc ^= static_cast<uint16_t>(data[position]);

//     for (uint8_t bit = 0; bit < 8; bit++) {
//       if (crc & 0x0001) {
//         crc >>= 1;
//         crc ^= 0xA001;
//       } else {
//         crc >>= 1;
//       }
//     }
//   }

//   return crc;
// }

// void setRS485Transmit(bool enabled) {
//   digitalWrite(WIND_DE_PIN, enabled ? HIGH : LOW);
//   delayMicroseconds(50);
// }

// void clearSerialBuffer() {
//   while (Serial2.available()) {
//     Serial2.read();
//   }
// }

// void printHexByte(uint8_t value) {
//   if (value < 0x10) {
//     Serial.print('0');
//   }

//   Serial.print(value, HEX);
// }

// void printRawResponse(const uint8_t* buffer, uint8_t length) {
//   Serial.print("RX: ");

//   for (uint8_t i = 0; i < length; i++) {
//     printHexByte(buffer[i]);
//     Serial.print(' ');
//   }

//   Serial.println();
// }

// /*
//   Reads one holding register using Modbus function 0x03.

//   Returns true only when a valid register value is received.
// */
// bool readHoldingRegister(uint16_t registerAddress, uint16_t* value) {
//   uint8_t request[8] = {
//     WIND_SLAVE_ADDR,
//     0x03,
//     static_cast<uint8_t>(registerAddress >> 8),
//     static_cast<uint8_t>(registerAddress & 0xFF),
//     0x00,
//     0x01,
//     0x00,
//     0x00
//   };

//   uint16_t requestCrc = modbus_crc16(request, 6);

//   request[6] = static_cast<uint8_t>(requestCrc & 0xFF);
//   request[7] = static_cast<uint8_t>(requestCrc >> 8);

//   clearSerialBuffer();

//   setRS485Transmit(true);

//   size_t bytesWritten = Serial2.write(request, sizeof(request));
//   Serial2.flush();

//   // Ensure the final UART stop bit has left the transmitter.
//   delayMicroseconds(200);

//   setRS485Transmit(false);

//   if (bytesWritten != sizeof(request)) {
//     Serial.println("TX error");
//     return false;
//   }

//   /*
//     Normal one-register response:
//     address, function, byte count, data high, data low, CRC low, CRC high
//     Total: 7 bytes

//     Exception response:
//     address, function | 0x80, exception code, CRC low, CRC high
//     Total: 5 bytes
//   */
//   uint8_t response[16];
//   uint8_t responseLength = 0;

//   uint32_t startTime = millis();
//   uint32_t lastByteTime = startTime;

//   while (millis() - startTime < 300) {
//     while (Serial2.available() && responseLength < sizeof(response)) {
//       response[responseLength++] =
//           static_cast<uint8_t>(Serial2.read());

//       lastByteTime = millis();
//     }

//     // Stop after the response has been quiet for at least 10 ms.
//     if (responseLength > 0 && millis() - lastByteTime >= 10) {
//       break;
//     }
//   }

//   if (responseLength == 0) {
//     Serial.println("No response");
//     return false;
//   }

//   printRawResponse(response, responseLength);

//   if (responseLength < 5) {
//     Serial.println("Invalid: response too short");
//     return false;
//   }

//   uint16_t receivedCrc =
//       static_cast<uint16_t>(response[responseLength - 2]) |
//       (static_cast<uint16_t>(response[responseLength - 1]) << 8);

//   uint16_t calculatedCrc =
//       modbus_crc16(response, responseLength - 2);

//   if (receivedCrc != calculatedCrc) {
//     Serial.print("CRC error: received 0x");
//     Serial.print(receivedCrc, HEX);
//     Serial.print(", calculated 0x");
//     Serial.println(calculatedCrc, HEX);
//     return false;
//   }

//   if (response[0] != WIND_SLAVE_ADDR) {
//     Serial.println("Invalid slave address");
//     return false;
//   }

//   // Check for a Modbus exception.
//   if (response[1] == (0x03 | 0x80)) {
//     Serial.print("Modbus exception 0x");
//     printHexByte(response[2]);

//     switch (response[2]) {
//       case 0x01:
//         Serial.println(" — illegal function");
//         break;

//       case 0x02:
//         Serial.println(" — illegal register address");
//         break;

//       case 0x03:
//         Serial.println(" — illegal data value");
//         break;

//       case 0x04:
//         Serial.println(" — device failure");
//         break;

//       default:
//         Serial.println();
//         break;
//     }

//     return false;
//   }

//   if (responseLength != 7) {
//     Serial.println("Invalid normal-response length");
//     return false;
//   }

//   if (response[1] != 0x03) {
//     Serial.println("Unexpected function code");
//     return false;
//   }

//   if (response[2] != 0x02) {
//     Serial.println("Unexpected byte count");
//     return false;
//   }

//   *value =
//       (static_cast<uint16_t>(response[3]) << 8) |
//       static_cast<uint16_t>(response[4]);

//   return true;
// }

// void scanRegisters() {
//   Serial.println();
//   Serial.println("======================================");
//   Serial.println("Starting WS302 holding-register scan");
//   Serial.print("Range: ");
//   Serial.print(FIRST_REGISTER);
//   Serial.print(" through ");
//   Serial.println(LAST_REGISTER);
//   Serial.println("======================================");

//   for (uint16_t address = FIRST_REGISTER;
//        address <= LAST_REGISTER;
//        address++) {

//     Serial.println();
//     Serial.print("Register ");
//     Serial.print(address);
//     Serial.print(" (0x");

//     if (address < 0x10) {
//       Serial.print('0');
//     }

//     Serial.print(address, HEX);
//     Serial.println(")");

//     uint16_t value = 0;

//     if (readHoldingRegister(address, &value)) {
//       Serial.print("VALUE: ");
//       Serial.print(value);
//       Serial.print(" decimal, 0x");

//       if (value < 0x1000) Serial.print('0');
//       if (value < 0x0100) Serial.print('0');
//       if (value < 0x0010) Serial.print('0');

//       Serial.println(value, HEX);
//     } else {
//       Serial.println("VALUE: unavailable");
//     }

//     // Avoid sending requests too aggressively.
//     delay(150);
//   }

//   Serial.println();
//   Serial.println("======================================");
//   Serial.println("Register scan complete");
//   Serial.println("======================================");
// }

// void setup() {
//   Serial.begin(115200);

//   while (!Serial && millis() < 5000) {
//     // Wait briefly for the USB serial monitor.
//   }

//   pinMode(WIND_DE_PIN, OUTPUT);
//   digitalWrite(WIND_DE_PIN, LOW);

//   Serial2.setTX(WIND_TX_PIN);
//   Serial2.setRX(WIND_RX_PIN);
//   Serial2.begin(WIND_BAUD, SERIAL_8E1);

//   Serial.println("WS302 Modbus register scanner");
//   Serial.println("Function: 0x03 Read Holding Registers");
//   Serial.println("The scan will begin in 2 seconds.");

//   delay(2000);

//   scanRegisters();
// }

// void loop() {
//   // The scan runs once in setup().
// }


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