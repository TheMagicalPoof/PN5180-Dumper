# PN5180 Dumper

PN5180 Dumper is a PN5180-based RFID/NFC tool for scanning, identifying, reading, dumping, and eventually writing supported tags with an ESP32-S3 reader and host-side UI tools.

The current firmware still supports streaming captures over serial. The repository is now structured for a larger universal tool: ESP firmware command modules, a shared Python host library/CLI, and future Qt UI.

## Supported Tags

- `ISO15693` - full memory dump when System Info exposes block size and block count.
- `ISO14443A` - UID detection plus best-effort reading of openly readable MIFARE/NTAG-style 16-byte reads.
- `FELICA` - IDm detection. Memory dump is not implemented because the bundled PN5180 library exposes polling/serial detection only.

Known limitation: `iClass` exists in the bundled PN5180 library, but it currently conflicts with the ISO15693 header when both are included in the same sketch. It will need a separate compatibility wrapper or a separate sketch before it can be enabled in the unified scanner.

## Hardware

- Seeed Studio XIAO ESP32-S3
- PN5180 RFID/NFC module
- ISO15693, ISO14443A, or FeliCa-compatible tag

## Files

- `firmware/pn5180_dumper/pn5180_dumper.ino` - ESP32-S3 Arduino firmware.
- `host/python/pn5180_dumper/` - Python host package and CLI.
- `docs/` - architecture, roadmap, and serial protocol notes.
- `scripts/run_capture_once.bat` - Windows helper that captures one complete dump and exits.
- `capture_dump.py` - compatibility wrapper for the legacy capture command.
- `run_capture_once.bat` - compatibility wrapper for the legacy Windows helper.
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

Flash `firmware/pn5180_dumper/pn5180_dumper.ino` to the board, connect the board over USB, then run:

```powershell
.\run_capture_once.bat
```

Or run the capture utility directly:

```powershell
python capture_dump.py --auto-port --once
```

The new host CLI can list ports and run the same legacy capture path:

```powershell
$env:PYTHONPATH = "host/python"
python -m pn5180_dumper.cli ports
python -m pn5180_dumper.cli capture --auto-port --once
```

If auto-detection cannot choose the port, pass it explicitly:

```powershell
python capture_dump.py --port COM6 --once
```

## Output

Each successful capture is saved under `captures/<timestamp>_<uid>/`:

- `metadata.json` - tag metadata and SHA-256 when a binary dump was captured.
- `dump.hex` - formatted hex dump, when readable memory data was captured.
- `dump.bin` - raw binary dump, when readable memory data was captured.
- `raw_serial.log` - full serial log from the board.

`captures/` is ignored by git because real RFID dumps can contain private tag data.

## Development Direction

See:

- `docs/ARCHITECTURE.md` - target firmware/host/UI structure.
- `docs/SERIAL_PROTOCOL.md` - legacy stream format and planned command protocol V2.
- `docs/ROADMAP.md` - phased implementation plan.
