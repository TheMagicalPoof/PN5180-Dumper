# Architecture

PN5180 Dumper is moving from a single-purpose capture sketch to a universal PN5180 tool with three layers:

1. Firmware command engine on ESP32-S3.
2. Host protocol/client library over serial.
3. User interfaces: Windows Qt GUI and cross-platform console CLI.

## Goals

- Scan and identify all tag families supported by PN5180 and the firmware modules.
- Read, dump, and write where the tag family and access state allow it.
- Keep potentially dangerous operations explicit: write, lock, password/auth, privacy, format.
- Let Qt and CLI share the same host library instead of duplicating serial logic.
- Preserve raw logs and binary dumps for reproducibility.

## Repository Layout

- `firmware/pn5180_dumper/` - ESP32-S3 Arduino firmware.
- `host/python/pn5180_dumper/` - Python host library and CLI entrypoint.
- `docs/` - protocol, architecture, and operation notes.
- `scripts/` - convenience scripts.
- `captures/` - local capture output, ignored by git.

## Firmware Shape

The firmware should evolve into modules with a shared interface:

```text
TagDriver
  name()
  setup_rf()
  scan()
  identify()
  read(plan)
  write(plan, data)
  dump(plan)
  auth(credentials)
```

Planned drivers:

- `iso15693` - inventory, system info, block read/write, full dump, DSFID/AFI metadata.
- `iso14443a` - Type A activation, UID/ATQA/SAK, NTAG/Ultralight reads and writes, MIFARE Classic only where auth support exists.
- `felica` - polling/IDm first, service/block reads later.
- `iclass` - separate compatibility work is needed because the current Arduino library has a header enum conflict with ISO15693.
- `raw` - expert mode for manually sending low-level PN5180/tag commands.

## Host Shape

The Python package is the shared host layer:

- port discovery,
- serial transport,
- command framing,
- response parsing,
- dump file storage,
- safety prompts for writes.

The Windows Qt application can call this library directly or wrap the same protocol concepts in C++ later. The Linux console UI should stay usable over SSH/headless serial sessions.

## Compatibility

The current firmware still emits legacy streaming records:

```text
DUMP_BEGIN
META ...
COMPACT_BEGIN
...
COMPACT_END
DUMP_END
```

The host keeps parsing this format while the new command protocol is introduced.

