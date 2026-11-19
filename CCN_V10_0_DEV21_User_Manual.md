# CCN DEV21 User Manual - Tension Integration

**Version:** 10.0 DEV21 - Tension Integration  
**Status:** Development and testing build

CCN reads cable-counter records from serial ports, playback files, or its
simulator. It can also read tension from an ATO load-cell amplifier over
Modbus RTU/RS-485. Cable and tension have separate inputs and displays.
Cable readings can be streamed to view-only client windows over TCP; tension
currently remains local to the connected CCN window.

DEV19 remains the frozen demo version. DEV21 is the working revision with
multi-COM, network, and tension features. DEV20 remains available unchanged.
When run from the same folder, DEV20 and DEV21 share `ccn_config.json` and raw
recordings; their processed CSV logs use separate revision-specific names.

## 1. Start CCN

From a VS Code terminal:

```powershell
cd C:\CNN
python .\CCN_V10_0_DEV21.py
```

If Windows does not recognize `python`, try:

```powershell
py .\CCN_V10_0_DEV21.py
```

Run from `C:\CNN` so relative configuration, log, and playback paths resolve
as expected. In this manual, the main window means the running CCN window.

## 2. Main window at a glance

- **Live COM Sources:** up to three independent serial ports. Each row has its
  own COM selector, Connect/Disconnect buttons, and status.
- **Playback Source:** shows the selected playback file and the loaded playback
  sources. Add and start playback from the **Playback** menu.
- **Tension - ATO Modbus RTU:** a separate RS-485 COM input and tension
  readout. It does not consume one of the three SCC COM rows.
- **Counter cards:** one card per source and SCC address. A port can provide
  more than one address.
- **Enable Logging:** controls CSV logging. Raw serial text recordings are
  saved separately.
- **View > Show Live COM Sources:** hides or shows the COM selectors,
  connection controls, and live status panel. It starts shown; hiding it does
  not disconnect active ports.
- **View > Show Playback Source:** hides or shows the playback filename and
  loaded-file details. It starts shown; hiding it does not stop playback.
- **View > Show Log Terminal:** shows or hides the event log panel. It starts
  hidden; this is separate from **Enable Logging**.
- **View > Show Tension Panel:** hides or shows the entire tension panel,
  including its COM-port controls. Hiding it does not disconnect the amplifier
  or stop tension readings.
- **Network status:** shows whether this window is local, hosting a server, or
  connected as a client.

The **Connection**, **Playback**, **Network**, **View**, and **Help** menus
contain less-frequent actions.

## 3. Connect live COM ports

1. Connect the serial adapter and confirm its COM number in Windows Device
   Manager.
2. In CCN, use **Connection > Refresh Ports**.
3. Choose a COM number in one of the Live COM Sources rows and click
   **Connect**.
4. Repeat in another row for each additional SCC/serial source, up to three.

DEV21's SCC inputs use **9600 baud, 8 data bits, no parity, 1 stop bit (8-N-1)**. The serial
reader is non-blocking and keeps a separate line buffer per COM port.

Only one program can normally open a COM port at a time. Close any serial
terminal or other program using that port before connecting CCN. If the port
does not appear, use **Refresh Ports** after checking the adapter driver.

### Connect the ATO tension amplifier

The ATO input uses its own USB-to-RS-485 adapter and COM port. Select that port
in the **Tension - ATO Modbus RTU** panel and use **Modbus Settings...** to set
the amplifier's slave ID, baud rate, parity, displayed unit, and scale factor.
The first-run scale is **1 display unit per register count**, with units shown
as **count**. Confirm the amplifier's communication mode, serial format,
register interpretation, and engineering scale before relying on live values;
the app cannot infer these from the COM port.

The reader polls holding registers starting at address 0 for two registers,
interpreted as a signed 32-bit net-weight value. The initial serial settings
are 9600 baud, 8 data bits, no parity, and one stop bit; these are configurable
in the panel. Use **Refresh Ports** to refresh both COM selectors. The tension
connection cannot share a COM port with an SCC input.

**ZERO TENSION DISPLAY** applies a software offset only; it sends no tare or
write command to the amplifier. Use **RESET TENSION ZERO** to clear that
software offset and return the display to the scaled amplifier reading. These
controls affect tension only; cable-counter zeroing and offsets are unchanged.
**Set Label** names the tension panel. **Peak Tension** shows the highest
zero-adjusted tension received since the last peak reset; **RESET PEAK**
starts a new peak at the current reading if it is fresh, otherwise waits for
the next reading. Zeroing or resetting the tension zero also starts a new peak.
The peak resets when starting a new live connection or simulation and is not
saved across application restarts.

Use **Alarm Settings...** to enable separate high-warning and high-critical
thresholds and choose a color for each. Alarms trigger when the displayed
tension goes **above** the threshold; if both are enabled, the critical
threshold must be higher. Critical tension uses the existing **View >
Audible Critical Alarm** setting and selected sound. When readings become
stale or lost, the alarm clears and the watchdog status takes priority; the
last peak remains visible. Changing units or scale clears the peak and zero
and disables both tension alarms until reviewed. A previously saved high
limit becomes the warning threshold.

