"""
===============================================================================
CCN - Cable Counter Network
Version: 0.4 GUI Prototype
Author: Scott Sharpe / Copilot Development

Purpose:
    First GUI prototype for the Cable Counter Network project.

Current Features:
    - PyQt6 GUI
    - COM Port selection
    - Connect button
    - Disconnect button
    - Status indicator
    - Event log window

Future Features:
    - Live serial communications
    - Cable Out display
    - Direction indication
    - Speed display
    - Calibration display
    - TCP/UDP broadcasting
    - Multiple counters
===============================================================================
"""

import sys
import serial.tools.list_ports
import serial

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

        self.setWindowTitle("CCN - Cable Counter Network")
        self.resize(700, 600)

        self.build_ui()

        def connect_port(self):

        self.log_window.append(
            "connect_port function called"
        )

    def build_ui(self):

        main_layout = QVBoxLayout()
        # ------------------------------------------------------------
        # COM PORT SECTION
        # ------------------------------------------------------------

        com_group = QGroupBox("Connection")

        com_layout = QHBoxLayout()

        self.com_label = QLabel("COM Port:")

        self.com_port_combo = QComboBox()

        ports = serial.tools.list_ports.comports()

        for port in ports:
            self.com_port_combo.addItem(port.device)

        self.connect_button = QPushButton("Connect")

        self.connect_button.clicked.connect(
        self.connect_port
    )

        

        self.disconnect_button = QPushButton("Disconnect")

        com_layout.addWidget(self.com_label)
        com_layout.addWidget(self.com_port_combo)
        com_layout.addWidget(self.connect_button)
        com_layout.addWidget(self.disconnect_button)

        com_group.setLayout(com_layout)

        # ------------------------------------------------------------
        # STATUS SECTION
        # ------------------------------------------------------------

        self.status_label = QLabel("Status: DISCONNECTED")

        # ------------------------------------------------------------
        # CABLE DISPLAY SECTION
        # ------------------------------------------------------------

        cable_group = QGroupBox("Cable Counter Data")

        cable_layout = QVBoxLayout()

        self.address_label = QLabel("Address: ---")

        self.cable_label = QLabel("Cable Out: 0.0 m")
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

        cable_layout.addWidget(self.address_label)
        cable_layout.addWidget(self.cable_label)
        cable_layout.addWidget(self.direction_label)
        cable_layout.addWidget(self.speed_label)
        cable_layout.addWidget(self.calibration_label)

        cable_group.setLayout(cable_layout)

        # ------------------------------------------------------------
        # EVENT LOG
        # ------------------------------------------------------------

        log_group = QGroupBox("Event Log")

        log_layout = QVBoxLayout()

        self.log_window = QTextEdit()
        self.log_window.setReadOnly(True)

        self.log_window.append(
            "CCN v0.4 GUI started"
        )

        log_layout.addWidget(self.log_window)

        log_group.setLayout(log_layout)

        # ------------------------------------------------------------
        # ADD SECTIONS TO MAIN WINDOW
        # ------------------------------------------------------------

        main_layout.addWidget(com_group)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(cable_group)
        main_layout.addWidget(log_group)

        self.setLayout(main_layout)


def main():

    app = QApplication(sys.argv)

    window = CCNMainWindow()

    window.show()

    sys.exit(app.exec())

    


if __name__ == "__main__":
    main()