#include <SPI.h>
#include <PN5180FeliCa.h>
#include <PN5180ISO14443.h>
#include <PN5180ISO15693.h>

// XIAO ESP32-S3 wiring for PN5180.
static constexpr uint8_t PN5180_SCK_PIN = 7;
static constexpr uint8_t PN5180_MISO_PIN = 8;
static constexpr uint8_t PN5180_MOSI_PIN = 9;
static constexpr uint8_t PN5180_NSS_PIN = 2;
static constexpr uint8_t PN5180_BUSY_PIN = 3;
static constexpr uint8_t PN5180_RST_PIN = 4;
static constexpr uint32_t SERIAL_BAUD = 460800;
static constexpr uint8_t MAX_BLOCKS_PER_READ_CAP = 32;
static constexpr uint32_t ISO15693_INITIAL_WAIT_MS = 2;
static constexpr uint32_t ISO15693_POLL_WAIT_MS = 1;
static constexpr uint32_t ISO15693_RX_TIMEOUT_MS = 120;
static constexpr uint8_t MAX_MULTI_READ_RETRIES = 6;
static constexpr uint8_t MAX_SINGLE_READ_RETRIES = 12;
static constexpr uint16_t ISO15693_READ_BUFFER_BYTES = 1024;
static constexpr uint8_t ISO15693_MAX_WRITE_BLOCK_SIZE = 32;
static constexpr uint8_t MAX_ISO14443A_READ_COMMANDS = 64;
static constexpr uint8_t PN5180_WRITE_REGISTER_SAFE = 0x00;
static constexpr uint8_t PN5180_WRITE_REGISTER_OR_MASK_SAFE = 0x01;
static constexpr uint8_t PN5180_WRITE_REGISTER_AND_MASK_SAFE = 0x02;
static constexpr uint8_t PN5180_READ_REGISTER_SAFE = 0x04;
static constexpr uint8_t PN5180_SEND_DATA_SAFE = 0x09;
static constexpr uint8_t PN5180_READ_DATA_SAFE = 0x0A;
static constexpr uint8_t PN5180_LOAD_RF_CONFIG_SAFE = 0x11;
static constexpr uint8_t PN5180_RF_ON_SAFE = 0x16;
static constexpr uint8_t PN5180_MIFARE_AUTHENTICATE = 0x0C;
static constexpr uint8_t MIFARE_KEY_A = 0x60;
static constexpr uint8_t MIFARE_KEY_B = 0x61;
static constexpr uint16_t MIFARE_CLASSIC_MAX_BLOCKS = 256;
static constexpr uint8_t MIFARE_CLASSIC_BLOCK_SIZE = 16;
static constexpr uint32_t PN5180_BUSY_TIMEOUT_MS = 40;
static constexpr uint32_t PN5180_RESET_TIMEOUT_MS = 250;
static constexpr uint32_t PN5180_RF_ON_TIMEOUT_MS = 250;
static constexpr uint32_t MIFARE_CLASSIC_READ_TIMEOUT_MS = 45;
static constexpr uint8_t MIFARE_CLASSIC_DEFAULT_READ_RETRIES = 3;
static constexpr uint8_t MIFARE_CLASSIC_DEFAULT_RECOVERY_RETRIES = 8;
static constexpr uint8_t MIFARE_CLASSIC_BRUTE_READ_RETRIES = 3;
static constexpr uint8_t MIFARE_BLOCK_STATUS_READ = 1;
static constexpr uint8_t MIFARE_BLOCK_STATUS_NOT_READ = 2;
static constexpr uint8_t MIFARE_BLOCK_STATUS_KEY_MISSING = 3;

PN5180ISO15693 nfc15693(PN5180_NSS_PIN, PN5180_BUSY_PIN, PN5180_RST_PIN);
PN5180ISO14443 nfc14443(PN5180_NSS_PIN, PN5180_BUSY_PIN, PN5180_RST_PIN);
PN5180FeliCa nfcFeliCa(PN5180_NSS_PIN, PN5180_BUSY_PIN, PN5180_RST_PIN);
SPISettings pn5180DirectSpiSettings(7000000, MSBFIRST, SPI_MODE0);
uint8_t lastMifareAuthStatus = 0xFF;

