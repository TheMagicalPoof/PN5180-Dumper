PN5180 Dumper
=============

PN5180 Dumper is being shaped into a universal PN5180 RFID/NFC tool for
scanning, identifying, reading, dumping, and eventually writing supported tags.

Supported tags
--------------
- ISO15693: full memory dump when block size and block count are available.
- ISO14443A: UID detection plus best-effort openly readable 16-byte reads.
- FeliCa: IDm detection. Memory dump is not implemented in the bundled library.

iClass is present in the PN5180 library, but its header currently conflicts with
ISO15693 when both are compiled into one sketch. It is intentionally disabled in
the unified scanner for now.

Files
-----

- firmware/pn5180_dumper/pn5180_dumper.ino
  ESP32-S3 Arduino firmware.

- host/python/pn5180_dumper/
  Python host package and CLI.

- docs/
  Architecture, roadmap, and serial protocol notes.

- capture_dump.py
  Compatibility wrapper for the legacy streaming capture utility.

- run_capture_once.bat
  Compatibility wrapper that starts one capture in auto-port mode and exits
  after the first full dump.


How to use
----------
1. Connect the board to USB.
2. Run:

   run_capture_once.bat

   or manually:

   python capture_dump.py --auto-port --once

   or:

   set PYTHONPATH=host\python
   python -m pn5180_dumper.cli ports
   python -m pn5180_dumper.cli capture --auto-port --once


Result files
------------
Each captured tag is saved into its own folder inside:

  captures\

The folder contains:

- metadata.json
  Tag metadata and SHA-256 when a binary dump was captured.

- dump.hex
  Text hex dump, when readable memory data was captured.

- dump.bin
  Raw binary dump, when readable memory data was captured. Open this file in a
  hex editor if you want to see the real bytes.

- raw_serial.log
  Full raw serial output from the Programmer.


Notes
-----
- Default serial speed in the utility is 460800.
