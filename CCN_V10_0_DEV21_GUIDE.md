# CCN DEV21 - Tension Integration: Beginner's Guide

This guide is a map to the DEV21 program. You do not need to understand every
line before making a small change. The working application is
[CCN_V10_0_DEV21.py](./CCN_V10_0_DEV21.py); keep the earlier DEV19 and DEV20 files unchanged.
For operating instructions, use the [DEV21 User Manual](./CCN_V10_0_DEV21_User_Manual.md).
For the development and backup process, see the
[VS Code and Copilot Workflow](./CCN_VSCode_Copilot_Workflow.md).

## Run DEV21

Open a VS Code terminal and run:

```powershell
cd C:\CNN
python .\CCN_V10_0_DEV21.py
```

If `python` is not recognized, try `py .\CCN_V10_0_DEV21.py`. Run from `C:\CNN`
so the application finds the expected `ccn_config.json`, `logs`, and
`recordings` folders.

## What happens when the program starts

Near the bottom of the file, the program:

1. Creates a Qt application.
2. Creates a `CCNMainWindow` object.
3. Shows the window and starts Qt's event loop.

The event loop waits for button clicks, timer ticks, serial data, and TCP
network events. Most application behavior is organized as methods on
`CCNMainWindow`.

## How counter data moves

```text
COM port -----------\
Playback file -------+--> process_scc_line --> source state and counter card
Simulation ----------/                         |--> CSV log
                                               \--> TCP clients (server mode)

ATO RS-485 COM --> Modbus RTU poll --> tension pane --> tension CSV
                                           |
                                           +--> optional cable/tension plot

TCP server --> client socket --> apply_remote_counter --> remote counter card
```

`process_scc_line` is the main entry point for locally received SCC text. It
checks the record, updates the matching source, refreshes the card, optionally
writes a CSV row, and broadcasts the update if this window is acting as a TCP
server.

Each counter is identified by its **source ID** and **address**. For example,
`COM4` plus address `A` is a different counter from `COM5` plus address `A`.
This is why the app can show several ports and playback sources at once.

The ATO amplifier is a separate Modbus RTU source; it does not send SCC text
and does not use an SCC input row. In Modbus Settings, the tension pane can be
linked to one exact cable card (source plus address). New tension samples pair
with that card's latest cable value when it is recent, for the live plot and
tension CSV. The Modbus scale and unit need confirmation against the amplifier;
the initial display is unscaled register counts.

The **View > Show Tension Panel** action hides or shows the full tension panel,
including the adapter COM controls, without disconnecting the input. The
**RESET TENSION ZERO** button clears only the tension software zero; it does
not alter cable-counter zeroing or installation offsets.
The tension label is editable, and its peak tracks the highest displayed
reading since the last reset. Separate high-warning and high-critical alarm
thresholds and colors are configured with **Alarm Settings...**; critical
tension shares the optional audible alarm with the counter cards.

## Finding the main parts of the code

Use VS Code's Find feature (`Ctrl+F`) to search for these method names:

| What you want to understand or change | Where to look |
|---|---|
| Startup defaults and COM/TCP limits | Constants near the top of the file |
| Saved preferences | `load_config`, `save_config` |
| Menus and menu actions | `build_menus`, `show_about` |
| Main screen layout | `build_ui`, `create_port_row` |
| COM port connect/disconnect | `refresh_ports`, `connect_port`, `disconnect_port` |
| ATO tension Modbus COM input | `connect_tension_port`, `read_tension_data` |
| Tension/cable pairing and plot | `apply_tension_reading`, `TensionCablePlot` |
| Reading complete serial records | `read_serial_data` |
| Checking and applying an SCC record | `process_scc_line` |
| Counter state and card creation | `get_source_state`, `create_counter_card` |
| Updating a counter card | `update_counter_card` |
| TCP server / client | `start_tcp_server`, `connect_tcp_client` |
| Sending live state to clients | `broadcast_counter_state` |
| Applying received state on a client | `apply_remote_counter` |
| Playback files | `add_playback_source`, `start_playback`, `playback_tick` |
| Simulated counters | `start_simulation`, `simulation_tick` |
| Shutting down timers and ports | `closeEvent` |

## A few Python ideas used here

- **`self`** means “this particular CCN window.” For example,
  `self.serial_connections` is the set of COM connections owned by that window.
- **A dictionary** stores related values by name. A counter state has entries
  such as `raw_cable`, `units`, and `direction`.
- `ato_modbus.py` contains the small Modbus RTU request, CRC, and net-weight
  response helpers used by the separate tension input.
- **A method** is a function that belongs to a class. `connect_port` and
  `process_scc_line` are methods of `CCNMainWindow`.
- **A Qt signal** announces an event. For example,
  `timer.timeout.connect(self.read_serial_data)` means “when this timer expires,
  call `read_serial_data`.”
- **`QTimer`** schedules repeated work without pausing the window. Serial
  polling, playback, simulation, and watchdog updates use timers.
- **A layout** arranges widgets. `build_ui` creates the visible labels, buttons,
  and panels; it does not read serial data.

## Testing the TCP display on one PC

1. Open one DEV21 window. Start simulated counters from the **Playback** menu,
   then choose **Network → Start TCP Server**.
2. Open a second DEV21 window from another VS Code terminal.
3. In the second window, choose **Network → Connect to Server** and enter
   `127.0.0.1` with the server's port (default `8765`).
4. The second window should show the server's counter data. It is view-only;
   the server keeps control of COM ports and operating actions.

The TCP service has no login, so use it only on a trusted local network or VPN.
Do not forward its port from the internet. On a second PC, Windows Firewall may
need to allow the app on the private network.

## Files and settings

- `ccn_config.json` stores local display and counter preferences.
- `logs` contains CSV readings when logging is enabled.
- `recordings` contains raw serial text recordings.
- The standalone serial generator is a separate program; it sends test SCC
  records but does not control a physical SCC counter.

When two DEV21 windows run from the same folder, they share the configuration
and log folders. For a local TCP test, turn off **Enable Logging** in the client
window if you do not want both windows writing readings.