static const uint8_t MIFARE_CLASSIC_KEYS[][6] = {
  {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF},
// Keep extended dictionaries on the host side; the startup scan should stay fast.
#if 0
  {0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0},
  {0xA1, 0xB1, 0xC1, 0xD1, 0xE1, 0xF1},
  {0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5},
  {0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5},
  {0x4D, 0x3A, 0x99, 0xC3, 0x51, 0xDD},
  {0x1A, 0x98, 0x2C, 0x7E, 0x45, 0x9A},
  {0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
  {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF},
  {0xD3, 0xF7, 0xD3, 0xF7, 0xD3, 0xF7},
  {0x71, 0x4C, 0x5C, 0x88, 0x6E, 0x97},
  {0x58, 0x7E, 0xE5, 0xF9, 0x35, 0x0F},
  {0xA0, 0x47, 0x8C, 0xC3, 0x90, 0x91},
  {0x53, 0x3C, 0xB6, 0xC7, 0x23, 0xF6},
  {0x8F, 0xD0, 0xA4, 0xF2, 0x56, 0xE9},
  {0xA5, 0xA4, 0xA3, 0xA2, 0xA1, 0xA0},
  {0x89, 0xEC, 0xA9, 0x7F, 0x8C, 0x2A},
  {0x5C, 0x8F, 0xF9, 0x99, 0x0D, 0xA2},
  {0x75, 0xCC, 0xB5, 0x9C, 0x9B, 0xED},
  {0xD0, 0x1A, 0xFE, 0xEB, 0x89, 0x0A},
  {0x4B, 0x79, 0x1B, 0xEA, 0x7B, 0xCC},
  {0x26, 0x12, 0xC6, 0xDE, 0x84, 0xCA},
  {0x70, 0x7B, 0x11, 0xFC, 0x14, 0x81},
  {0x03, 0xF9, 0x06, 0x76, 0x46, 0xAE},
  {0x23, 0x52, 0xC5, 0xB5, 0x6D, 0x85},
  {0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5},
  {0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5},
  {0xFA, 0xFA, 0xFA, 0xFA, 0xFA, 0xFA},
  {0xFB, 0xFB, 0xFB, 0xFB, 0xFB, 0xFB},
  {0x5A, 0x1B, 0x85, 0xFC, 0xE2, 0x0A},
  {0xE0, 0x00, 0x00, 0x00, 0x00, 0x00},
  {0xE7, 0xD6, 0x06, 0x4C, 0x58, 0x60},
  {0xB2, 0x7C, 0xCA, 0xB3, 0x0D, 0xBD},
  {0xD2, 0xEC, 0xE8, 0xB9, 0x39, 0x5E},
  {0x14, 0x94, 0xE8, 0x16, 0x63, 0xD7},
  {0x7C, 0x9F, 0xB8, 0x47, 0x42, 0x42},
  {0x56, 0x93, 0x69, 0xC5, 0xA0, 0xE5},
  {0x63, 0x21, 0x93, 0xBE, 0x1C, 0x3C},
  {0x64, 0x46, 0x72, 0xBD, 0x4A, 0xFE},
  {0x8F, 0xE6, 0x44, 0x03, 0x87, 0x90},
  {0x9D, 0xE8, 0x9E, 0x07, 0x02, 0x77},
  {0xB5, 0xFF, 0x67, 0xCB, 0xA9, 0x51},
  {0xEF, 0xF6, 0x03, 0xE1, 0xEF, 0xE9},
  {0xF1, 0x4E, 0xE7, 0xCA, 0xE8, 0x63},
  {0x9C, 0x28, 0xA6, 0x0F, 0x72, 0x49},
  {0xC9, 0x82, 0x6A, 0xF0, 0x27, 0x94},
  {0xFC, 0x00, 0x01, 0x87, 0x78, 0xF7},
  {0x02, 0x97, 0x92, 0x7C, 0x0F, 0x77},
  {0x54, 0x72, 0x61, 0x76, 0x65, 0x6C},
  {0x00, 0x00, 0x0F, 0xFE, 0x24, 0x88},
  {0x77, 0x69, 0x74, 0x68, 0x75, 0x73},
  {0xEE, 0x00, 0x42, 0xF8, 0x88, 0x40},
  {0x26, 0x94, 0x0B, 0x21, 0xFF, 0x5D},
  {0xA6, 0x45, 0x98, 0xA7, 0x74, 0x78},
  {0x5C, 0x59, 0x8C, 0x9C, 0x58, 0xB5},
  {0xE4, 0xD2, 0x77, 0x0A, 0x89, 0xBE},
  {0x72, 0x2B, 0xFC, 0xC5, 0x37, 0x5F},
  {0xF1, 0xD8, 0x3F, 0x96, 0x43, 0x14},
  {0x50, 0x52, 0x49, 0x56, 0x41, 0x41},
  {0x50, 0x52, 0x49, 0x56, 0x41, 0x42},
  {0x47, 0x52, 0x4F, 0x55, 0x50, 0x41},
  {0x43, 0x4F, 0x4D, 0x4D, 0x4F, 0x41},
  {0x47, 0x52, 0x4F, 0x55, 0x50, 0x42},
  {0x43, 0x4F, 0x4D, 0x4D, 0x4F, 0x42},
  {0x4B, 0x0B, 0x20, 0x10, 0x7C, 0xCB},
  {0x60, 0x5F, 0x5E, 0x5D, 0x5C, 0x5B},
  {0x19, 0x94, 0x04, 0x28, 0x19, 0x70},
  {0x19, 0x94, 0x04, 0x28, 0x19, 0x98},
  {0xFF, 0xF0, 0x11, 0x22, 0x33, 0x58},
  {0xFF, 0x9F, 0x11, 0x22, 0x33, 0x58},
  {0xAC, 0x37, 0xE7, 0x63, 0x85, 0xF5},
  {0x57, 0x6D, 0xCF, 0xFF, 0x2F, 0x25},
  {0x1E, 0xE3, 0x84, 0x19, 0xEF, 0x39},
  {0x26, 0x57, 0x87, 0x19, 0xDC, 0xD9},
  {0x00, 0x00, 0x00, 0x00, 0x00, 0x01},
  {0x00, 0x00, 0x00, 0x00, 0x00, 0x02},
  {0x00, 0x00, 0x00, 0x00, 0x00, 0x0A},
  {0x00, 0x00, 0x00, 0x00, 0x00, 0x0B},
  {0x01, 0x02, 0x03, 0x04, 0x05, 0x06},
  {0x01, 0x23, 0x45, 0x67, 0x89, 0xAB},
  {0x10, 0x00, 0x00, 0x00, 0x00, 0x00},
  {0x11, 0x11, 0x11, 0x11, 0x11, 0x11},
  {0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC},
  {0x12, 0xF2, 0xEE, 0x34, 0x78, 0xC1},
  {0x14, 0xD4, 0x46, 0xE3, 0x33, 0x63},
  {0x19, 0x99, 0xA3, 0x55, 0x4A, 0x55},
  {0x20, 0x00, 0x00, 0x00, 0x00, 0x00},
  {0x22, 0x22, 0x22, 0x22, 0x22, 0x22},
  {0x27, 0xDD, 0x91, 0xF1, 0xFC, 0xF1},
  {0x50, 0x52, 0x09, 0x01, 0x6A, 0x1F},
  {0x2B, 0xA9, 0x62, 0x1E, 0x0A, 0x36},
  {0x4A, 0xF9, 0xD7, 0xAD, 0xEB, 0xE4},
  {0x33, 0x33, 0x33, 0x33, 0x33, 0x33},
  {0x33, 0xF9, 0x74, 0xB4, 0x27, 0x69},
  {0x34, 0xD1, 0xDF, 0x99, 0x34, 0xC5},
  {0x43, 0xAB, 0x19, 0xEF, 0x5C, 0x31},
  {0x44, 0x44, 0x44, 0x44, 0x44, 0x44},
  {0x50, 0x52, 0x49, 0x56, 0x54, 0x41},
  {0x50, 0x52, 0x49, 0x56, 0x54, 0x42},
  {0x55, 0x55, 0x55, 0x55, 0x55, 0x55},
#endif
};
static constexpr uint8_t MIFARE_CLASSIC_KEY_COUNT = sizeof(MIFARE_CLASSIC_KEYS) / sizeof(MIFARE_CLASSIC_KEYS[0]);

struct MifareClassicDumpResult {
  uint16_t blockCount = 0;
  uint16_t blocksRead = 0;
  uint8_t sectorCount = 0;
  uint8_t sectorsAuthenticated = 0;
};

bool pn5180WriteRegisterWithAndMaskSafe(uint8_t reg, uint32_t mask);
bool pn5180WriteRegisterWithOrMaskSafe(uint8_t reg, uint32_t mask);
bool pn5180ClearIRQStatusSafe(uint32_t irqMask);
bool pn5180LoadRfConfigSafe(uint8_t txConf, uint8_t rxConf);
bool pn5180TransceiveRfSafe(const uint8_t *command, uint8_t commandLen, uint8_t validBits, uint8_t expectedLen, uint8_t *response, uint32_t timeoutMs);
bool setupRfSafe(uint8_t txConf, uint8_t rxConf, bool startTransceive, const __FlashStringHelper *protocolName);
uint8_t activateTypeASafe(uint8_t *buffer, uint8_t kind);

struct SystemInfoData {
  ISO15693ErrorCode rc = ISO15693_EC_UNKNOWN_ERROR;
  uint8_t uid[8] = {0};
  uint8_t infoFlags = 0;
  bool hasDsfid = false;
  uint8_t dsfid = 0;
  bool hasAfi = false;
  uint8_t afi = 0;
  bool hasMemorySize = false;
  uint8_t blockSize = 0;
  uint8_t numBlocks = 0;
  bool hasIcReference = false;
  uint8_t icReference = 0;
};

void printHexByte(uint8_t value) {
  if (value < 0x10) {
    Serial.print('0');
  }
  Serial.print(value, HEX);
}

void printUidReversed(const uint8_t *uid, uint8_t len) {
  for (int i = len - 1; i >= 0; --i) {
    printHexByte(uid[i]);
    if (i > 0) {
      Serial.print(':');
    }
  }
}

void printUidReversedCompact(const uint8_t *uid, uint8_t len) {
  for (int i = len - 1; i >= 0; --i) {
    printHexByte(uid[i]);
  }
}

void printHexCompact(const uint8_t *data, uint8_t len) {
  for (uint8_t i = 0; i < len; ++i) {
    printHexByte(data[i]);
  }
}

void printHexLine(const uint8_t *data, uint8_t len) {
  for (uint8_t i = 0; i < len; ++i) {
    printHexByte(data[i]);
    if (i + 1 < len) {
      Serial.print(' ');
    }
  }
  Serial.println();
}

void printMifareKey(const uint8_t key[6]) {
  for (uint8_t i = 0; i < 6; ++i) {
    printHexByte(key[i]);
  }
}

bool waitPn5180BusyState(uint8_t expectedState, uint32_t timeoutMs) {
  uint32_t startedAt = millis();
  while (digitalRead(PN5180_BUSY_PIN) != expectedState) {
    if ((millis() - startedAt) > timeoutMs) {
      return false;
    }
    delayMicroseconds(50);
  }
  return true;
}

bool pn5180DirectCommand(uint8_t *sendBuffer, size_t sendBufferLen, uint8_t *recvBuffer = nullptr, size_t recvBufferLen = 0) {
  bool ok = true;

  SPI.beginTransaction(pn5180DirectSpiSettings);

  ok = waitPn5180BusyState(LOW, PN5180_BUSY_TIMEOUT_MS);
  if (ok) {
    digitalWrite(PN5180_NSS_PIN, LOW);
    delay(2);
    for (size_t i = 0; i < sendBufferLen; ++i) {
      SPI.transfer(sendBuffer[i]);
    }
    ok = waitPn5180BusyState(HIGH, PN5180_BUSY_TIMEOUT_MS);
    digitalWrite(PN5180_NSS_PIN, HIGH);
    delay(1);
  }

  if (ok) {
    ok = waitPn5180BusyState(LOW, PN5180_BUSY_TIMEOUT_MS);
  }

  if (ok && recvBuffer != nullptr && recvBufferLen > 0) {
    digitalWrite(PN5180_NSS_PIN, LOW);
    delay(2);
    for (size_t i = 0; i < recvBufferLen; ++i) {
      recvBuffer[i] = SPI.transfer(0xFF);
    }
    ok = waitPn5180BusyState(HIGH, PN5180_BUSY_TIMEOUT_MS);
    digitalWrite(PN5180_NSS_PIN, HIGH);
    delay(1);
    if (ok) {
      ok = waitPn5180BusyState(LOW, PN5180_BUSY_TIMEOUT_MS);
    }
  }

  digitalWrite(PN5180_NSS_PIN, HIGH);
  SPI.endTransaction();
  return ok;
}

void printErrorText(ISO15693ErrorCode rc) {
  Serial.print(F(" ("));
  switch (rc) {
    case EC_NO_CARD:
      Serial.print(F("No card detected"));
      break;
    case ISO15693_EC_OK:
      Serial.print(F("OK"));
      break;
    case ISO15693_EC_NOT_SUPPORTED:
      Serial.print(F("Command not supported"));
      break;
    case ISO15693_EC_NOT_RECOGNIZED:
      Serial.print(F("Command not recognized"));
      break;
    case ISO15693_EC_OPTION_NOT_SUPPORTED:
      Serial.print(F("Option not supported"));
      break;
    case ISO15693_EC_UNKNOWN_ERROR:
      Serial.print(F("Unknown error"));
      break;
    case ISO15693_EC_BLOCK_NOT_AVAILABLE:
      Serial.print(F("Block not available"));
      break;
    case ISO15693_EC_BLOCK_ALREADY_LOCKED:
      Serial.print(F("Block already locked"));
      break;
    case ISO15693_EC_BLOCK_IS_LOCKED:
      Serial.print(F("Block is locked"));
      break;
    case ISO15693_EC_BLOCK_NOT_PROGRAMMED:
      Serial.print(F("Block not programmed"));
      break;
    case ISO15693_EC_BLOCK_NOT_LOCKED:
      Serial.print(F("Block not locked"));
      break;
    case ISO15693_EC_CUSTOM_CMD_ERROR:
      Serial.print(F("Custom command error"));
      break;
    default:
      Serial.print(F("Undefined ISO15693 error"));
      break;
  }
  Serial.print(F(")"));
}

bool issueIso15693Raw(uint8_t *cmd, uint8_t cmdLen, uint8_t **resultPtr, ISO15693ErrorCode &rc) {
  nfc15693.sendData(cmd, cmdLen);
  delay(ISO15693_INITIAL_WAIT_MS);

  uint32_t status = nfc15693.getIRQStatus();
  if ((status & RX_SOF_DET_IRQ_STAT) == 0) {
    rc = EC_NO_CARD;
    return false;
  }

  uint32_t startWait = millis();
  while ((status & RX_IRQ_STAT) == 0) {
    if ((millis() - startWait) > ISO15693_RX_TIMEOUT_MS) {
      rc = ISO15693_EC_UNKNOWN_ERROR;
      return false;
    }
    delay(ISO15693_POLL_WAIT_MS);
    status = nfc15693.getIRQStatus();
  }

  uint32_t rxStatus = 0;
  nfc15693.readRegister(RX_STATUS, &rxStatus);
  uint16_t len = static_cast<uint16_t>(rxStatus & 0x000001ff);

  *resultPtr = nfc15693.readData(len);
  if (*resultPtr == nullptr) {
    rc = ISO15693_EC_UNKNOWN_ERROR;
    return false;
  }

  uint8_t responseFlags = (*resultPtr)[0];
  if (responseFlags & 0x01) {
    uint8_t errorCode = (*resultPtr)[1];
    rc = (errorCode >= 0xA0) ? ISO15693_EC_CUSTOM_CMD_ERROR : static_cast<ISO15693ErrorCode>(errorCode);
    return false;
  }

  nfc15693.clearIRQStatus(RX_SOF_DET_IRQ_STAT | IDLE_IRQ_STAT | TX_IRQ_STAT | RX_IRQ_STAT);
  rc = ISO15693_EC_OK;
  return true;
}

ISO15693ErrorCode getMultipleBlockSecurityStatus(uint8_t *uid, uint8_t firstBlock, uint8_t blockCount, uint8_t *statusBytes) {
  // ISO15693 command 0x2C: Get Multiple Block Security Status, addressed mode.
  uint8_t cmd[] = {0x22, 0x2C, 1, 2, 3, 4, 5, 6, 7, 8, firstBlock, static_cast<uint8_t>(blockCount - 1)};
  for (uint8_t i = 0; i < 8; ++i) {
    cmd[2 + i] = uid[i]; // UID is LSB-first in this library.
  }

  uint8_t *result = nullptr;
  ISO15693ErrorCode rc = ISO15693_EC_UNKNOWN_ERROR;
  if (!issueIso15693Raw(cmd, sizeof(cmd), &result, rc)) {
    return rc;
  }

  for (uint8_t i = 0; i < blockCount; ++i) {
    statusBytes[i] = result[1 + i];
  }

  return ISO15693_EC_OK;
}

ISO15693ErrorCode getIso15693InventorySafe(uint8_t *uid) {
  uint8_t inventory[] = {0x26, 0x01, 0x00};
  uint8_t *result = nullptr;
  ISO15693ErrorCode rc = ISO15693_EC_UNKNOWN_ERROR;
  if (!issueIso15693Raw(inventory, sizeof(inventory), &result, rc)) {
    return rc;
  }

  for (uint8_t i = 0; i < 8; ++i) {
    uid[i] = result[2 + i];
  }
  return ISO15693_EC_OK;
}

SystemInfoData readSystemInfo(uint8_t *uid) {
  SystemInfoData info;
  uint8_t cmd[] = {0x22, 0x2B, 1, 2, 3, 4, 5, 6, 7, 8};
  for (uint8_t i = 0; i < 8; ++i) {
    cmd[2 + i] = uid[i]; // UID is LSB-first in this library.
  }

  uint8_t *result = nullptr;
  ISO15693ErrorCode rc = ISO15693_EC_UNKNOWN_ERROR;
  if (!issueIso15693Raw(cmd, sizeof(cmd), &result, rc)) {
    info.rc = rc;
    return info;
  }

  info.rc = ISO15693_EC_OK;
  info.infoFlags = result[1];
  for (uint8_t i = 0; i < 8; ++i) {
    info.uid[i] = result[2 + i];
  }

  uint8_t *p = &result[10];
  if (info.infoFlags & 0x01) {
    info.hasDsfid = true;
    info.dsfid = *p++;
  }
  if (info.infoFlags & 0x02) {
    info.hasAfi = true;
    info.afi = *p++;
  }
  if (info.infoFlags & 0x04) {
    info.hasMemorySize = true;
    info.numBlocks = static_cast<uint8_t>(*p++ + 1);
    info.blockSize = static_cast<uint8_t>((*p++ & 0x1F) + 1);
  }
  if (info.infoFlags & 0x08) {
    info.hasIcReference = true;
    info.icReference = *p++;
  }

  return info;
}

uint8_t getBlocksPerRead(uint8_t blockSize) {
  if (blockSize == 0) {
    return 1;
  }
  uint16_t blocksByBuffer = ISO15693_READ_BUFFER_BYTES / blockSize;
  if (blocksByBuffer == 0) {
    return 1;
  }
  return static_cast<uint8_t>(min<uint16_t>(MAX_BLOCKS_PER_READ_CAP, blocksByBuffer));
}

ISO15693ErrorCode readMultipleBlocks(uint8_t *uid, uint8_t firstBlock, uint8_t blockCount, uint8_t *buffer, uint8_t blockSize) {
  // ISO15693 command 0x23: Read Multiple Blocks, addressed mode.
  uint8_t cmd[] = {0x22, 0x23, 1, 2, 3, 4, 5, 6, 7, 8, firstBlock, static_cast<uint8_t>(blockCount - 1)};
  for (uint8_t i = 0; i < 8; ++i) {
    cmd[2 + i] = uid[i]; // UID is LSB-first in this library.
  }

  uint8_t *result = nullptr;
  ISO15693ErrorCode rc = ISO15693_EC_UNKNOWN_ERROR;
  if (!issueIso15693Raw(cmd, sizeof(cmd), &result, rc)) {
    return rc;
  }

  uint16_t payloadSize = static_cast<uint16_t>(blockCount) * blockSize;
  for (uint16_t i = 0; i < payloadSize; ++i) {
    buffer[i] = result[1 + i];
  }

  return ISO15693_EC_OK;
}

void ensureRfReady() {
  while (true) {
    nfc15693.reset();
    if (nfc15693.setupRF()) {
      return;
    }
    Serial.println(F("INFO rf_setup_retry"));
    delay(100);
  }
}

bool tryReadSingleBlockWithRetry(uint8_t *uid, uint8_t blockNo, uint8_t *blockData, uint8_t blockSize) {
  uint8_t attempt = 0;

  while (attempt < MAX_SINGLE_READ_RETRIES) {
    ++attempt;
    ISO15693ErrorCode rc = nfc15693.readSingleBlock(uid, blockNo, blockData, blockSize);
    if (rc == ISO15693_EC_OK) {
      if (attempt > 1) {
        Serial.print(F("INFO block_recovered block="));
        Serial.print(blockNo);
        Serial.print(F(" attempts="));
        Serial.print(attempt);
        Serial.println();
      }
      return true;
    }

    Serial.print(F("INFO block_retry block="));
    Serial.print(blockNo);
    Serial.print(F(" attempt="));
    Serial.print(attempt);
    Serial.print(F(" rc="));
    Serial.print(static_cast<int>(rc));
    Serial.println();

    ensureRfReady();
    delay(5);
  }

  Serial.print(F("ERROR block_failed block="));
  Serial.print(blockNo);
  Serial.print(F(" attempts="));
  Serial.print(attempt);
  Serial.println();
  return false;
}

bool tryReadMultipleBlocksWithRetry(uint8_t *uid, uint8_t firstBlock, uint8_t blockCount, uint8_t *blockData, uint8_t blockSize) {
  for (uint8_t attempt = 1; attempt <= MAX_MULTI_READ_RETRIES; ++attempt) {
    ISO15693ErrorCode rc = readMultipleBlocks(uid, firstBlock, blockCount, blockData, blockSize);
    if (rc == ISO15693_EC_OK) {
      if (attempt > 1) {
        Serial.print(F("INFO chunk_recovered first_block="));
        Serial.print(firstBlock);
        Serial.print(F(" count="));
        Serial.print(blockCount);
        Serial.print(F(" attempts="));
        Serial.print(attempt);
        Serial.println();
      }
      return true;
    }

    Serial.print(F("INFO chunk_retry first_block="));
    Serial.print(firstBlock);
    Serial.print(F(" count="));
    Serial.print(blockCount);
    Serial.print(F(" attempt="));
    Serial.print(attempt);
    Serial.print(F(" rc="));
    Serial.print(static_cast<int>(rc));
    Serial.println();

    ensureRfReady();
    delay(5);
  }

  return false;
}

uint8_t readBlocksAdaptive(uint8_t *uid, uint8_t firstBlock, uint8_t remainingCount, uint8_t *blockData, uint8_t blockSize) {
  static uint8_t learnedChunkCount = 0;
  uint8_t preferredChunkCount = learnedChunkCount > 0 ? learnedChunkCount : getBlocksPerRead(blockSize);
  uint8_t chunkCount = min<uint8_t>(preferredChunkCount, remainingCount);

  while (chunkCount > 1) {
    if (tryReadMultipleBlocksWithRetry(uid, firstBlock, chunkCount, blockData, blockSize)) {
      learnedChunkCount = chunkCount;
      return chunkCount;
    }

    uint8_t newChunkCount = max<uint8_t>(1, chunkCount / 2);
    Serial.print(F("INFO chunk_fallback first_block="));
    Serial.print(firstBlock);
    Serial.print(F(" from="));
    Serial.print(chunkCount);
    Serial.print(F(" to="));
    Serial.print(newChunkCount);
    Serial.println();
    chunkCount = newChunkCount;
  }

  if (!tryReadSingleBlockWithRetry(uid, firstBlock, blockData, blockSize)) {
    return 0;
  }
  learnedChunkCount = 1;
  return 1;
}

bool readCompactHexDump(uint8_t *uid, uint8_t blockSize, uint8_t numBlocks) {
  Serial.println(F("COMPACT_BEGIN"));

  uint8_t blockData[ISO15693_READ_BUFFER_BYTES];

  for (uint16_t firstBlock = 0; firstBlock < numBlocks;) {
    uint8_t remaining = static_cast<uint8_t>(numBlocks - firstBlock);
    uint8_t blockCount = readBlocksAdaptive(uid, static_cast<uint8_t>(firstBlock), remaining, blockData, blockSize);
    if (blockCount == 0) {
      Serial.println(F("COMPACT_END"));
      return false;
    }

    for (uint8_t blockIndex = 0; blockIndex < blockCount; ++blockIndex) {
      uint16_t offset = static_cast<uint16_t>(blockIndex) * blockSize;
      printHexLine(blockData + offset, blockSize);
    }

    firstBlock += blockCount;
  }

  Serial.println(F("COMPACT_END"));
  return true;
}

template <typename Reader>
bool setupRf(Reader &reader, const __FlashStringHelper *protocolName) {
  reader.reset();
  if (reader.setupRF()) {
    return true;
  }

  Serial.print(F("INFO rf_setup_failed protocol="));
  Serial.println(protocolName);
  return false;
}

uint8_t mifareClassicSakBase(uint8_t sak) {
  return sak & static_cast<uint8_t>(~0x20);
}

const __FlashStringHelper *classifyIso14443A(uint8_t sak) {
  const bool isoDepCompatible = (sak & 0x20) != 0;
  switch (mifareClassicSakBase(sak)) {
    case 0x00:
      if (isoDepCompatible) {
        return F("ISO14443_4_COMPATIBLE");
      }
      return F("MIFARE_ULTRALIGHT_OR_NTAG");
    case 0x08:
      if (isoDepCompatible) {
        return F("MIFARE_CLASSIC_1K_ISO14443_4_COMPATIBLE");
      }
      return F("MIFARE_CLASSIC_1K");
    case 0x09:
      if (isoDepCompatible) {
        return F("MIFARE_MINI_ISO14443_4_COMPATIBLE");
      }
      return F("MIFARE_MINI");
    case 0x18:
      if (isoDepCompatible) {
        return F("MIFARE_CLASSIC_4K_ISO14443_4_COMPATIBLE");
      }
      return F("MIFARE_CLASSIC_4K");
    default:
      return F("UNKNOWN_TYPE_A");
  }
}

bool isMifareClassicSak(uint8_t sak) {
  uint8_t baseSak = mifareClassicSakBase(sak);
  return baseSak == 0x08 || baseSak == 0x09 || baseSak == 0x18;
}

uint16_t mifareClassicBlockCount(uint8_t sak) {
  switch (mifareClassicSakBase(sak)) {
    case 0x09:
      return 20;  // MIFARE Mini: 5 sectors * 4 blocks.
    case 0x18:
      return 256; // MIFARE Classic 4K.
    case 0x08:
    default:
      return 64;  // MIFARE Classic 1K.
  }
}

uint8_t mifareClassicSectorCount(uint8_t sak) {
  switch (mifareClassicSakBase(sak)) {
    case 0x09:
      return 5;
    case 0x18:
      return 40;
    case 0x08:
    default:
      return 16;
  }
}

uint16_t mifareClassicSectorFirstBlock(uint8_t sector) {
  if (sector < 32) {
    return static_cast<uint16_t>(sector) * 4;
  }
  return static_cast<uint16_t>(128 + (sector - 32) * 16);
}

uint8_t mifareClassicSectorBlockCount(uint8_t sector) {
  return sector < 32 ? 4 : 16;
}

uint8_t activateTypeASafe(uint8_t *buffer, uint8_t kind) {
  uint8_t cmd[7] = {0};

  if (!pn5180LoadRfConfigSafe(0x00, 0x80)) {
    return 0;
  }
  if (!pn5180WriteRegisterWithAndMaskSafe(SYSTEM_CONFIG, 0xFFFFFFBF)) {
    return 0;
  }
  if (!pn5180WriteRegisterWithAndMaskSafe(CRC_RX_CONFIG, 0xFFFFFFFE)) {
    return 0;
  }
  if (!pn5180WriteRegisterWithAndMaskSafe(CRC_TX_CONFIG, 0xFFFFFFFE)) {
    return 0;
  }

  cmd[0] = kind == 0 ? 0x26 : 0x52;
  if (!pn5180TransceiveRfSafe(cmd, 1, 0x07, 2, buffer, 30)) {
    return 0;
  }

  cmd[0] = 0x93;
  cmd[1] = 0x20;
  if (!pn5180TransceiveRfSafe(cmd, 2, 0x00, 5, cmd + 2, 35)) {
    return 0;
  }

  if (!pn5180WriteRegisterWithOrMaskSafe(CRC_RX_CONFIG, 0x01)) {
    return 0;
  }
  if (!pn5180WriteRegisterWithOrMaskSafe(CRC_TX_CONFIG, 0x01)) {
    return 0;
  }

  cmd[0] = 0x93;
  cmd[1] = 0x70;
  if (!pn5180TransceiveRfSafe(cmd, 7, 0x00, 1, buffer + 2, 35)) {
    return 0;
  }

  if ((buffer[2] & 0x04) == 0) {
    for (uint8_t i = 0; i < 4; ++i) {
      buffer[3 + i] = cmd[2 + i];
    }
    return 4;
  }

  if (cmd[2] != 0x88) {
    return 0;
  }
  for (uint8_t i = 0; i < 3; ++i) {
    buffer[3 + i] = cmd[3 + i];
  }

  if (!pn5180WriteRegisterWithAndMaskSafe(CRC_RX_CONFIG, 0xFFFFFFFE)) {
    return 0;
  }
  if (!pn5180WriteRegisterWithAndMaskSafe(CRC_TX_CONFIG, 0xFFFFFFFE)) {
    return 0;
  }

  cmd[0] = 0x95;
  cmd[1] = 0x20;
  if (!pn5180TransceiveRfSafe(cmd, 2, 0x00, 5, cmd + 2, 35)) {
    return 0;
  }
  for (uint8_t i = 0; i < 4; ++i) {
    buffer[6 + i] = cmd[2 + i];
  }

  if (!pn5180WriteRegisterWithOrMaskSafe(CRC_RX_CONFIG, 0x01)) {
    return 0;
  }
  if (!pn5180WriteRegisterWithOrMaskSafe(CRC_TX_CONFIG, 0x01)) {
    return 0;
  }

  cmd[0] = 0x95;
  cmd[1] = 0x70;
  if (!pn5180TransceiveRfSafe(cmd, 7, 0x00, 1, buffer + 2, 35)) {
    return 0;
  }

  return 7;
}

bool reselectIso14443A(const uint8_t *expectedUid, uint8_t expectedUidLength, uint8_t &sak) {
  if (!setupRfSafe(0x00, 0x80, false, F("ISO14443A"))) {
    return false;
  }

  uint8_t response[10] = {0};
  uint8_t uidLength = activateTypeASafe(response, 1);
  if (uidLength != expectedUidLength) {
    return false;
  }

  for (uint8_t i = 0; i < uidLength; ++i) {
    if (response[3 + i] != expectedUid[i]) {
      return false;
    }
  }

  sak = response[2];
  return true;
}

bool mifareClassicAuthenticate(uint8_t blockAddress, uint8_t keyType, const uint8_t key[6], const uint8_t uid[4]) {
  uint8_t command[13] = {
    PN5180_MIFARE_AUTHENTICATE,
    key[0], key[1], key[2], key[3], key[4], key[5],
    keyType,
    blockAddress,
    uid[0], uid[1], uid[2], uid[3],
  };
  uint8_t response[1] = {0xFF};

  lastMifareAuthStatus = 0xFE;
  pn5180ClearIRQStatusSafe(0xFFFFFFFF);
  if (!pn5180DirectCommand(command, sizeof(command), response, sizeof(response))) {
    lastMifareAuthStatus = 0xFD;
    return false;
  }
  lastMifareAuthStatus = response[0];
  return response[0] == 0x00;
}

void encodeUint32Le(uint32_t value, uint8_t *buffer) {
  buffer[0] = static_cast<uint8_t>(value & 0xFF);
  buffer[1] = static_cast<uint8_t>((value >> 8) & 0xFF);
  buffer[2] = static_cast<uint8_t>((value >> 16) & 0xFF);
  buffer[3] = static_cast<uint8_t>((value >> 24) & 0xFF);
}

uint32_t decodeUint32Le(const uint8_t *buffer) {
  return static_cast<uint32_t>(buffer[0])
      | (static_cast<uint32_t>(buffer[1]) << 8)
      | (static_cast<uint32_t>(buffer[2]) << 16)
      | (static_cast<uint32_t>(buffer[3]) << 24);
}

bool pn5180WriteRegisterSafe(uint8_t reg, uint32_t value) {
  uint8_t command[6] = {PN5180_WRITE_REGISTER_SAFE, reg, 0, 0, 0, 0};
  encodeUint32Le(value, &command[2]);
  return pn5180DirectCommand(command, sizeof(command));
}

bool pn5180WriteRegisterWithAndMaskSafe(uint8_t reg, uint32_t mask) {
  uint8_t command[6] = {PN5180_WRITE_REGISTER_AND_MASK_SAFE, reg, 0, 0, 0, 0};
  encodeUint32Le(mask, &command[2]);
  return pn5180DirectCommand(command, sizeof(command));
}

bool pn5180WriteRegisterWithOrMaskSafe(uint8_t reg, uint32_t mask) {
  uint8_t command[6] = {PN5180_WRITE_REGISTER_OR_MASK_SAFE, reg, 0, 0, 0, 0};
  encodeUint32Le(mask, &command[2]);
  return pn5180DirectCommand(command, sizeof(command));
}

bool pn5180ReadRegisterSafe(uint8_t reg, uint32_t *value) {
  uint8_t command[2] = {PN5180_READ_REGISTER_SAFE, reg};
  uint8_t response[4] = {0};
  if (!pn5180DirectCommand(command, sizeof(command), response, sizeof(response))) {
    return false;
  }
  *value = decodeUint32Le(response);
  return true;
}

bool pn5180ClearIRQStatusSafe(uint32_t irqMask) {
  return pn5180WriteRegisterSafe(IRQ_CLEAR, irqMask);
}

bool pn5180GetIRQStatusSafe(uint32_t *irqStatus) {
  return pn5180ReadRegisterSafe(IRQ_STATUS, irqStatus);
}

bool pn5180ResetSafe() {
  digitalWrite(PN5180_RST_PIN, LOW);
  delay(10);
  digitalWrite(PN5180_RST_PIN, HIGH);
  delay(10);

  uint32_t startedAt = millis();
  uint32_t irqStatus = 0;
  while (true) {
    if (pn5180GetIRQStatusSafe(&irqStatus) && (irqStatus & IDLE_IRQ_STAT)) {
      pn5180ClearIRQStatusSafe(0xFFFFFFFF);
      return true;
    }
    if ((millis() - startedAt) > PN5180_RESET_TIMEOUT_MS) {
      return false;
    }
    delay(2);
  }
}

bool pn5180LoadRfConfigSafe(uint8_t txConf, uint8_t rxConf) {
  uint8_t command[3] = {PN5180_LOAD_RF_CONFIG_SAFE, txConf, rxConf};
  return pn5180DirectCommand(command, sizeof(command));
}

bool pn5180RfOnSafe() {
  uint8_t command[2] = {PN5180_RF_ON_SAFE, 0x00};
  if (!pn5180DirectCommand(command, sizeof(command))) {
    return false;
  }

  uint32_t startedAt = millis();
  uint32_t irqStatus = 0;
  while (true) {
    if (pn5180GetIRQStatusSafe(&irqStatus) && (irqStatus & TX_RFON_IRQ_STAT)) {
      pn5180ClearIRQStatusSafe(TX_RFON_IRQ_STAT);
      return true;
    }
    if ((millis() - startedAt) > PN5180_RF_ON_TIMEOUT_MS) {
      return false;
    }
    delay(2);
  }
}

bool setupRfSafe(uint8_t txConf, uint8_t rxConf, bool startTransceive, const __FlashStringHelper *protocolName) {
  if (!pn5180ResetSafe()) {
    Serial.print(F("INFO rf_reset_failed protocol="));
    Serial.println(protocolName);
    return false;
  }
  if (!pn5180LoadRfConfigSafe(txConf, rxConf)) {
    Serial.print(F("INFO rf_config_failed protocol="));
    Serial.println(protocolName);
    return false;
  }
  if (!pn5180RfOnSafe()) {
    Serial.print(F("INFO rf_on_failed protocol="));
    Serial.println(protocolName);
    return false;
  }
  if (startTransceive) {
    if (!pn5180WriteRegisterWithAndMaskSafe(SYSTEM_CONFIG, 0xFFFFFFF8)) {
      return false;
    }
    if (!pn5180WriteRegisterWithOrMaskSafe(SYSTEM_CONFIG, 0x00000003)) {
      return false;
    }
  }
  return true;
}

bool pn5180SendRfDataSafe(const uint8_t *data, uint8_t len, uint8_t validBits = 0) {
  if (len > 18) {
    return false;
  }

  uint8_t command[20] = {0};
  command[0] = PN5180_SEND_DATA_SAFE;
  command[1] = validBits;
  for (uint8_t i = 0; i < len; ++i) {
    command[2 + i] = data[i];
  }

  if (!pn5180WriteRegisterWithAndMaskSafe(SYSTEM_CONFIG, 0xFFFFFFF8)) {
    return false;
  }
  if (!pn5180WriteRegisterWithOrMaskSafe(SYSTEM_CONFIG, 0x00000003)) {
    return false;
  }
  return pn5180DirectCommand(command, static_cast<size_t>(len) + 2);
}

bool pn5180ReadRfDataSafe(uint8_t len, uint8_t *buffer) {
  uint8_t command[2] = {PN5180_READ_DATA_SAFE, 0x00};
  return pn5180DirectCommand(command, sizeof(command), buffer, len);
}

bool pn5180WaitForRx(uint8_t expectedLen, uint32_t timeoutMs) {
  uint32_t startedAt = millis();
  uint32_t irqStatus = 0;
  while (true) {
    if (!pn5180GetIRQStatusSafe(&irqStatus)) {
      return false;
    }
    if (irqStatus & RX_IRQ_STAT) {
      break;
    }
    if ((millis() - startedAt) > timeoutMs) {
      pn5180WriteRegisterWithAndMaskSafe(SYSTEM_CONFIG, 0xFFFFFFF8);
      return false;
    }
    delay(1);
  }

  uint32_t rxStatus = 0;
  if (!pn5180ReadRegisterSafe(RX_STATUS, &rxStatus)) {
    return false;
  }
  return static_cast<uint16_t>(rxStatus & 0x000001FF) == expectedLen;
}

bool pn5180TransceiveRfSafe(const uint8_t *command, uint8_t commandLen, uint8_t validBits, uint8_t expectedLen, uint8_t *response, uint32_t timeoutMs) {
  pn5180ClearIRQStatusSafe(0xFFFFFFFF);
  if (!pn5180SendRfDataSafe(command, commandLen, validBits)) {
    return false;
  }
  if (!pn5180WaitForRx(expectedLen, timeoutMs)) {
    return false;
  }
  return pn5180ReadRfDataSafe(expectedLen, response);
}

bool mifareClassicReadBlockSafe(uint8_t blockAddress, uint8_t *buffer) {
  uint8_t command[2] = {0x30, blockAddress};
  return pn5180TransceiveRfSafe(command, sizeof(command), 0, MIFARE_CLASSIC_BLOCK_SIZE, buffer, MIFARE_CLASSIC_READ_TIMEOUT_MS);
}

bool mifareClassicWriteBlockSafe(uint8_t blockAddress, const uint8_t *buffer) {
  uint8_t command[2] = {0xA0, blockAddress};
  uint8_t ack[1] = {0x00};

  pn5180WriteRegisterWithAndMaskSafe(CRC_RX_CONFIG, 0xFFFFFFFE);
  if (!pn5180SendRfDataSafe(command, sizeof(command), 0x00)) {
    pn5180WriteRegisterWithOrMaskSafe(CRC_RX_CONFIG, 0x01);
    return false;
  }
  delay(5);
  if (!pn5180ReadRfDataSafe(1, ack) || ((ack[0] & 0x0F) != 0x0A)) {
    pn5180WriteRegisterWithOrMaskSafe(CRC_RX_CONFIG, 0x01);
    return false;
  }

  if (!pn5180SendRfDataSafe(buffer, MIFARE_CLASSIC_BLOCK_SIZE, 0x00)) {
    pn5180WriteRegisterWithOrMaskSafe(CRC_RX_CONFIG, 0x01);
    return false;
  }
  delay(10);
  ack[0] = 0x00;
  if (!pn5180ReadRfDataSafe(1, ack) || ((ack[0] & 0x0F) != 0x0A)) {
    pn5180WriteRegisterWithOrMaskSafe(CRC_RX_CONFIG, 0x01);
    return false;
  }

  pn5180WriteRegisterWithOrMaskSafe(CRC_RX_CONFIG, 0x01);
  return true;
}

void mifareHaltSafe() {
  uint8_t command[2] = {0x50, 0x00};
  pn5180SendRfDataSafe(command, sizeof(command));
  pn5180WriteRegisterWithAndMaskSafe(SYSTEM_CONFIG, 0xFFFFFFF8);
}

bool readMifareClassicBlockFresh(
    uint8_t blockAddress,
    uint8_t keyType,
    const uint8_t key[6],
    const uint8_t *expectedUid,
    uint8_t expectedUidLength,
    uint8_t &sak,
    uint8_t *buffer,
    bool &authenticated) {
  authenticated = false;
  if (expectedUidLength != 4) {
    return false;
  }
  if (!setupRfSafe(0x00, 0x80, false, F("ISO14443A"))) {
    return false;
  }

  uint8_t response[10] = {0};
  uint8_t uidLength = activateTypeASafe(response, 1);
  if (uidLength != expectedUidLength) {
    return false;
  }
  for (uint8_t i = 0; i < uidLength; ++i) {
    if (response[3 + i] != expectedUid[i]) {
      return false;
    }
  }

  sak = response[2];
  uint8_t uid[4] = {response[3], response[4], response[5], response[6]};
  if (!mifareClassicAuthenticate(blockAddress, keyType, key, uid)) {
    mifareHaltSafe();
    return false;
  }

  authenticated = true;
  bool readOk = mifareClassicReadBlockSafe(blockAddress, buffer);
  mifareHaltSafe();
  return readOk;
}

int hexNibble(char ch) {
  if (ch >= '0' && ch <= '9') {
    return ch - '0';
  }
  if (ch >= 'a' && ch <= 'f') {
    return ch - 'a' + 10;
  }
  if (ch >= 'A' && ch <= 'F') {
    return ch - 'A' + 10;
  }
  return -1;
}

bool parseMifareKeyText(const String &text, uint8_t key[6]) {
  if (text.length() != 12) {
    return false;
  }
  for (uint8_t i = 0; i < 6; ++i) {
    int high = hexNibble(text[i * 2]);
    int low = hexNibble(text[i * 2 + 1]);
    if (high < 0 || low < 0) {
      return false;
    }
    key[i] = static_cast<uint8_t>((high << 4) | low);
  }
  return true;
}

bool parseHexBytesText(const String &text, uint8_t *buffer, uint8_t expectedBytes) {
  if (text.length() != static_cast<uint16_t>(expectedBytes) * 2) {
    return false;
  }
  for (uint8_t i = 0; i < expectedBytes; ++i) {
    int high = hexNibble(text[i * 2]);
    int low = hexNibble(text[i * 2 + 1]);
    if (high < 0 || low < 0) {
      return false;
    }
    buffer[i] = static_cast<uint8_t>((high << 4) | low);
  }
  return true;
}

bool mifareClassicIsTrailerBlock(uint16_t block) {
  if (block < 128) {
    return (block % 4) == 3;
  }
  return ((block - 128) % 16) == 15;
}

String nextCommandToken(const String &line, int &cursor) {
  while (cursor < static_cast<int>(line.length()) && line[cursor] == ' ') {
    ++cursor;
  }
  int start = cursor;
  while (cursor < static_cast<int>(line.length()) && line[cursor] != ' ') {
    ++cursor;
  }
  return line.substring(start, cursor);
}

void printBruteResult(uint8_t block, char keyType, const uint8_t key[6], const __FlashStringHelper *status) {
  Serial.print(F("PND1 BRUTE_RESULT block="));
  Serial.print(block);
  Serial.print(F(" key_type="));
  Serial.print(keyType);
  Serial.print(F(" key="));
  printMifareKey(key);
  Serial.print(F(" status="));
  Serial.println(status);
}

void printBruteOkResult(uint8_t block, char keyType, const uint8_t key[6], const uint8_t data[16]) {
  Serial.print(F("PND1 BRUTE_RESULT block="));
  Serial.print(block);
  Serial.print(F(" key_type="));
  Serial.print(keyType);
  Serial.print(F(" key="));
  printMifareKey(key);
  Serial.print(F(" status=ok data="));
  printHexCompact(data, MIFARE_CLASSIC_BLOCK_SIZE);
  Serial.println();
}

void printBruteBatchEnd(uint8_t block, uint16_t startIndex, const String &batchId, uint16_t checked, const __FlashStringHelper *status) {
  Serial.print(F("PND1 BRUTE_BATCH_END block="));
  Serial.print(block);
  Serial.print(F(" start="));
  Serial.print(startIndex);
  Serial.print(F(" batch="));
  Serial.print(batchId);
  Serial.print(F(" checked="));
  Serial.print(checked);
  Serial.print(F(" status="));
  Serial.println(status);
}

uint8_t mifareClassicSectorForBlock(uint16_t block) {
  if (block < 128) {
    return static_cast<uint8_t>(block / 4);
  }
  return static_cast<uint8_t>(32 + ((block - 128) / 16));
}

bool tryMifareClassicBruteKey(
    uint8_t blockValue,
    char keyTypeChar,
    const uint8_t key[6],
    bool readWholeSector,
    bool emitFailure) {
  uint8_t keyType = keyTypeChar == 'B' ? MIFARE_KEY_B : MIFARE_KEY_A;
  uint8_t data[MIFARE_CLASSIC_BLOCK_SIZE] = {0};
  bool authenticated = false;

  for (uint8_t attempt = 1; attempt <= MIFARE_CLASSIC_BRUTE_READ_RETRIES; ++attempt) {
    if (!setupRfSafe(0x00, 0x80, false, F("ISO14443A"))) {
      continue;
    }

    uint8_t response[10] = {0};
    uint8_t uidLength = activateTypeASafe(response, 1);
    if (uidLength == 0) {
      continue;
    }
    if (uidLength != 4) {
      if (emitFailure) {
        printBruteResult(blockValue, keyTypeChar, key, F("uid_unsupported"));
      }
      return false;
    }

    uint8_t uid[4] = {response[3], response[4], response[5], response[6]};
    if (!mifareClassicAuthenticate(blockValue, keyType, key, uid)) {
      mifareHaltSafe();
      delay(8);
      continue;
    }
    authenticated = true;

    if (mifareClassicReadBlockSafe(blockValue, data)) {
      if (readWholeSector) {
        uint8_t sector = mifareClassicSectorForBlock(blockValue);
        uint16_t firstBlock = mifareClassicSectorFirstBlock(sector);
        uint8_t blockCount = mifareClassicSectorBlockCount(sector);
        printBruteOkResult(blockValue, keyTypeChar, key, data);
        for (uint8_t offset = 0; offset < blockCount; ++offset) {
          uint16_t sectorBlock = firstBlock + offset;
          if (sectorBlock == blockValue || sectorBlock > 255) {
            continue;
          }
          uint8_t sectorData[MIFARE_CLASSIC_BLOCK_SIZE] = {0};
          if (mifareClassicReadBlockSafe(static_cast<uint8_t>(sectorBlock), sectorData)) {
            printBruteOkResult(static_cast<uint8_t>(sectorBlock), keyTypeChar, key, sectorData);
          } else {
            printBruteResult(static_cast<uint8_t>(sectorBlock), keyTypeChar, key, F("read_failed"));
          }
        }
        mifareHaltSafe();
        Serial.print(F("PND1 BRUTE_SECTOR_END sector="));
        Serial.print(sector);
        Serial.print(F(" key_type="));
        Serial.print(keyTypeChar);
        Serial.print(F(" key="));
        printMifareKey(key);
        Serial.println();
        return true;
      }
      mifareHaltSafe();
      printBruteOkResult(blockValue, keyTypeChar, key, data);
      return true;
    }
    mifareHaltSafe();
    delay(8);
  }

  if (emitFailure) {
    printBruteResult(blockValue, keyTypeChar, key, authenticated ? F("read_failed") : F("auth_failed"));
  }
  return false;
}

void handleMifareBruteCommand(const String &line, bool readWholeSector = false) {
  int cursor = 0;
  String prefix = nextCommandToken(line, cursor);
  String command = nextCommandToken(line, cursor);
  String blockToken = nextCommandToken(line, cursor);
  String keyTypeToken = nextCommandToken(line, cursor);
  String keyToken = nextCommandToken(line, cursor);

  if (prefix != F("PND1") ||
      !(command == F("BRUTE") || command == F("BRUTE_SECTOR")) ||
      blockToken.length() == 0 ||
      keyTypeToken.length() == 0) {
    Serial.println(F("PND1 BRUTE_RESULT status=bad_command"));
    return;
  }

  int blockValue = blockToken.toInt();
  if (blockValue < 0 || blockValue > 255) {
    Serial.println(F("PND1 BRUTE_RESULT status=bad_block"));
    return;
  }

  char keyTypeChar = keyTypeToken[0] == 'B' || keyTypeToken[0] == 'b' ? 'B' : 'A';
  uint8_t key[6] = {0};
  if (!parseMifareKeyText(keyToken, key)) {
    Serial.println(F("PND1 BRUTE_RESULT status=bad_key"));
    return;
  }

  tryMifareClassicBruteKey(static_cast<uint8_t>(blockValue), keyTypeChar, key, readWholeSector, true);
}

void handleMifareBruteBatchCommand(const String &line) {
  int cursor = 0;
  String prefix = nextCommandToken(line, cursor);
  String command = nextCommandToken(line, cursor);
  String blockToken = nextCommandToken(line, cursor);
  String startToken = nextCommandToken(line, cursor);
  String batchToken = nextCommandToken(line, cursor);

  if (prefix != F("PND1") ||
      command != F("BRUTE_BATCH") ||
      blockToken.length() == 0 ||
      startToken.length() == 0 ||
      batchToken.length() == 0) {
    Serial.println(F("PND1 BRUTE_BATCH_END status=bad_command"));
    return;
  }

  int blockValue = blockToken.toInt();
  if (blockValue < 0 || blockValue > 255) {
    Serial.println(F("PND1 BRUTE_BATCH_END status=bad_block"));
    return;
  }

  uint16_t startIndex = static_cast<uint16_t>(startToken.toInt());
  uint16_t checked = 0;
  while (cursor < static_cast<int>(line.length())) {
    String attemptToken = nextCommandToken(line, cursor);
    if (attemptToken.length() == 0) {
      break;
    }
    if (attemptToken.length() != 13) {
      printBruteBatchEnd(static_cast<uint8_t>(blockValue), startIndex, batchToken, checked, F("bad_key"));
      return;
    }

    char keyTypeChar = attemptToken[0] == 'B' || attemptToken[0] == 'b' ? 'B' : 'A';
    uint8_t key[6] = {0};
    if (!parseMifareKeyText(attemptToken.substring(1), key)) {
      printBruteBatchEnd(static_cast<uint8_t>(blockValue), startIndex, batchToken, checked, F("bad_key"));
      return;
    }

    ++checked;
    if (tryMifareClassicBruteKey(static_cast<uint8_t>(blockValue), keyTypeChar, key, true, false)) {
      printBruteBatchEnd(static_cast<uint8_t>(blockValue), startIndex, batchToken, checked, F("found"));
      return;
    }
  }

  printBruteBatchEnd(static_cast<uint8_t>(blockValue), startIndex, batchToken, checked, F("not_found"));
}

void printWriteResult(uint16_t block, const __FlashStringHelper *status, char keyType = '-', const uint8_t *key = nullptr) {
  Serial.print(F("PND1 WRITE_RESULT block="));
  Serial.print(block);
  Serial.print(F(" status="));
  Serial.print(status);
  if (keyType != '-') {
    Serial.print(F(" key_type="));
    Serial.print(keyType);
    Serial.print(F(" key="));
    printMifareKey(key ? key : MIFARE_CLASSIC_KEYS[0]);
  }
  Serial.println();
}

void printIso15693WriteResult(uint16_t block, const __FlashStringHelper *status, ISO15693ErrorCode rc = ISO15693_EC_OK) {
  Serial.print(F("PND1 WRITE_RESULT block="));
  Serial.print(block);
  Serial.print(F(" status="));
  Serial.print(status);
  Serial.print(F(" protocol=ISO15693 rc="));
  Serial.println(static_cast<int>(rc));
}

bool parseHexBytesTextDynamic(const String &text, uint8_t *buffer, uint8_t expectedBytes) {
  return parseHexBytesText(text, buffer, expectedBytes);
}

bool writeIso15693BlockFresh(uint8_t blockAddress, const uint8_t *data, uint8_t blockSize, bool verify, ISO15693ErrorCode &rc) {
  uint8_t uid[8] = {0};
  if (!setupRfSafe(0x0D, 0x8D, true, F("ISO15693"))) {
    rc = ISO15693_EC_UNKNOWN_ERROR;
    return false;
  }

  rc = getIso15693InventorySafe(uid);
  if (rc != ISO15693_EC_OK) {
    return false;
  }

  rc = nfc15693.writeSingleBlock(uid, blockAddress, const_cast<uint8_t *>(data), blockSize);
  if (rc != ISO15693_EC_OK) {
    return false;
  }

  if (!verify) {
    return true;
  }

  uint8_t verifyData[ISO15693_MAX_WRITE_BLOCK_SIZE] = {0};
  rc = nfc15693.readSingleBlock(uid, blockAddress, verifyData, blockSize);
  if (rc != ISO15693_EC_OK) {
    return false;
  }

  for (uint8_t i = 0; i < blockSize; ++i) {
    if (verifyData[i] != data[i]) {
      rc = ISO15693_EC_UNKNOWN_ERROR;
      return false;
    }
  }
  return true;
}

void handleIso15693WriteCommand(const String &line) {
  int cursor = 0;
  String prefix = nextCommandToken(line, cursor);
  String command = nextCommandToken(line, cursor);
  String blockToken = nextCommandToken(line, cursor);
  String dataToken = nextCommandToken(line, cursor);

  if (prefix != F("PND1") || command != F("WRITE_ISO15693") || blockToken.length() == 0 || dataToken.length() == 0) {
    Serial.println(F("PND1 WRITE_RESULT status=bad_command protocol=ISO15693"));
    return;
  }

  int blockValue = blockToken.toInt();
  if (blockValue < 0 || blockValue > 255) {
    Serial.println(F("PND1 WRITE_RESULT status=bad_block protocol=ISO15693"));
    return;
  }

  bool verify = false;
  while (cursor < static_cast<int>(line.length())) {
    String option = nextCommandToken(line, cursor);
    if (option == F("VERIFY")) {
      verify = true;
    }
  }

  uint8_t uid[8] = {0};
  if (!setupRfSafe(0x0D, 0x8D, true, F("ISO15693"))) {
    printIso15693WriteResult(static_cast<uint16_t>(blockValue), F("rf_setup_failed"), ISO15693_EC_UNKNOWN_ERROR);
    return;
  }

  ISO15693ErrorCode rc = getIso15693InventorySafe(uid);
  if (rc != ISO15693_EC_OK) {
    printIso15693WriteResult(static_cast<uint16_t>(blockValue), F("no_card"), rc);
    return;
  }

  SystemInfoData info = readSystemInfo(uid);
  if (info.rc != ISO15693_EC_OK || !info.hasMemorySize || info.blockSize == 0 || info.blockSize > ISO15693_MAX_WRITE_BLOCK_SIZE) {
    printIso15693WriteResult(static_cast<uint16_t>(blockValue), F("bad_system_info"), info.rc);
    return;
  }

  if (blockValue >= info.numBlocks) {
    printIso15693WriteResult(static_cast<uint16_t>(blockValue), F("bad_block"), ISO15693_EC_BLOCK_NOT_AVAILABLE);
    return;
  }

  uint8_t data[ISO15693_MAX_WRITE_BLOCK_SIZE] = {0};
  if (!parseHexBytesTextDynamic(dataToken, data, info.blockSize)) {
    printIso15693WriteResult(static_cast<uint16_t>(blockValue), F("bad_data"), ISO15693_EC_UNKNOWN_ERROR);
    return;
  }

  for (uint8_t attempt = 0; attempt < 3; ++attempt) {
    if (writeIso15693BlockFresh(static_cast<uint8_t>(blockValue), data, info.blockSize, verify, rc)) {
      printIso15693WriteResult(static_cast<uint16_t>(blockValue), F("ok"), rc);
      return;
    }
    delay(10);
  }

  if (rc == ISO15693_EC_BLOCK_IS_LOCKED || rc == ISO15693_EC_BLOCK_ALREADY_LOCKED) {
    printIso15693WriteResult(static_cast<uint16_t>(blockValue), F("block_locked"), rc);
    return;
  }
  printIso15693WriteResult(static_cast<uint16_t>(blockValue), F("failed"), rc);
}

bool writeMifareClassicBlockFresh(
    uint8_t blockAddress,
    uint8_t keyType,
    const uint8_t key[6],
    const uint8_t data[MIFARE_CLASSIC_BLOCK_SIZE],
    bool verify) {
  if (!setupRfSafe(0x00, 0x80, false, F("ISO14443A"))) {
    return false;
  }

  uint8_t response[10] = {0};
  uint8_t uidLength = activateTypeASafe(response, 1);
  if (uidLength != 4) {
    return false;
  }

  uint8_t sak = response[2];
  if (!isMifareClassicSak(sak) || blockAddress >= mifareClassicBlockCount(sak)) {
    return false;
  }

  uint8_t uid[4] = {response[3], response[4], response[5], response[6]};
  if (!mifareClassicAuthenticate(blockAddress, keyType, key, uid)) {
    mifareHaltSafe();
    return false;
  }

  if (!mifareClassicWriteBlockSafe(blockAddress, data)) {
    mifareHaltSafe();
    return false;
  }
  mifareHaltSafe();

  if (!verify) {
    return true;
  }

  uint8_t verifyData[MIFARE_CLASSIC_BLOCK_SIZE] = {0};
  bool authenticated = false;
  const uint8_t *expectedVerifyUid = blockAddress == 0 ? data : uid;
  if (!readMifareClassicBlockFresh(blockAddress, keyType, key, expectedVerifyUid, 4, sak, verifyData, authenticated)) {
    return false;
  }
  for (uint8_t i = 0; i < MIFARE_CLASSIC_BLOCK_SIZE; ++i) {
    if (verifyData[i] != data[i]) {
      return false;
    }
  }
  return true;
}

bool readMagicAck(const uint8_t *command, uint8_t len, uint8_t validBits) {
  uint8_t ack[1] = {0x00};
  pn5180ClearIRQStatusSafe(0xFFFFFFFF);
  if (!pn5180SendRfDataSafe(command, len, validBits)) {
    return false;
  }
  delay(5);
  pn5180ReadRfDataSafe(1, ack);
  return (ack[0] & 0x0F) == 0x0A;
}

bool unlockMifareClassicMagicBackdoor() {
  if (!setupRfSafe(0x00, 0x80, false, F("ISO14443A"))) {
    return false;
  }

  uint8_t response[10] = {0};
  if (activateTypeASafe(response, 1) == 0) {
    return false;
  }
  mifareHaltSafe();
  delay(5);

  pn5180WriteRegisterWithAndMaskSafe(CRC_RX_CONFIG, 0xFFFFFFFE);
  pn5180WriteRegisterWithAndMaskSafe(CRC_TX_CONFIG, 0xFFFFFFFE);

  uint8_t wakeCommand[1] = {0x40};
  if (!readMagicAck(wakeCommand, sizeof(wakeCommand), 0x07)) {
    pn5180WriteRegisterWithOrMaskSafe(CRC_RX_CONFIG, 0x01);
    pn5180WriteRegisterWithOrMaskSafe(CRC_TX_CONFIG, 0x01);
    return false;
  }

  uint8_t unlockCommand[1] = {0x43};
  if (!readMagicAck(unlockCommand, sizeof(unlockCommand), 0x00)) {
    pn5180WriteRegisterWithOrMaskSafe(CRC_RX_CONFIG, 0x01);
    pn5180WriteRegisterWithOrMaskSafe(CRC_TX_CONFIG, 0x01);
    return false;
  }

  pn5180WriteRegisterWithOrMaskSafe(CRC_RX_CONFIG, 0x01);
  pn5180WriteRegisterWithOrMaskSafe(CRC_TX_CONFIG, 0x01);
  return true;
}

uint8_t writeMifareClassicMagicBlock0(const uint8_t data[MIFARE_CLASSIC_BLOCK_SIZE], bool verify) {
  if (!unlockMifareClassicMagicBackdoor()) {
    return 1;
  }
  if (!mifareClassicWriteBlockSafe(0, data)) {
    mifareHaltSafe();
    return 2;
  }
  mifareHaltSafe();

  if (!verify) {
    return 0;
  }

  uint8_t sak = 0;
  uint8_t verifyData[MIFARE_CLASSIC_BLOCK_SIZE] = {0};
  bool authenticated = false;
  if (!readMifareClassicBlockFresh(0, MIFARE_KEY_A, MIFARE_CLASSIC_KEYS[0], data, 4, sak, verifyData, authenticated)) {
    return 3;
  }
  for (uint8_t i = 0; i < MIFARE_CLASSIC_BLOCK_SIZE; ++i) {
    if (verifyData[i] != data[i]) {
      return 3;
    }
  }
  return 0;
}

const __FlashStringHelper *magicWriteStatusText(uint8_t status) {
  switch (status) {
    case 1:
      return F("magic_unlock_failed");
    case 2:
      return F("magic_write_failed");
    case 3:
      return F("magic_verify_failed");
    case 0:
    default:
      return F("ok");
  }
}

void handleMifareWriteCommand(const String &line) {
  int cursor = 0;
  String prefix = nextCommandToken(line, cursor);
  String command = nextCommandToken(line, cursor);
  String blockToken = nextCommandToken(line, cursor);
  String dataToken = nextCommandToken(line, cursor);

  if (prefix != F("PND1") || command != F("WRITE") || blockToken.length() == 0 || dataToken.length() == 0) {
    Serial.println(F("PND1 WRITE_RESULT status=bad_command"));
    return;
  }

  int blockValue = blockToken.toInt();
  if (blockValue < 0 || blockValue > 255) {
    Serial.println(F("PND1 WRITE_RESULT status=bad_block"));
    return;
  }

  bool verify = false;
  bool allowBlock0 = false;
  bool allowTrailer = false;
  uint8_t commandKey[6] = {0};
  const uint8_t *writeKey = MIFARE_CLASSIC_KEYS[0];
  while (cursor < static_cast<int>(line.length())) {
    String option = nextCommandToken(line, cursor);
    if (option == F("VERIFY")) {
      verify = true;
    } else if (option == F("ALLOW0")) {
      allowBlock0 = true;
    } else if (option == F("ALLOWTRAILER")) {
      allowTrailer = true;
    } else if (option.startsWith(F("KEY="))) {
      if (!parseMifareKeyText(option.substring(4), commandKey)) {
        printWriteResult(static_cast<uint16_t>(blockValue), F("bad_key"));
        return;
      }
      writeKey = commandKey;
    }
  }

  if ((blockValue == 0 && !allowBlock0) ||
      (mifareClassicIsTrailerBlock(static_cast<uint16_t>(blockValue)) && !allowTrailer)) {
    printWriteResult(static_cast<uint16_t>(blockValue), F("skipped_protected"));
    return;
  }

  uint8_t data[MIFARE_CLASSIC_BLOCK_SIZE] = {0};
  if (!parseHexBytesText(dataToken, data, MIFARE_CLASSIC_BLOCK_SIZE)) {
    printWriteResult(static_cast<uint16_t>(blockValue), F("bad_data"));
    return;
  }

  for (uint8_t keyTypeIndex = 0; keyTypeIndex < 2; ++keyTypeIndex) {
    uint8_t keyType = keyTypeIndex == 0 ? MIFARE_KEY_A : MIFARE_KEY_B;
    char keyTypeChar = keyTypeIndex == 0 ? 'A' : 'B';
    for (uint8_t attempt = 0; attempt < 3; ++attempt) {
      if (writeMifareClassicBlockFresh(
              static_cast<uint8_t>(blockValue),
              keyType,
              writeKey,
              data,
              verify)) {
        printWriteResult(static_cast<uint16_t>(blockValue), F("ok"), keyTypeChar, writeKey);
        return;
      }
      delay(10);
    }
  }

  if (blockValue == 0 && allowBlock0) {
    for (uint8_t attempt = 0; attempt < 3; ++attempt) {
      uint8_t magicStatus = writeMifareClassicMagicBlock0(data, verify);
      if (magicStatus == 0) {
        printWriteResult(static_cast<uint16_t>(blockValue), F("ok"), 'M');
        return;
      }
      if (attempt == 2) {
        printWriteResult(static_cast<uint16_t>(blockValue), magicWriteStatusText(magicStatus));
        return;
      }
      delay(20);
    }
  }

  printWriteResult(static_cast<uint16_t>(blockValue), F("failed"));
}

void handleMagicProbeCommand() {
  Serial.print(F("PND1 MAGIC_RESULT gen1a="));
  Serial.println(unlockMifareClassicMagicBackdoor() ? F("ok") : F("failed"));
  mifareHaltSafe();
}

bool scanIso14443AIfPresent() {
  if (!setupRfSafe(0x00, 0x80, false, F("ISO14443A"))) {
    return false;
  }

  uint8_t response[10] = {0};
  uint8_t uidLength = activateTypeASafe(response, 1);
  if (uidLength == 0) {
    return false;
  }

  uint8_t uid[10] = {0};
  for (uint8_t i = 0; i < uidLength && i < sizeof(uid); ++i) {
    uid[i] = response[3 + i];
  }

  uint8_t atqa0 = response[0];
  uint8_t atqa1 = response[1];
  uint8_t sak = response[2];

  Serial.print(F("TAG_DETECTED type=ISO14443A protocol=ISO14443A uid="));
  printHexCompact(uid, uidLength);
  Serial.print(F(" uid_length="));
  Serial.print(uidLength);
  Serial.print(F(" atqa="));
  printHexByte(atqa0);
  printHexByte(atqa1);
  Serial.print(F(" sak="));
  printHexByte(sak);
  Serial.print(F(" family="));
  Serial.println(classifyIso14443A(sak));

  mifareHaltSafe();
  return true;
}

bool scanIso15693IfPresent() {
  uint8_t uid[8] = {0};
  if (!setupRfSafe(0x0D, 0x8D, true, F("ISO15693"))) {
    return false;
  }

  ISO15693ErrorCode rc = getIso15693InventorySafe(uid);
  if (rc != ISO15693_EC_OK) {
    return false;
  }

  Serial.print(F("TAG_DETECTED type=ISO15693 protocol=ISO15693 uid="));
  printUidReversedCompact(uid, 8);
  Serial.print(F(" uid_length=8 rc="));
  Serial.println(static_cast<int>(rc));
  return true;
}

bool scanFeliCaIfPresent() {
  if (!setupRfSafe(0x09, 0x89, false, F("FELICA"))) {
    return false;
  }

  uint8_t uid[20] = {0};
  uint8_t uidLength = nfcFeliCa.readCardSerial(uid);
  if (uidLength == 0) {
    return false;
  }

  Serial.print(F("TAG_DETECTED type=FELICA protocol=FELICA uid="));
  printHexCompact(uid, uidLength);
  Serial.print(F(" uid_length="));
  Serial.println(uidLength);
  return true;
}

void handleScanCommand() {
  if (!(scanIso14443AIfPresent() || scanIso15693IfPresent() || scanFeliCaIfPresent())) {
    Serial.println(F("INFO no_card"));
  }
}

bool processSerialCommand() {
  if (!Serial.available()) {
    return false;
  }
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) {
    return false;
  }
  if (line == F("PND1 DUMP")) {
    if (!(dumpIso14443AIfPresent() || dumpIso15693IfPresent() || dumpFeliCaIfPresent())) {
      Serial.println(F("INFO no_card"));
    }
    return true;
  }
  if (line == F("PND1 SCAN")) {
    handleScanCommand();
    return true;
  }
  if (line.startsWith(F("PND1 BRUTE_BATCH"))) {
    handleMifareBruteBatchCommand(line);
    return true;
  }
  if (line.startsWith(F("PND1 BRUTE_SECTOR"))) {
    handleMifareBruteCommand(line, true);
    return true;
  }
  if (line.startsWith(F("PND1 BRUTE"))) {
    handleMifareBruteCommand(line, false);
    return true;
  }
  if (line.startsWith(F("PND1 WRITE_ISO15693"))) {
    handleIso15693WriteCommand(line);
    return true;
  }
  if (line.startsWith(F("PND1 WRITE"))) {
    handleMifareWriteCommand(line);
    return true;
  }
  if (line == F("PND1 MAGIC_PROBE")) {
    handleMagicProbeCommand();
    return true;
  }
  Serial.println(F("PND1 ERROR status=unknown_command"));
  return true;
}