These are application alarms, not a safety-rated alarm or cutoff. Live readings
are logged separately to
`logs\ccn_v10_0_dev21_tension_YYYY-MM-DD.csv`.

### Plot tension against a cable counter

Open **Modbus Settings...** and choose the specific cable card in
**Cable counter for plot**. The choice includes the source and SCC address, so
two counters with the same address on different COM sources remain distinct.
The **Tension vs Cable Plot...** button opens a live plot. Each new tension
sample is paired with the latest linked cable reading if that cable reading is
less than two seconds old. The horizontal axis uses the cable card's displayed
value (including its offsets); the vertical axis uses the zero-adjusted tension.
The plot keeps up to 2,000 paired points in memory. Tension CSV rows include
the linked cable source, address, displayed value, and units when a fresh cable
reading is available.

### Simulate tension

Use **Playback > Simulated Tension > Start Tension Simulation** to exercise the
separate tension pane without hardware. The simulation moves between the
configured start and end values, uses the selected display unit, and can be
linked to a simulated or live cable card for plot testing. Set a warning or
critical threshold and a simulation range above it to test the alarms.
Enable **Simulate lost communication** in Tension Settings to stop updates
after ten samples (about five seconds) and observe the stale/lost watchdog
states. Stop the simulation before connecting the amplifier. Simulation data
is not added to CSV logs.

### Resetting an SCC

Use **Connection > Reset SCC on Connected Port...** to choose a connected port
and send an SCC reset command. This is separate from zeroing the displayed
value. Use it only when you intend to reset the SCC attached to that port.

## 4. Read and adjust counter cards

Each card shows the source, address, displayed value, raw cable value,
installation offset, direction, speed, calibration, watchdog, and last-data
time.

The displayed value is calculated as:

```text
displayed value = raw cable + installation offset + zero offset
```

- **ZERO DISPLAY** changes the software zero offset for that card. It does not
  change the raw input or send a command to the SCC.
- **INSTALL OFFSET** changes the installation offset for that card.
- **Set Label** changes the card's local label.
- **Display / Alert** configures its readout color and optional near-target
  alerts.
- **View > Audible Critical Alarm** turns critical-alert sounds on or off.
  The on/off choice is saved.
- **View > Critical Alarm Sound** selects **Windows System Beep** or the
  sound configured for Windows' **Low Battery Alarm** event. Use **Test
  Selected Sound** in that submenu to play the selected sound once; this test
  works even when the alarm is turned off.
  A new critical alert plays the selected sound up to ten times. System beeps
  are about half a second apart; the Windows Low Battery Alarm sound repeats
  about every two seconds. The sequence stops if the critical condition clears,
  and does not repeat while it remains active. Turning the alarm off stops
  sounds in progress. The sound choice is saved.
- Use **View > Counter Displays** to hide or show individual counter cards,
  identified by label, source, and SCC address. New displays are enabled by
  default; hiding a card does not stop its data source or logging.
- Drag the small handle at the card's lower-right corner to resize it. Use
  **View > Reset Counter Card Sizes** to restore default sizes.
- **View > Appearance** changes the theme. **View > Cable Display Size** changes
  the large reading font.

The watchdog changes from receiving data to stale/lost when updates stop.
Alerts use the card's displayed value and units. Critical alerts also blink
red and can play the optional audible alarm.

## 5. Use playback files

Playback is useful for reviewing previously recorded SCC data without a live
counter.

1. Choose **Playback > Browse Playback File...** for one file, or
   **Add Multiple Playback Files...** for several.
2. Choose **Playback > Play Playback**.
3. Choose **Playback > Stop Playback** to stop and rewind the loaded sources.

CCN reads text files line by line and processes valid SCC records; unrelated
lines are ignored. Multiple playback files are treated as separate sources.
Playback does not write commands to a physical SCC.

## 6. Use simulated counters

Choose **Playback > Simulated Counters** and start two or three counters.
Simulation generates test readings inside CCN; it does not use a COM port or
control hardware.

**Simulation Settings...** sets Start and End values for addresses A, B, and C.
Each value moves from Start to End and back. The default ranges are:

| Address | Start | End |
|---|---:|---:|
| A | 0 m | 50 m |
| B | 50 m | 100 m |
| C | 125 m | 200 m |

Simulation ranges are saved in the CCN configuration. **ZERO DISPLAY** changes
the display offset; it does not change the simulation's raw Start/End range.
If you click **Restore Defaults** and accept the Simulation Settings dialog,
CCN also clears the saved display-zero offsets for simulated counters and
resets their raw readings to the configured Start values. It resets simulation
motion too, but does not change offsets for COM or playback counters. The default
Start values are 0 m for A, 50 m for B, and 125 m for C.

## 7. Test with SS Serial Generator

**SS Serial Generator** is a separate test utility. It sends SCC-format text
records; it does not control or imitate every function of a physical SCC.

