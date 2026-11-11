"""
===============================================================================
CCN - Cable Counter Network
Version: 0.6 GUI Prototype

Author:
    Scott Sharpe / Copilot Development

Purpose:
    GUI framework for SCC Cable Counter monitoring.

Current Features:
    - COM Port Detection
    - Connect Button
    - Disconnect Button
    - Status Display
    - Event Log
    - Large Cable Out Display

Future Features:
    - SCC Serial Data Reading
    - Address Display
    - Direction Display
    - Speed Display
    - Calibration Display
    - TCP / UDP Broadcasting
    - Multiple Cable Counters
===============================================================================
"""

import sys
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


class CCNMainWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.ser = None

        self.setWindowTitle(
            "CCN - Cable Counter Network"
        )

        self.resize(800, 700)

        self.build_ui()

    # -----------------------------------------------------------------
    # Connect Button
    # -----------------------------------------------------------------

    def connect_port(self):

        selected_port = (
            self.com_port_combo.currentText()
        )

        self.log_window.append(
            f"Attempting connection to {selected_port}"
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

        except Exception as e:

            self.status_label.setText(
                "Status: CONNECTION FAILED"
            )

            self.log_window.append(
                f"ERROR: {e}"
            )

    # -----------------------------------------------------------------
    # Disconnect Button
    # -----------------------------------------------------------------

    def disconnect_port(self):

        try:

            if self.ser is not None:
                self.ser.close()

            self.status_label.setText(
                "Status: DISCONNECTED"
            )

            self.log_window.append(
                "Port disconnected"
            )

        except Exception as e:

            self.log_window.append(
                f"ERROR: {e}"
            )

    # -----------------------------------------------------------------
    # Build User Interface
    # -----------------------------------------------------------------

    def build_ui(self):

        main_layout = QVBoxLayout()

        # -------------------------------------------------------------
        # CONNECTION SECTION
        # -------------------------------------------------------------

        com_group = QGroupBox("Connection")

        com_layout = QHBoxLayout()

        self.com_label = QLabel("COM Port:")

        self.com_port_combo = QComboBox()

        ports = serial.tools.list_ports.comports()

        for port in ports:
            self.com_port_combo.addItem(
                port.device
            )

        self.connect_button = QPushButton(
            "Connect"
        )

        self.connect_button.clicked.connect(
            self.connect_port
        )

        self.disconnect_button = QPushButton(
            "Disconnect"
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

        # -------------------------------------------------------------
        # STATUS
        # -------------------------------------------------------------

        self.status_label = QLabel(
            "Status: DISCONNECTED"
        )

        # -------------------------------------------------------------
        # CABLE COUNTER DISPLAY
        # -------------------------------------------------------------

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
            "font-size: 32px;"
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

        # -------------------------------------------------------------
        # EVENT LOG
        # -------------------------------------------------------------

        log_group = QGroupBox(
            "Event Log"
        )

        log_layout = QVBoxLayout()

        self.log_window = QTextEdit()

        self.log_window.setReadOnly(
            True
        )

        self.log_window.append(
            "CCN v0.6 GUI Started"
        )

        log_layout.addWidget(
            self.log_window
        )

        log_group.setLayout(
            log_layout
        )

        # -------------------------------------------------------------
        # ADD EVERYTHING TO MAIN WINDOW
        # -------------------------------------------------------------

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