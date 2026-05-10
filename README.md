# PN5180 Dumper

PN5180 Dumper is a PN5180 + ESP32-S3 RFID/NFC tool with a Python/Qt host app for reading, viewing, exporting, and writing supported tags.

Current status: `v0.3-alpha` quality. The tool is useful on the bench, but the protocol and UI are still evolving.

## Current Capabilities

- `ISO15693`: inventory and full memory dump when System Info exposes block size and block count.
- `ISO14443A`: UID/ATQA/SAK detection.
- `MIFARE Classic 1K`: tested read/dump with default key `FFFFFFFFFFFF`.
- `MIFARE Classic 4K/S70`: firmware has block/sector layout support, but real 4K write/read coverage is still experimental until tested with hardware.
- `MIFARE Classic write`: safe data-block write flow from Qt with optional verify.
- `Magic UID diagnostics`: Gen1A magic backdoor probe and guarded block 0 write attempts.
- `FeliCa`: IDm detection only; memory dump is not implemented with the bundled PN5180 library.

## Important Limits

- Safe write skips sector trailer blocks because they contain keys and access bits.
- UID/block 0 writing only works on UID-changeable blanks such as `Gen1A`, `CUID`, `FUID`, or `UFUID`; normal MIFARE Classic cards will not rewrite block 0.
- `Probe magic UID` only detects Gen1A-style backdoor support.
- iClass is not enabled because the bundled PN5180 library conflicts with ISO15693 headers when included in the same sketch.
- CLI commands beyond `ports` and `capture` are placeholders; the Qt app is currently the main UI.

## Hardware

- Seeed Studio XIAO ESP32-S3
- PN5180 RFID/NFC module
- ISO15693, ISO14443A/MIFARE Classic, or FeliCa-compatible tag

## Wiring

| PN5180 signal | XIAO ESP32-S3 pin |
| --- | --- |
| SCK | 7 |
| MISO | 8 |
| MOSI | 9 |
| NSS | 2 |
| BUSY | 3 |
| RST | 4 |

## Install

```powershell
pip install -r requirements.txt -r requirements-qt.txt
```

Flash `firmware/pn5180_dumper/pn5180_dumper.ino` to the XIAO ESP32-S3.

## Run Qt UI

```powershell
.\scripts\run_qt_app.bat
```

The Qt app:

- remembers the last selected serial port;
- uses baud rate `460800`;
- saves captures to `captures/`;
- displays raw dump data as a hex table;
- exports `dump.bin`;
- writes loaded dumps back to MIFARE Classic-compatible blanks.

## CLI

The CLI can list ports and capture protocol records:

```powershell
$env:PYTHONPATH = "host/python"
python -m pn5180_dumper.cli ports
python -m pn5180_dumper.cli capture --auto-port --once
```

Reserved commands such as `scan`, `read`, `write`, and `dump` are not wired into the CLI yet.

## Output

Each successful capture is saved under:

```text
captures/<UTC timestamp>_<sha256-prefix>/
```

Files:

- `metadata.json`: tag metadata, dump size, and SHA-256.
- `dump.hex`: formatted hex dump.
- `dump.bin`: raw binary dump.
- `block_status.json`: per-block status from the parser.
- `raw_serial.log`: full serial/protocol log.

`captures/` is ignored by git because real RFID dumps can contain private data.

## Buying Blank Tags

For UID cloning, search for explicit wording:

- `MIFARE Classic 1K Gen1A UID changeable`
- `MIFARE Classic 4K S70 UID changeable`
- `Magic UID`
- `CUID`
- `FUID`
- `UFUID`
- `Block 0 writable`

Avoid listings that only say `13.56MHz`, `S50`, `S70`, or `MIFARE Classic` without `UID changeable` or `magic`.

## Project Layout

- `firmware/pn5180_dumper/pn5180_dumper.ino`: ESP32-S3 Arduino firmware.
- `host/python/pn5180_dumper/`: Python host package, capture parser, CLI, and Qt UI.
- `docs/`: architecture, roadmap, and serial protocol notes.
- `scripts/run_qt_app.bat`: Windows Qt launcher.
- `scripts/run_capture_once.bat`: legacy one-shot capture helper.

## Development Notes

See:

- `docs/ARCHITECTURE.md`
- `docs/SERIAL_PROTOCOL.md`
- `docs/ROADMAP.md`