MifareClassicDumpResult readMifareClassicWithDictionary(
    uint8_t *uid,
    uint8_t uidLength,
    uint8_t sak,
    uint8_t dump[MIFARE_CLASSIC_MAX_BLOCKS][MIFARE_CLASSIC_BLOCK_SIZE],
    uint8_t blockStatus[MIFARE_CLASSIC_MAX_BLOCKS]) {
  MifareClassicDumpResult result;
  result.blockCount = mifareClassicBlockCount(sak);
  result.sectorCount = mifareClassicSectorCount(sak);

  for (uint16_t block = 0; block < MIFARE_CLASSIC_MAX_BLOCKS; ++block) {
    blockStatus[block] = MIFARE_BLOCK_STATUS_NOT_READ;
    for (uint8_t i = 0; i < MIFARE_CLASSIC_BLOCK_SIZE; ++i) {
      dump[block][i] = 0;
    }
  }

  if (uidLength != 4) {
    Serial.println(F("INFO mfclassic_auth status=unsupported_uid_length"));
    return result;
  }

  Serial.print(F("INFO mfclassic_dump_start sectors="));
  Serial.print(result.sectorCount);
  Serial.print(F(" keys="));
  Serial.println(MIFARE_CLASSIC_KEY_COUNT);

  uint8_t activeSak = sak;
  for (uint8_t sector = 0; sector < result.sectorCount; ++sector) {
    uint16_t firstBlock = mifareClassicSectorFirstBlock(sector);
    uint8_t sectorBlocks = mifareClassicSectorBlockCount(sector);
    bool sectorAuthenticated = false;
    bool sectorLogged = false;

    for (uint8_t offset = 0; offset < sectorBlocks; ++offset) {
      uint16_t block = firstBlock + offset;
      if (block >= result.blockCount) {
        break;
      }

      uint8_t buffer[MIFARE_CLASSIC_BLOCK_SIZE] = {0};
      bool blockOk = false;
      bool blockAuthenticated = false;
      uint8_t authenticatedKeyType = 0;
      uint8_t authenticatedKeyIndex = 0;

      for (uint8_t attempt = 0; attempt < MIFARE_CLASSIC_DEFAULT_READ_RETRIES && !blockOk; ++attempt) {
        for (uint8_t keyTypeIndex = 0; keyTypeIndex < 2 && !blockOk; ++keyTypeIndex) {
          uint8_t keyType = keyTypeIndex == 0 ? MIFARE_KEY_A : MIFARE_KEY_B;
          for (uint8_t keyIndex = 0; keyIndex < MIFARE_CLASSIC_KEY_COUNT && !blockOk; ++keyIndex) {
            bool keyAuthenticated = false;
            blockOk = readMifareClassicBlockFresh(
                static_cast<uint8_t>(block),
                keyType,
                MIFARE_CLASSIC_KEYS[keyIndex],
                uid,
                uidLength,
                activeSak,
                buffer,
                keyAuthenticated);
            if (keyAuthenticated) {
              blockAuthenticated = true;
              sectorAuthenticated = true;
              authenticatedKeyType = keyType;
              authenticatedKeyIndex = keyIndex;
              if (!sectorLogged) {
                ++result.sectorsAuthenticated;
                Serial.print(F("INFO mfclassic_auth sector="));
                Serial.print(sector);
                Serial.print(F(" key_type="));
                Serial.print(authenticatedKeyType == MIFARE_KEY_A ? 'A' : 'B');
                Serial.print(F(" key_index="));
                Serial.print(authenticatedKeyIndex);
                Serial.print(F(" key="));
                printMifareKey(MIFARE_CLASSIC_KEYS[authenticatedKeyIndex]);
                Serial.println(F(" status=ok"));
                sectorLogged = true;
              }
            }
            delay(6);
          }
        }
      }

      if (blockOk) {
        for (uint8_t i = 0; i < MIFARE_CLASSIC_BLOCK_SIZE; ++i) {
          dump[block][i] = buffer[i];
        }
        blockStatus[block] = MIFARE_BLOCK_STATUS_READ;
        ++result.blocksRead;
      } else {
        if (blockAuthenticated) {
          blockStatus[block] = MIFARE_BLOCK_STATUS_NOT_READ;
        } else {
          blockStatus[block] = MIFARE_BLOCK_STATUS_KEY_MISSING;
        }
      }
    }

    if (!sectorAuthenticated) {
      Serial.print(F("INFO mfclassic_auth sector="));
      Serial.print(sector);
      Serial.print(F(" status=failed last_status="));
      printHexByte(lastMifareAuthStatus);
      Serial.println();
    }

    delay(4);
    reselectIso14443A(uid, uidLength, activeSak);
  }

  for (uint16_t block = 0; block < result.blockCount; ++block) {
    if (blockStatus[block] == MIFARE_BLOCK_STATUS_READ) {
      continue;
    }
    if (blockStatus[block] == MIFARE_BLOCK_STATUS_KEY_MISSING) {
      continue;
    }

    uint8_t buffer[MIFARE_CLASSIC_BLOCK_SIZE] = {0};
    bool recovered = false;
    bool blockAuthenticated = false;
    uint8_t recoveredKeyType = 0;
    uint8_t recoveredKeyIndex = 0;

    for (uint8_t attempt = 0; attempt < MIFARE_CLASSIC_DEFAULT_RECOVERY_RETRIES && !recovered; ++attempt) {
      for (uint8_t keyTypeIndex = 0; keyTypeIndex < 2 && !recovered; ++keyTypeIndex) {
        uint8_t keyType = keyTypeIndex == 0 ? MIFARE_KEY_A : MIFARE_KEY_B;
        for (uint8_t keyIndex = 0; keyIndex < MIFARE_CLASSIC_KEY_COUNT && !recovered; ++keyIndex) {
          bool keyAuthenticated = false;
          recovered = readMifareClassicBlockFresh(
              static_cast<uint8_t>(block),
              keyType,
              MIFARE_CLASSIC_KEYS[keyIndex],
              uid,
              uidLength,
              activeSak,
              buffer,
              keyAuthenticated);
          if (keyAuthenticated) {
            blockAuthenticated = true;
            recoveredKeyType = keyType;
            recoveredKeyIndex = keyIndex;
          }
          delay(6);
        }
      }
    }

    if (recovered) {
      for (uint8_t i = 0; i < MIFARE_CLASSIC_BLOCK_SIZE; ++i) {
        dump[block][i] = buffer[i];
      }
      blockStatus[block] = MIFARE_BLOCK_STATUS_READ;
      ++result.blocksRead;
      Serial.print(F("INFO mfclassic_recovered block="));
      Serial.print(block);
      Serial.print(F(" key_type="));
      Serial.print(recoveredKeyType == MIFARE_KEY_A ? 'A' : 'B');
      Serial.print(F(" key_index="));
      Serial.print(recoveredKeyIndex);
      Serial.print(F(" key="));
      printMifareKey(MIFARE_CLASSIC_KEYS[recoveredKeyIndex]);
      Serial.println();
    } else if (blockAuthenticated || blockStatus[block] == MIFARE_BLOCK_STATUS_NOT_READ) {
      blockStatus[block] = MIFARE_BLOCK_STATUS_NOT_READ;
      Serial.print(F("INFO mfclassic_read_failed block="));
      Serial.println(block);
    } else {
      blockStatus[block] = MIFARE_BLOCK_STATUS_KEY_MISSING;
    }
  }

  result.sectorsAuthenticated = 0;
  for (uint8_t sector = 0; sector < result.sectorCount; ++sector) {
    uint16_t firstBlock = mifareClassicSectorFirstBlock(sector);
    uint8_t sectorBlocks = mifareClassicSectorBlockCount(sector);
    for (uint8_t offset = 0; offset < sectorBlocks; ++offset) {
      uint16_t block = firstBlock + offset;
      if (block < result.blockCount && blockStatus[block] == MIFARE_BLOCK_STATUS_READ) {
        ++result.sectorsAuthenticated;
        break;
      }
    }
  }

  return result;
}

