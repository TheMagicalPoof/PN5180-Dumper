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
static constexpr uint8_t MAX_ISO14443A_READ_COMMANDS = 64;

PN5180ISO15693 nfc15693(PN5180_NSS_PIN, PN5180_BUSY_PIN, PN5180_RST_PIN);
PN5180ISO14443 nfc14443(PN5180_NSS_PIN, PN5180_BUSY_PIN, PN5180_RST_PIN);
PN5180FeliCa nfcFeliCa(PN5180_NSS_PIN, PN5180_BUSY_PIN, PN5180_RST_PIN);

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

const __FlashStringHelper *classifyIso14443A(uint8_t sak) {
  switch (sak) {
    case 0x00:
      return F("MIFARE_ULTRALIGHT_OR_NTAG");
    case 0x08:
      return F("MIFARE_CLASSIC_1K");
    case 0x09:
      return F("MIFARE_MINI");
    case 0x18:
      return F("MIFARE_CLASSIC_4K");
    case 0x20:
      return F("ISO14443_4_COMPATIBLE");
    default:
      return F("UNKNOWN_TYPE_A");
  }
}

uint8_t iso14443AReadStep(uint8_t sak) {
  // Ultralight/NTAG READ returns four 4-byte pages at once. Other Type A tags
  // usually expose 16-byte blocks or require protocol-specific/authenticated IO.
  return (sak == 0x00) ? 4 : 1;
}

bool dumpIso15693IfPresent() {
  uint8_t uid[8] = {0};
  if (!setupRf(nfc15693, F("ISO15693"))) {
    return false;
  }

  ISO15693ErrorCode rc = nfc15693.getInventory(uid);
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
  if (!setupRf(nfc14443, F("ISO14443A"))) {
    return false;
  }

  uint8_t response[10] = {0};
  uint8_t uidLength = nfc14443.activateTypeA(response, 1);
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

  for (uint16_t address = 0; readCount < MAX_ISO14443A_READ_COMMANDS && address < 255; address += readStep) {
    uint8_t buffer[16] = {0};
    if (!nfc14443.mifareBlockRead(static_cast<uint8_t>(address), buffer)) {
      Serial.print(F("INFO typea_read_stop address="));
      Serial.println(address);
      break;
    }

    readAddresses[readCount] = static_cast<uint8_t>(address);
    for (uint8_t i = 0; i < 16; ++i) {
      blockData[readCount][i] = buffer[i];
    }
    ++readCount;
  }

  nfc14443.mifareHalt();

  Serial.println(F("DUMP_BEGIN"));
  Serial.print(F("META type=ISO14443A protocol=ISO14443A uid="));
  printHexCompact(uid, uidLength);
  Serial.print(F(" uid_length="));
  Serial.print(uidLength);
  Serial.print(F(" rc=0 block_size=16 num_blocks="));
  if (readCount > 0) {
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
  Serial.println();

  if (readCount > 0) {
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
  if (!setupRf(nfcFeliCa, F("FELICA"))) {
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
  if (dumpIso15693IfPresent() || dumpIso14443AIfPresent() || dumpFeliCaIfPresent()) {
    delay(3000);
    return;
  }

  Serial.println(F("INFO no_card"));
  delay(500);
}
