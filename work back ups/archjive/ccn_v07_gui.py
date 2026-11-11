"""
===============================================================================
CCN - Cable Counter Network
Version: 0.7

Author:
    Scott Sharpe / Copilot Development

Purpose:
    GUI version of the SCC Cable Counter.

Current Features:
    - COM Port Selection
    - Connect / Disconnect
    - Live SCC Data Display
    - Address Display
    - Cable Out Display
    - Direction Display
    - Speed Display
    - Calibration Display
    - Event Log
===============================================================================
"""

import sys
import re
import time
import serial
import serial.tools.list_ports

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QComboBox,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox
)

from PyQt6.QtCore import QTimer


class CCNMainWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.ser = None

        self.previous_cable = None
        self.previous_time = None

        self.setWindowTitle(
            "CCN - Cable Counter Network v0.7"
        )

        self.resize(900, 700)

        self.build_ui()

        # Timer used to read serial data
        self.timer = QTimer()
        self.timer.timeout.connect(
            self.read_serial_data
        )

    # ------------------------------------------------------------------
    # Connect Button
    # ------------------------------------------------------------------

    def connect_port(self):

        selected_port = (
            self.com_port_combo.currentText()
        )

        try:

            self.ser = serial.Serial(
                port=selected_port,
                baudrate=9600,
                timeout=1
            )

            self.status_label.setText(
                f"Status: CONNECTED TO {selected_port}"
            )

            self.log_window.append(
                f"Connected to {selected_port}"
            )

            self.timer.start(200)

        except Exception as e:

            self.status_label.setText(
                "Status: CONNECTION FAILED"
            )

            self.log_window.append(
                f"ERROR: {e}"
            )

    # ------------------------------------------------------------------
    # Disconnect Button
    # ------------------------------------------------------------------

    def disconnect_port(self):

        try:

            self.timer.stop()

            if self.ser:
                self.ser.close()

            self.status_label.setText(
                "Status: DISCONNECTED"
            )

            self.log_window.append(
                "Disconnected"
            )

        except Exception as e:

            self.log_window.append(
                f"ERROR: {e}"
            )

    # ------------------------------------------------------------------
    # Read Serial Data
    # ------------------------------------------------------------------

    def read_serial_data(self):

        if self.ser is None:
            return

        try:

            if self.ser.in_waiting:

                line = (
                    self.ser.readline()
                    .decode(
                        "utf-8",
                        errors="ignore"
                    )
                    .strip()
                )

                self.parse_scc_string(line)

        except Exception as e:

            self.log_window.append(
                f"RX ERROR: {e}"
            )

    # ------------------------------------------------------------------
    # Parse SCC String
    # ------------------------------------------------------------------

    def parse_scc_string(self, line):

        pattern = (
            r"\$CC([A-D])([\d\.]+)([MF])([+-]\d{4})"
        )

        match = re.match(
            pattern,
            line
        )

        if not match:
            return

        address = match.group(1)
        cable_out = float(
            match.group(2)
        )
        units = match.group(3)
        calibration = match.group(4)

        # --------------------------------------------------------------
        # Direction / Speed
        # --------------------------------------------------------------

        direction = "STOPPED"
        speed = 0.0

        current_time = time.time()

        if (
            self.previous_cable is not None
            and
            self.previous_time is not None
        ):

            delta_cable = (
                cable_out
                - self.previous_cable
            )

            delta_time = (
                current_time
                - self.previous_time
            )

            if delta_time > 0:

                speed = abs(
                    delta_cable
                    / delta_time
                )

            if delta_cable > 0.01:

                direction = (
                    "PAYING OUT"
                )

            elif delta_cable < -0.01:

                direction = (
                    "HAULING IN"
                )

        self.previous_cable = cable_out
        self.previous_time = current_time

        # --------------------------------------------------------------
        # Update Display
        # --------------------------------------------------------------

        self.address_label.setText(
            f"Address: {address}"
        )

        self.cable_label.setText(
            f"Cable Out: {cable_out:.1f} {units}"
        )

        self.direction_label.setText(
            f"Direction: {direction}"
        )

        self.speed_label.setText(
            f"Speed: {speed:.3f} {units}/s"
        )

        self.calibration_label.setText(
            f"Calibration: {calibration}"
        )

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def build_ui(self):

        main_layout = QVBoxLayout()

        # --------------------------------------------------------------
        # Connection Group
        # --------------------------------------------------------------

        com_group = QGroupBox(
            "Connection"
        )

        com_layout = QHBoxLayout()

        self.com_label = QLabel(
            "COM Port:"
        )

        self.com_port_combo = (
            QComboBox()
        )

        ports = (
            serial.tools.list_ports
            .comports()
        )

        for port in ports:

            self.com_port_combo.addItem(
                port.device
            )

        self.connect_button = (
            QPushButton(
                "Connect"
            )
        )

        self.connect_button.clicked.connect(
            self.connect_port
        )

        self.disconnect_button = (
            QPushButton(
                "Disconnect"
            )
        )

        self.disconnect_button.clicked.connect(
            self.disconnect_port
        )

        com_layout.addWidget(
            self.com_label
        )

        com_layout.addWidget(
            self.com_port_combo
        )

        com_layout.addWidget(
            self.connect_button
        )

        com_layout.addWidget(
            self.disconnect_button
        )

        com_group.setLayout(
            com_layout
        )

        # --------------------------------------------------------------
        # Status
        # --------------------------------------------------------------

        self.status_label = QLabel(
            "Status: DISCONNECTED"
        )

        # --------------------------------------------------------------
        # Cable Data
        # --------------------------------------------------------------

        cable_group = QGroupBox(
            "Cable Counter Data"
        )

        cable_layout = QVBoxLayout()

        self.address_label = QLabel(
            "Address: ---"
        )

        self.cable_label = QLabel(
            "Cable Out: 0.0 m"
        )

        self.cable_label.setStyleSheet(
            "font-size: 36px;"
            "font-weight: bold;"
        )

        self.direction_label = QLabel(
            "Direction: STOPPED"
        )

        self.speed_label = QLabel(
            "Speed: 0.000 m/s"
        )

        self.calibration_label = QLabel(
            "Calibration: ----"
        )

        cable_layout.addWidget(
            self.address_label
        )

        cable_layout.addWidget(
            self.cable_label
        )

        cable_layout.addWidget(
            self.direction_label
        )

        cable_layout.addWidget(
            self.speed_label
        )

        cable_layout.addWidget(
            self.calibration_label
        )

        cable_group.setLayout(
            cable_layout
        )

        # --------------------------------------------------------------
        # Event Log
        # --------------------------------------------------------------

        log_group = QGroupBox(
            "Event Log"
        )

        log_layout = QVBoxLayout()

        self.log_window = QTextEdit()

        self.log_window.setReadOnly(
            True
        )

        self.log_window.append(
            "CCN v0.7 GUI Started"
        )

        log_layout.addWidget(
            self.log_window
        )

        log_group.setLayout(
            log_layout
        )

        # --------------------------------------------------------------
        # Main Layout
        # --------------------------------------------------------------

        main_layout.addWidget(
            com_group
        )

        main_layout.addWidget(
            self.status_label
        )

        main_layout.addWidget(
            cable_group
        )

        main_layout.addWidget(
            log_group
        )

        self.setLayout(
            main_layout
        )


def main():

    app = QApplication(
        sys.argv
    )

    window = CCNMainWindow()

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()