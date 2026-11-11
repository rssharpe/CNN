"""
===============================================================================
CCN - Cable Counter Network
Version: 0.1 Prototype

Author: Scott Sharpe / Copilot Development

Purpose:
    Read SCC Bluetooth Cable Counter data from a serial COM port,
    decode the incoming string, determine:

        - Counter Address
        - Cable Out
        - Units
        - Calibration Factor
        - Direction (IN / OUT / STOPPED)
        - Cable Speed (m/s)

Example SCC Message:

    $CCB00000.7M,+0357

Decoded As:

    Address      = B
    Cable Out    = 0.7
    Units        = M
    Calibration  = +0357

Future Versions:

    - PyQt6 GUI
    - Full Screen Display
    - TCP Server
    - UDP Broadcast
    - Multiple Counters
    - Alarms
    - Logging

===============================================================================
"""

import os

import serial
import re
import time
from datetime import datetime


# ============================================================================
# USER SETTINGS
# ============================================================================

COM_PORT = "COM7"
BAUD_RATE = 9600


# ============================================================================
# SCC STRING PARSER
# ============================================================================

def parse_scc_string(data_string):
    """
    Parse SCC message.

    Example:
        $CCB00000.7M,+0357

    Returns dictionary or None if parsing fails.
    """

    pattern = r"\$CC([A-D])([\d\.]+)([MF])([+-]\d{4})"

    match = re.search(pattern, data_string)

    if not match:
        return None

    return {
        "address": match.group(1),
        "cable_out": float(match.group(2)),
        "units": match.group(3),
        "calibration": match.group(4)
    }


# ============================================================================
# MAIN PROGRAM
# ============================================================================

def main():

    print("\n")
    print("=" * 70)
    print("CCN - CABLE COUNTER NETWORK PROTOTYPE")
    print("=" * 70)

    print(f"Opening {COM_PORT}...")

    try:

        ser = serial.Serial(
            port=COM_PORT,
            baudrate=BAUD_RATE,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=1
        )

    except Exception as e:

        print(f"\nERROR OPENING PORT: {e}")
        input("\nPress ENTER to exit...")
        return

    print("CONNECTED\n")

    previous_cable = None
    previous_time = None
    last_movement_time = None

    while True:

        try:

            # ---------------------------------------------------------------
            # Read serial line
            # ---------------------------------------------------------------

            raw_line = ser.readline()
            

            if not raw_line:
                continue

            line = raw_line.decode(
                errors="ignore"
            ).strip()

            # Example:
            # $CCB00000.7M,+0357

            result = parse_scc_string(line)

            

            if result is None:
                continue

            current_time = time.time()

            cable_out = result["cable_out"]

            # ---------------------------------------------------------------
            # Calculate direction and speed
            # ---------------------------------------------------------------

            direction = "STOPPED"
            speed = 0.0

            if previous_cable is not None:

                delta_cable = cable_out - previous_cable

                delta_time = (
                    current_time - previous_time
                )

                if delta_time > 0:

                    speed = abs(
                        delta_cable / delta_time
                    )

                if delta_cable > 0.01:
                    direction = "HAULING IN"
                    last_movement_time = current_time

                else:

                    if (
                        last_movement_time is not None
                    and
                    (current_time - last_movement_time) < 8.0
                ):
                        pass

                    else:
                    
                        direction = "STOPPED"
                

                
            previous_cable = cable_out
            previous_time = current_time

            # ---------------------------------------------------------------
            # Display data
            # ---------------------------------------------------------------

            print("\033[2J\033[H", end="")

            
           

            print(
                f"Time        : "
                f"{datetime.now().strftime('%H:%M:%S')}"
            )

            print(
                f"Address     : "
                f"{result['address']}"
            )

            print(
                f"Cable Out   : "
                f"{result['cable_out']:.1f}"
            )

            print(
                f"Units       : "
                f"{result['units']}"
            )

            print(
                f"Calibration : "
                f"{result['calibration']}"
            )

            print(
                f"Direction   : "
                f"{direction}"
            )

            print(
                f"Speed       : "
                f"{speed:.3f} m/s"
            )

            print(
                f"Speed       : "
                f"{speed * 60:.2f} m/min"
            )

            print(
                f"Speed       : "
                f"{speed * 196.850:.2f} ft/min"
            )

        except KeyboardInterrupt:

            print("\n\nProgram Stopped")

            ser.close()

            break

        except Exception as e:

            print(f"\nERROR: {e}")


# ============================================================================
# PROGRAM ENTRY
# ============================================================================

if __name__ == "__main__":
    main()