# PN5180 Dumper

PN5180 Dumper captures ISO15693 RFID tag memory dumps with a PN5180 reader and a XIAO ESP32-S3 board.

The Arduino sketch reads the tag through the PN5180 module and prints a structured dump to the serial port. The Python utility listens to that serial output, detects a complete dump, and saves metadata plus binary and hex dump files.

## Hardware

- Seeed Studio XIAO ESP32-S3
- PN5180 RFID/NFC module
- ISO15693-compatible tag

## Files

- `DumpInfo.ino` - Arduino sketch for PN5180 ISO15693 reading.
- `capture_dump.py` - Serial capture utility that saves complete dumps.
- `run_capture_once.bat` - Windows helper that captures one complete dump and exits.
- `requirements.txt` - Python dependencies.

## Wiring

The sketch currently uses this XIAO ESP32-S3 to PN5180 pin mapping:

| PN5180 signal | XIAO ESP32-S3 pin |
| --- | --- |
| SCK | 7 |
| MISO | 8 |
| MOSI | 9 |
| NSS | 2 |
| BUSY | 3 |
| RST | 4 |

## Usage

Install the Python dependency:

```powershell
pip install -r requirements.txt
```

Flash `DumpInfo.ino` to the board, connect the board over USB, then run:

```powershell
.\run_capture_once.bat
```

Or run the capture utility directly:

```powershell
python capture_dump.py --auto-port --once
```

If auto-detection cannot choose the port, pass it explicitly:

```powershell
python capture_dump.py --port COM6 --once
```

## Output

Each successful capture is saved under `captures/<timestamp>_<uid>/`:

- `metadata.json` - tag metadata and SHA-256 of the binary dump.
- `dump.hex` - formatted hex dump.
- `dump.bin` - raw binary dump.
- `raw_serial.log` - full serial log from the board.

`captures/` is ignored by git because real RFID dumps can contain private tag data.

