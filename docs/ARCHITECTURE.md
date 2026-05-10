# Architecture

PN5180 Dumper currently has three practical layers:

1. ESP32-S3 firmware for PN5180 RF operations.
2. Python host package for serial capture/parsing/storage.
3. PyQt5 Windows GUI for bench use.

The repo is still shaped for a future universal tool, but the implemented alpha path is Qt + `PND1`.

## Firmware

Firmware file:

```text
firmware/pn5180_dumper/pn5180_dumper.ino
```

Implemented responsibilities:

- PN5180 setup for ISO15693, ISO14443A, and FeliCa polling.
- Command-driven loop, no cyclic automatic dump.
- `PND1 DUMP` one-shot tag detection/read.
- MIFARE Classic default-key read with fresh activation and recovery retries.
- MIFARE Classic host-driven brute attempts.
- MIFARE Classic safe write for data blocks.
- Guarded block 0 write attempts for UID-changeable blanks.
- Gen1A magic probe.

MIFARE Classic layout support:

- Mini: 20 blocks.
- 1K/S50: 64 blocks.
- 4K/S70: 256 blocks.

4K layout is represented in code, but still needs hardware validation.

## Host Package

Package path:

```text
host/python/pn5180_dumper/
```

Key modules:

- `capture.py`: serial record parser and capture saving.
- `qt_app.py`: PyQt5 GUI and current main workflow.
- `keys.py`: default/proxmark dictionary loading helpers.
- `cli.py`: port listing and legacy capture CLI.

## Qt GUI

The Qt app is currently the main interface. It provides:

- serial port selection and persistence;
- reader/tag online indicators;
- raw dump hex table;
- dump export path;
- write import path and write buffer viewer;
- safe write with confirmation;
- optional guarded UID block 0 write;
- magic UID probe;
- diagnostic serial log.

The GUI writes MIFARE Classic blocks one-by-one and waits for `PND1 WRITE_RESULT` before sending the next block.

## Capture Storage

Captures are saved under:

```text
captures/<UTC timestamp>_<sha256-prefix>/
```

Each folder may contain:

- `metadata.json`
- `dump.hex`
- `dump.bin`
- `block_status.json`
- `raw_serial.log`

## Future Shape

The target architecture still is:

```text
Firmware command engine
  -> stable protocol
  -> shared host client
  -> Qt GUI and console UI
```

The next architectural step is to extract serial command transport from `qt_app.py` into a reusable host client so CLI and Qt use the same implementation.
