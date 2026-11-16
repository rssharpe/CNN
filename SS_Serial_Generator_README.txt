SS Serial Generator 1.0.0

Purpose
-------
Standalone test utility that sends SCC-format serial records. It does not
control an SCC counter.

Use
---
1. Install SS_Serial_Generator_Setup.exe and launch SS Serial Generator.
2. Connect its COM port to one end of a virtual COM pair or physical RS-232
   null-modem link. Connect CCN to the other end; the two programs must use
   different COM endpoints.
3. Select the generator COM port and configure the address, units,
   calibration, direction, speed, and send interval.
4. Click Start Sending. The serial format is 9600 baud, 8-N-1. Click Stop
   before changing ports or closing the application.

Build from source
-----------------
Requires Python, PyInstaller, pyserial, and Inno Setup 6. From this folder,
run:

    .\build_ss_serial_generator.ps1

The script creates dist\SS_Serial_Generator.exe and
dist\installer\SS_Serial_Generator_Setup.exe. The installer is per-user and
does not require administrator privileges. The EXE and installer are
unsigned; Windows SmartScreen may show a warning.
