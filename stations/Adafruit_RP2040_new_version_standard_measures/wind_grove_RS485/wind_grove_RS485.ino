// // wind for Atomlite:
#include <cstring>
#include <cmath>
#include <HardwareSerial.h>

// --- Atom Lite Grove port pins ---
// Grove connector exposes only G26 and G32 (plus 5V/GND).
// Assign one to RX and one to TX; swap if it doesn't work.
#define WIND_TX_PIN 26
#define WIND_RX_PIN 32
#define WIND_SLAVE_ADDR 0x01
#define WIND_BAUD 9600

// Use UART1 - UART0 is tied to the USB/Serial Monitor connection.
HardwareSerial WindSerial(1);

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

bool readWindData(float* speedMs, uint16_t* directionDeg) {
  constexpr uint8_t registerCount = 4;
  constexpr size_t expectedLength = 13;

  uint8_t request[8] = {
    WIND_SLAVE_ADDR,
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
  while (WindSerial.available() > 0) {
    WindSerial.read();
  }

  /*
    Grove RS485 has automatic direction control.
    Do not control DE or /RE manually.
  */
  WindSerial.write(request, sizeof(request));
  WindSerial.flush();

  uint8_t response[expectedLength] = {};
  size_t length = 0;
  const uint32_t startTime = millis();

  while ((millis() - startTime) < 400) {
    while (WindSerial.available() > 0 && length < expectedLength) {
      response[length++] =
          static_cast<uint8_t>(WindSerial.read());
    }

    if (length == expectedLength) {
      break;
    }

    // Modbus exception responses contain five bytes.
    if (length == 5 &&
        response[0] == WIND_SLAVE_ADDR &&
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
      response[0] == WIND_SLAVE_ADDR &&
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

  if (response[0] != WIND_SLAVE_ADDR) {
    Serial.println("Incorrect slave address");
    return false;
  }

  if (response[1] != 0x03) {
    Serial.println("Incorrect Modbus function");
    return false;
  }

  if (response[2] != 0x08) {
    Serial.println("Incorrect Modbus byte count");
    return false;
  }

  const uint16_t receivedCrc =
      static_cast<uint16_t>(response[11]) |
      (static_cast<uint16_t>(response[12]) << 8);

  const uint16_t calculatedCrc =
      modbus_crc16(response, 11);

  if (receivedCrc != calculatedCrc) {
    Serial.print("CRC error. Received: 0x");
    Serial.print(receivedCrc, HEX);
    Serial.print(" Calculated: 0x");
    Serial.println(calculatedCrc, HEX);
    return false;
  }

  const uint16_t reg0 =
      (static_cast<uint16_t>(response[3]) << 8) |
      response[4];

  const uint16_t reg1 =
      (static_cast<uint16_t>(response[5]) << 8) |
      response[6];

  const uint16_t reg2 =
      (static_cast<uint16_t>(response[7]) << 8) |
      response[8];

  const uint16_t reg3 =
      (static_cast<uint16_t>(response[9]) << 8) |
      response[10];

  /*
    Based on your register tests:

    Register 1: wind direction
    Register 2: low 16-bit word of wind-speed float
    Register 3: high 16-bit word of wind-speed float
  */
  const uint32_t speedBits =
      (static_cast<uint32_t>(reg3) << 16) |
      static_cast<uint32_t>(reg2);

  float decodedSpeed = 0.0f;
  memcpy(&decodedSpeed, &speedBits, sizeof(decodedSpeed));

  Serial.print("Register 0: ");
  Serial.println(reg0);

  Serial.print("Register 1, direction: ");
  Serial.println(reg1);

  Serial.print("Register 2: 0x");
  Serial.println(reg2, HEX);

  Serial.print("Register 3: 0x");
  Serial.println(reg3, HEX);

  Serial.print("Decoded speed: ");
  Serial.println(decodedSpeed, 4);

  // Reject corrupted or unreasonable decoded values.
  if (!std::isfinite(decodedSpeed) ||
      decodedSpeed < 0.0f ||
      decodedSpeed > 100.0f) {
    Serial.println("Invalid wind-speed value");
    return false;
  }

  if (reg1 > 359) {
    Serial.println("Invalid wind-direction value");
    return false;
  }

  *speedMs = decodedSpeed;
  *directionDeg = reg1;

  return true;
}

void setup() {
  Serial.begin(115200);

  const uint32_t serialStart = millis();
  while (!Serial && (millis() - serialStart) < 5000) {
  }

  // ESP32 HardwareSerial: begin(baud, config, rxPin, txPin)
  WindSerial.begin(WIND_BAUD, SERIAL_8E1, WIND_RX_PIN, WIND_TX_PIN);

  Serial.println();
  Serial.println("WS302 Grove RS485 test (M5Stack Atom Lite)");
  Serial.print("TX pin: G");
  Serial.print(WIND_TX_PIN);
  Serial.print(" | RX pin: G");
  Serial.println(WIND_RX_PIN);
  Serial.println("Expected response: 13 bytes beginning 01 03 08");
  delay(2000);
}

void loop() {
  float speedMs = 0.0f;
  uint16_t directionDeg = 0;

  if (readWindData(&speedMs, &directionDeg)) {
    if (speedMs < 0.2f) {
      Serial.print("Wind speed: ");
      Serial.print(speedMs, 3);
      Serial.println(" m/s | Direction: N/A (calm)");
    } else {
      Serial.print("Wind speed: ");
      Serial.print(speedMs, 3);
      Serial.print(" m/s | Direction: ");
      Serial.print(directionDeg);
      Serial.println(" degrees");
    }

  } else {
    Serial.println("Wind reading failed");
  }

  Serial.println();
  delay(1000);
}




// // wind for RP2040:

// #include <cstring>
// #include <cmath>

// #define WIND_TX_PIN 24
// #define WIND_RX_PIN 25
// #define WIND_SLAVE_ADDR 0x01
// #define WIND_BAUD 9600

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

// bool readWindData(float* speedMs, uint16_t* directionDeg) {
//   constexpr uint8_t registerCount = 4;
//   constexpr size_t expectedLength = 13;

//   uint8_t request[8] = {
//     WIND_SLAVE_ADDR,
//     0x03,
//     0x00, 0x00,  // Starting register: 0
//     0x00, registerCount,
//     0x00, 0x00
//   };

//   const uint16_t requestCrc = modbus_crc16(request, 6);

//   // Modbus CRC is transmitted low byte first.
//   request[6] = static_cast<uint8_t>(requestCrc & 0xFF);
//   request[7] = static_cast<uint8_t>((requestCrc >> 8) & 0xFF);

//   // Remove any old bytes from the UART receive buffer.
//   while (Serial2.available() > 0) {
//     Serial2.read();
//   }

//   /*
//     Grove RS485 has automatic direction control.
//     Do not control DE or /RE manually.
//   */
//   Serial2.write(request, sizeof(request));
//   Serial2.flush();

//   uint8_t response[expectedLength] = {};
//   size_t length = 0;
//   const uint32_t startTime = millis();

//   while ((millis() - startTime) < 400) {
//     while (Serial2.available() > 0 && length < expectedLength) {
//       response[length++] =
//           static_cast<uint8_t>(Serial2.read());
//     }

//     if (length == expectedLength) {
//       break;
//     }

//     // Modbus exception responses contain five bytes.
//     if (length == 5 &&
//         response[0] == WIND_SLAVE_ADDR &&
//         (response[1] & 0x80)) {
//       break;
//     }
//   }

//   Serial.print("RX (");
//   Serial.print(length);
//   Serial.print(" bytes): ");

//   for (size_t i = 0; i < length; i++) {
//     if (response[i] < 0x10) {
//       Serial.print('0');
//     }

//     Serial.print(response[i], HEX);
//     Serial.print(' ');
//   }

//   Serial.println();

//   // Check for a Modbus exception response.
//   if (length == 5 &&
//       response[0] == WIND_SLAVE_ADDR &&
//       (response[1] & 0x80)) {

//     const uint16_t receivedCrc =
//         static_cast<uint16_t>(response[3]) |
//         (static_cast<uint16_t>(response[4]) << 8);

//     const uint16_t calculatedCrc =
//         modbus_crc16(response, 3);

//     if (receivedCrc == calculatedCrc) {
//       Serial.print("Modbus exception code: 0x");

//       if (response[2] < 0x10) {
//         Serial.print('0');
//       }

//       Serial.println(response[2], HEX);
//     } else {
//       Serial.println("Invalid exception-response CRC");
//     }

//     return false;
//   }

//   if (length != expectedLength) {
//     Serial.println("Incorrect response length");
//     return false;
//   }

//   if (response[0] != WIND_SLAVE_ADDR) {
//     Serial.println("Incorrect slave address");
//     return false;
//   }

//   if (response[1] != 0x03) {
//     Serial.println("Incorrect Modbus function");
//     return false;
//   }

//   if (response[2] != 0x08) {
//     Serial.println("Incorrect Modbus byte count");
//     return false;
//   }

//   const uint16_t receivedCrc =
//       static_cast<uint16_t>(response[11]) |
//       (static_cast<uint16_t>(response[12]) << 8);

//   const uint16_t calculatedCrc =
//       modbus_crc16(response, 11);

//   if (receivedCrc != calculatedCrc) {
//     Serial.print("CRC error. Received: 0x");
//     Serial.print(receivedCrc, HEX);
//     Serial.print(" Calculated: 0x");
//     Serial.println(calculatedCrc, HEX);
//     return false;
//   }

//   const uint16_t reg0 =
//       (static_cast<uint16_t>(response[3]) << 8) |
//       response[4];

//   const uint16_t reg1 =
//       (static_cast<uint16_t>(response[5]) << 8) |
//       response[6];

//   const uint16_t reg2 =
//       (static_cast<uint16_t>(response[7]) << 8) |
//       response[8];

//   const uint16_t reg3 =
//       (static_cast<uint16_t>(response[9]) << 8) |
//       response[10];

//   /*
//     Based on your register tests:

//     Register 1: wind direction
//     Register 2: low 16-bit word of wind-speed float
//     Register 3: high 16-bit word of wind-speed float
//   */
//   const uint32_t speedBits =
//       (static_cast<uint32_t>(reg3) << 16) |
//       static_cast<uint32_t>(reg2);

//   float decodedSpeed = 0.0f;
//   memcpy(&decodedSpeed, &speedBits, sizeof(decodedSpeed));

//   Serial.print("Register 0: ");
//   Serial.println(reg0);

//   Serial.print("Register 1, direction: ");
//   Serial.println(reg1);

//   Serial.print("Register 2: 0x");
//   Serial.println(reg2, HEX);

//   Serial.print("Register 3: 0x");
//   Serial.println(reg3, HEX);

//   Serial.print("Decoded speed: ");
//   Serial.println(decodedSpeed, 4);

//   // Reject corrupted or unreasonable decoded values.
//   if (!std::isfinite(decodedSpeed) ||
//       decodedSpeed < 0.0f ||
//       decodedSpeed > 100.0f) {
//     Serial.println("Invalid wind-speed value");
//     return false;
//   }

//   if (reg1 > 359) {
//     Serial.println("Invalid wind-direction value");
//     return false;
//   }

//   *speedMs = decodedSpeed;
//   *directionDeg = reg1;

//   return true;
// }

// void setup() {
//   Serial.begin(115200);

//   while (!Serial && millis() < 5000) {
//   }

//   Serial2.setTX(WIND_TX_PIN);
//   Serial2.setRX(WIND_RX_PIN);
//   Serial2.begin(WIND_BAUD, SERIAL_8E1);

//   Serial.println();
//   Serial.println("WS302 Grove RS485 test");
//   Serial.println("Expected response: 13 bytes beginning 01 03 08");
//   delay(2000);
// }

// void loop() {
//   float speedMs = 0.0f;
//   uint16_t directionDeg = 0;

//   if (readWindData(&speedMs, &directionDeg)) {
//     if (speedMs < 0.2f) {
//       Serial.print("Wind speed: ");
//       Serial.print(speedMs, 3);
//       Serial.println(" m/s | Direction: N/A (calm)");
//     } else {
//       Serial.print("Wind speed: ");
//       Serial.print(speedMs, 3);
//       Serial.print(" m/s | Direction: ");
//       Serial.print(directionDeg);
//       Serial.println(" degrees");
//     }

//   } else {
//     Serial.println("Wind reading failed");
//   }

//   Serial.println();
//   delay(1000);
// }