uint8_t iso14443AReadStep(uint8_t sak) {
  // Ultralight/NTAG READ returns four 4-byte pages at once. Other Type A tags
  // usually expose 16-byte blocks or require protocol-specific/authenticated IO.
  return (sak == 0x00) ? 4 : 1;
}

bool dumpIso15693IfPresent() {
  uint8_t uid[8] = {0};
  if (!setupRfSafe(0x0D, 0x8D, true, F("ISO15693"))) {
    return false;
  }

  ISO15693ErrorCode rc = getIso15693InventorySafe(uid);
  if (rc != ISO15693_EC_OK) {
    return false;
  }

  SystemInfoData info = readSystemInfo(uid);

  Serial.println(F("DUMP_BEGIN"));
  Serial.print(F("META type=ISO15693 protocol=ISO15693 uid="));
  printUidReversedCompact(uid, 8);
  Serial.print(F(" uid_length=8 rc="));
  Serial.print(static_cast<int>(info.rc));
  Serial.print(F(" block_size="));
  if (info.hasMemorySize) {
    Serial.print(info.blockSize);
  } else {
    Serial.print(F("-"));
  }
  Serial.print(F(" num_blocks="));
  if (info.hasMemorySize) {
    Serial.print(info.numBlocks);
  } else {
    Serial.print(F("-"));
  }
  Serial.print(F(" dsfid="));
  if (info.hasDsfid) {
    printHexByte(info.dsfid);
  } else {
    Serial.print(F("-"));
  }
  Serial.print(F(" afi="));
  if (info.hasAfi) {
    printHexByte(info.afi);
  } else {
    Serial.print(F("-"));
  }
  Serial.print(F(" ic_reference="));
  if (info.hasIcReference) {
    printHexByte(info.icReference);
  } else {
    Serial.print(F("-"));
  }
  Serial.println();

  if (info.rc == ISO15693_EC_OK && info.hasMemorySize && info.blockSize > 0 && info.numBlocks > 0) {
    if (!readCompactHexDump(uid, info.blockSize, info.numBlocks)) {
      Serial.println(F("ERROR dump_incomplete protocol=ISO15693"));
    }
  } else {
    Serial.print(F("ERROR system_info rc="));
    Serial.print(static_cast<int>(info.rc));
    Serial.println();
  }

  Serial.println(F("DUMP_END"));
  return true;
}