### Connect the generator to CCN

Use either:

- A virtual COM pair, with the generator and CCN using opposite endpoints; or
- Two USB-to-RS232 adapters joined by a **null-modem** cable. Both adapters
  plug into the PC; the generator opens one COM port and CCN opens the other.

The two applications must use different COM endpoints. A straight-through
cable does not provide the crossed transmit/receive wiring of a null-modem
link.

### Send test records

1. Close serial terminals that might have either COM port open.
2. In SS Serial Generator, refresh/select the **generator** COM port.
3. Set the address (A-D), units (M/F), calibration, starting cable value,
   direction, speed, and send interval.
4. In CCN, select the other end of the pair and click **Connect**.
5. Click **Start Sending** in the generator. CCN should create/update a card
   for that address.
6. Click **Stop** in the generator before changing ports or closing it.

The generator sends at **9600 baud, 8-N-1**. Its defaults are address A, meters,
calibration `+0357`, starting value `0.7`, paying out at `0.5` units/second,
and a `500 ms` send interval.

## 8. Use the TCP server and view-only clients

The server PC owns the COM connections and all live inputs. Client windows
receive counter state and display it; clients cannot connect/disconnect COM
ports, reset an SCC, run playback, or run simulation.

### Test both ends on one PC

1. Open a first CCN window.
2. Start simulated counters from **Playback > Simulated Counters**.
3. Choose **Network > Start TCP Server**. The default port is `8765`.
4. Open a second CCN window from another terminal.
5. In the second window, choose **Network > Connect to Server**. Enter
   `127.0.0.1` and the same port.
6. Confirm the second window shows the server's counter cards and changing
   values.

The two windows share the same local configuration and output folders. Turn
off **Enable Logging** in the client if you do not want it to append a second
copy of readings to the CSV log.

### Connect another PC on the same network

1. Start the server on the PC connected to the serial equipment.
2. Find that PC's LAN IPv4 address (for example, run `ipconfig` in a terminal).
3. On the client PC, start the same CCN version and choose **Network > Connect
   to Server**.
4. Enter the server PC's LAN IPv4 address and the server's port (default
   `8765`).
5. If Windows Firewall prompts, allow the application on the **private**
   network only.

Keep TCP use on a trusted LAN or VPN. DEV21's view-only TCP service has no
login and sends data in plaintext. Do not forward its port to the public
internet.

## 9. Logging, recordings, and settings

- When **Enable Logging** is checked, CCN appends processed readings to
  `logs\ccn_v10_0_dev21_YYYY-MM-DD.csv`.
- ATO tension readings are written separately to
  `logs\ccn_v10_0_dev21_tension_YYYY-MM-DD.csv`; linked cable values are
  included only when a recent reading is available.
- Raw serial input is also recorded to
  `recordings\scc_raw_YYYY-MM-DD.txt`.
- When running the Python source from `C:\CNN`, configuration, logs, and
  recordings are stored under that working folder.
- The installed V1 app stores them under
  `%LOCALAPPDATA%\CSA\Cable Counter Display V1`, with logs and recordings in
  their own subfolders.

When running two windows from the same folder, they share these files. Avoid
changing settings in both windows at the same time.

## 10. Troubleshooting

| Symptom | Checks |
|---|---|
| COM port is missing | Check Device Manager, then use **Connection > Refresh Ports**. |
| COM port will not open | Close other serial programs and verify the selected port. |
| Tension shows counts | Set the Modbus scale and unit after confirming the amplifier's value format. |
| Tension has no live data | Confirm RS-485 A/B wiring, amplifier Modbus mode/address, baud, parity, and the selected COM port. |
| Cable/tension plot is empty | Select the correct source/address in **Modbus Settings...** and confirm both sources have recent readings. |
| Connected, but no card appears | Confirm the generator/SCC is sending valid SCC records at 9600 8-N-1. |
| Generator sends, but CCN stays blank | Confirm the generator and CCN use opposite ends of a working null-modem or virtual pair. |
| TCP client cannot connect | Start the server first; check the host IP, matching port, same network, and private-network firewall permission. |
| TCP client shows stale data | Check that the server is still running and its input source is sending. |
| Cannot connect as a client | Stop local COM, playback, or simulation sources in that window first. |

## 11. Preparing a Windows installer

Run `.\build_ccn_v1.ps1` from PowerShell in `C:\CNN` to build the package.
The build packages DEV21 using V3 output names:

- `dist\CSA Cable Counter Display V3.exe`
- `dist\installer\CSA_Cable_Counter_Display_V3_Setup.exe`

The installer is per-user and does not require administrator privileges. The
existing installed application name and location remain `CSA Cable Counter
Display V1` for compatibility with the earlier installer. The manual and CSA
logo are bundled into the application. Configuration, logs, and recordings are
kept outside the install folder under
`%LOCALAPPDATA%\CSA\Cable Counter Display V1`.

Test installation, launch, serial access, logging, uninstall, and reinstall
using a standard Windows account. The installer does not remove user data when
the application is uninstalled.
