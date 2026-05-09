RFID dump capture
=================

Files
-----

- capture_dump.py
  Console utility that listens to the serial port, auto-detects a dump in the
  Arduino output and saves it to files.

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
  Tag metadata: UID, block size, number of blocks, DSFID, AFI, IC reference.

- dump.hex
  Text hex dump.

- dump.bin
  Raw binary dump. Open this file in a hex editor if you want to see the real bytes.

- raw_serial.log
  Full raw serial output from the Programmer.


Notes
-----
- Default serial speed in the utility is 460800.
