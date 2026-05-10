# Roadmap

## Done Enough For Alpha

- Repository split into firmware, host package, docs, scripts, and tests.
- ESP32-S3 PN5180 firmware builds with Arduino CLI.
- Qt5 GUI starts on Windows and remembers serial port.
- Command-driven firmware loop.
- ISO15693 dump path.
- ISO14443A detection.
- MIFARE Classic 1K default-key dump tested with `FFFFFFFFFFFF`.
- MIFARE Classic safe data-block write path.
- Guarded block 0 write flow for UID-changeable blanks.
- Gen1A magic probe.
- Capture folder naming by timestamp + hash.

## Before `v0.3.0-alpha`

- Keep README/protocol docs aligned with current code.
- Add parser tests for `OK`, `NN`, and `MS` block status.
- Add smoke tests for capture folder naming and metadata.
- Add a visible warning in Qt that 4K/S70 is experimental until tested.
- Add release notes with known blank-tag types: Gen1A, CUID, FUID, UFUID.

## Before `v0.4.0`

- Validate MIFARE Classic 4K/S70 read and write on real hardware.
- Add a transport/client layer shared by Qt and CLI.
- Implement CLI commands for `dump`, `write`, and `magic-probe`.
- Add write dry-run summary with exact block list.
- Improve block 0 handling per blank type.
- Add optional trailer write mode behind a separate danger gate.

## Before `v1.0`

- Stable command protocol, likely `PND2`.
- Versioned firmware capability handshake.
- Better cancellation for long operations.
- Installer/portable Windows bundle.
- Cross-platform console UI.
- Expanded tag support: NTAG/Ultralight pages, FeliCa services, more ISO15693 write operations.
- Broader automated tests for parser, protocol, write queue, and UI state.

## Known Open Questions

- Which exact magic blank families should be supported first: Gen1A, CUID, FUID, UFUID?
- Can PN5180 reliably perform all needed magic UID backdoors, or do some blanks require lower-level timing work?
- Should iClass live in the unified firmware or a separate sketch because of library conflicts?
