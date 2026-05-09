# Roadmap

## Phase 1 - Structure

- Keep the current streaming firmware working.
- Split repository into firmware, host, docs, and scripts.
- Add host CLI entrypoint and port listing.
- Document command protocol V2.

## Phase 2 - Firmware Command Mode

- Add serial command parser on ESP32-S3.
- Implement `hello`, `scan`, and `identify`.
- Return capability metadata for each driver.
- Keep legacy streaming capture behind a mode/config flag.

## Phase 3 - Read/Dump Operations

- ISO15693 full read/write by block.
- NTAG/Ultralight read/write by page.
- FeliCa service discovery/read where possible.
- iClass feasibility pass and library conflict fix.
- Unified dump storage format.

## Phase 4 - Safety And Write Support

- Add dry-run and explicit write confirmation.
- Add write verification reads.
- Add protected/authenticated operation model.
- Add test fixtures from safe synthetic logs.

## Phase 5 - User Interfaces

- Cross-platform console CLI for Linux/Windows/macOS.
- Small Qt GUI for Windows with port selector, scan table, tag details, dump viewer, and write panel.
- Shared host library for both UI paths.

Initial PyQt5 GUI exists and supports the current streaming capture mode. It should switch from passive serial capture to active `scan`, `identify`, `read`, `write`, and `dump` commands after protocol V2 is implemented in firmware.