bool dumpIso14443AIfPresent() {
  if (!setupRfSafe(0x00, 0x80, false, F("ISO14443A"))) {
    return false;
  }

  uint8_t response[10] = {0};
  uint8_t uidLength = activateTypeASafe(response, 1);
  if (uidLength == 0) {
    return false;
  }

  uint8_t uid[10] = {0};
  for (uint8_t i = 0; i < uidLength && i < sizeof(uid); ++i) {
    uid[i] = response[3 + i];
  }

  uint8_t atqa0 = response[0];
  uint8_t atqa1 = response[1];
  uint8_t sak = response[2];
  uint8_t readStep = iso14443AReadStep(sak);
  uint8_t blockData[MAX_ISO14443A_READ_COMMANDS][16];
  uint8_t readAddresses[MAX_ISO14443A_READ_COMMANDS] = {0};
  uint8_t readCount = 0;
  const bool authRequired = isMifareClassicSak(sak);
  static uint8_t classicDump[MIFARE_CLASSIC_MAX_BLOCKS][MIFARE_CLASSIC_BLOCK_SIZE];
  static uint8_t classicBlockStatus[MIFARE_CLASSIC_MAX_BLOCKS];
  MifareClassicDumpResult classicResult;

  Serial.print(F("TAG_DETECTED type=ISO14443A protocol=ISO14443A uid="));
  printHexCompact(uid, uidLength);
  Serial.print(F(" uid_length="));
  Serial.print(uidLength);
  Serial.print(F(" atqa="));
  printHexByte(atqa0);
  printHexByte(atqa1);
  Serial.print(F(" sak="));
  printHexByte(sak);
  Serial.print(F(" family="));
  Serial.println(classifyIso14443A(sak));

  if (authRequired) {
    classicResult = readMifareClassicWithDictionary(uid, uidLength, sak, classicDump, classicBlockStatus);
  } else {
    for (uint16_t address = 0; readCount < MAX_ISO14443A_READ_COMMANDS && address < 255; address += readStep) {
      uint8_t buffer[16] = {0};
      if (!nfc14443.mifareBlockRead(static_cast<uint8_t>(address), buffer)) {
        break;
      }

      readAddresses[readCount] = static_cast<uint8_t>(address);
      for (uint8_t i = 0; i < 16; ++i) {
        blockData[readCount][i] = buffer[i];
      }
      ++readCount;
    }
  }

  mifareHaltSafe();

  Serial.println(F("DUMP_BEGIN"));
  Serial.print(F("META type=ISO14443A protocol=ISO14443A uid="));
  printHexCompact(uid, uidLength);
  Serial.print(F(" uid_length="));
  Serial.print(uidLength);
  Serial.print(F(" rc=0 block_size=16 num_blocks="));
  if (authRequired) {
    Serial.print(classicResult.blockCount);
  } else if (readCount > 0) {
    Serial.print(readCount);
  } else {
    Serial.print(F("-"));
  }
  Serial.print(F(" dsfid=- afi=- ic_reference=- atqa="));
  printHexByte(atqa0);
  printHexByte(atqa1);
  Serial.print(F(" sak="));
  printHexByte(sak);
  Serial.print(F(" family="));
  Serial.print(classifyIso14443A(sak));
  Serial.print(F(" read_step="));
  Serial.print(readStep);
  Serial.print(F(" memory_read="));
  if (authRequired && uidLength != 4) {
    Serial.print(F("auth_uid_unsupported"));
  } else if (authRequired && classicResult.blocksRead == classicResult.blockCount && classicResult.blockCount > 0) {
    Serial.print(F("ok"));
  } else if (authRequired && classicResult.blocksRead > 0) {
    Serial.print(F("partial"));
  } else if (authRequired) {
    Serial.print(F("auth_failed"));
  } else if (readCount > 0) {
    Serial.print(F("ok"));
  } else {
    Serial.print(F("unsupported_or_no_open_blocks"));
  }
  if (authRequired) {
    Serial.print(F(" blocks_read="));
    Serial.print(classicResult.blocksRead);
    Serial.print(F(" sectors="));
    Serial.print(classicResult.sectorCount);
    Serial.print(F(" sectors_authenticated="));
    Serial.print(classicResult.sectorsAuthenticated);
    Serial.print(F(" key_dictionary_size="));
    Serial.print(MIFARE_CLASSIC_KEY_COUNT);
  }
  Serial.println();

  if (authRequired && classicResult.blocksRead > 0) {
    Serial.println(F("COMPACT_BEGIN"));
    uint8_t emptyBlock[MIFARE_CLASSIC_BLOCK_SIZE] = {0};
    for (uint16_t block = 0; block < classicResult.blockCount; ++block) {
      if (classicBlockStatus[block] == MIFARE_BLOCK_STATUS_KEY_MISSING) {
        Serial.print(F("INFO mfclassic_block_key_missing block="));
        Serial.println(block);
        printHexLine(emptyBlock, MIFARE_CLASSIC_BLOCK_SIZE);
      } else if (classicBlockStatus[block] == MIFARE_BLOCK_STATUS_NOT_READ) {
        Serial.print(F("INFO mfclassic_block_missing block="));
        Serial.println(block);
        printHexLine(emptyBlock, MIFARE_CLASSIC_BLOCK_SIZE);
      } else {
        Serial.print(F("INFO mfclassic_block block="));
        Serial.println(block);
        printHexLine(classicDump[block], MIFARE_CLASSIC_BLOCK_SIZE);
      }
    }
    Serial.println(F("COMPACT_END"));
  } else if (readCount > 0) {
    Serial.println(F("COMPACT_BEGIN"));
    for (uint8_t i = 0; i < readCount; ++i) {
      Serial.print(F("INFO typea_read address="));
      Serial.println(readAddresses[i]);
      printHexLine(blockData[i], 16);
    }
    Serial.println(F("COMPACT_END"));
  }

  Serial.println(F("DUMP_END"));
  return true;
}

