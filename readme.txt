PN5180 Dumper
=============

PN5180 Dumper scans RFID/NFC tags with a PN5180 reader and saves detected
records from the Arduino serial output.

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

- capture_dump.py
  Console utility that listens to the serial port, auto-detects complete tag
  records in the Arduino output and saves them to files.

- run_capture_once.bat
  Starts one capture in auto-port mode and exits after the first full dump.


How to use
----------
1. Connect the board to USB.
2. Run:

   run_capture_once.bat

   or manually:

   python capture_dump.py --auto-port --once


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
