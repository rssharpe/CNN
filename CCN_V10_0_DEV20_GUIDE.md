# CCN DEV20: Beginner's Guide

This guide is a map to the DEV20 program. You do not need to understand every
line before making a small change. The working application is
[CCN_V10_0_DEV20.py](./CCN_V10_0_DEV20.py); keep the frozen DEV19 file unchanged.
For operating instructions, use the [DEV20 User Manual](./CCN_V10_0_DEV20_User_Manual.md).
For the development and backup process, see the
[VS Code and Copilot Workflow](./CCN_VSCode_Copilot_Workflow.md).

## Run DEV20

Open a VS Code terminal and run:

```powershell
cd C:\CNN
python .\CCN_V10_0_DEV20.py
```

If `python` is not recognized, try `py .\CCN_V10_0_DEV20.py`. Run from `C:\CNN`
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

TCP server --> client socket --> apply_remote_counter --> remote counter card
```

`process_scc_line` is the main entry point for locally received SCC text. It
checks the record, updates the matching source, refreshes the card, optionally
writes a CSV row, and broadcasts the update if this window is acting as a TCP
server.

Each counter is identified by its **source ID** and **address**. For example,
`COM4` plus address `A` is a different counter from `COM5` plus address `A`.
This is why the app can show several ports and playback sources at once.

## Finding the main parts of the code

Use VS Code's Find feature (`Ctrl+F`) to search for these method names:

| What you want to understand or change | Where to look |
|---|---|
| Startup defaults and COM/TCP limits | Constants near the top of the file |
| Saved preferences | `load_config`, `save_config` |
| Menus and menu actions | `build_menus` |
| Main screen layout | `build_ui`, `create_port_row` |
| COM port connect/disconnect | `refresh_ports`, `connect_port`, `disconnect_port` |
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

1. Open one DEV20 window. Start simulated counters from the **Playback** menu,
   then choose **Network → Start TCP Server**.
2. Open a second DEV20 window from another VS Code terminal.
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

When two DEV20 windows run from the same folder, they share the configuration
and log folders. For a local TCP test, turn off **Enable Logging** in the client
window if you do not want both windows writing readings.