bool dumpFeliCaIfPresent() {
  if (!setupRfSafe(0x09, 0x89, false, F("FELICA"))) {
    return false;
  }

  uint8_t uid[20] = {0};
  uint8_t uidLength = nfcFeliCa.readCardSerial(uid);
  if (uidLength == 0) {
    return false;
  }

  Serial.println(F("DUMP_BEGIN"));
  Serial.print(F("META type=FELICA protocol=FELICA uid="));
  printHexCompact(uid, uidLength);
  Serial.print(F(" uid_length="));
  Serial.print(uidLength);
  Serial.println(F(" rc=0 block_size=- num_blocks=- dsfid=- afi=- ic_reference=- memory_read=unsupported_by_library"));
  Serial.println(F("DUMP_END"));
  return true;
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.setTimeout(120);
  delay(1000);

  SPI.begin(PN5180_SCK_PIN, PN5180_MISO_PIN, PN5180_MOSI_PIN, PN5180_NSS_PIN);
  nfc15693.begin();
  nfc14443.begin();
  nfcFeliCa.begin();

  // The library may re-init SPI internally; restore explicit routing for ESP32-S3.
  SPI.end();
  SPI.begin(PN5180_SCK_PIN, PN5180_MISO_PIN, PN5180_MOSI_PIN, PN5180_NSS_PIN);

  Serial.println(F("READER_READY protocols=ISO15693,ISO14443A,FELICA device=XIAO-ESP32-S3"));
}

void loop() {
  processSerialCommand();
  delay(5);
}
