
"""
CCN - Cable Counter Network
Version: 0.8

Enhancements over V0.7
- CSA Logo support (CSA_Logo.png)
- Local and UTC clocks
- Timestamped event log
- CSV recording
- Speed smoothing (rolling average)
- Credits footer
- RESET/OFFSET placeholders
"""

import sys
import re
import time
import csv
from collections import deque
from datetime import datetime, timezone

import serial
import serial.tools.list_ports

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QComboBox, QTextEdit, QVBoxLayout,
    QHBoxLayout, QGroupBox
)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap

class CCNMainWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.ser = None
        self.previous_cable = None
        self.previous_time = None
        self.speed_history = deque(maxlen=10)

        self.log_filename = datetime.now().strftime('CCN_%Y%m%d_%H%M%S.csv')
        self.csv_file = None
        self.csv_writer = None

        self.setWindowTitle('CCN - Cable Counter Network v0.8')
        self.resize(1000, 800)

        self.build_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self.read_serial_data)

        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clocks)
        self.clock_timer.start(1000)
        self.update_clocks()

    def log_event(self, message):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_window.append(f'[{timestamp}] {message}')

    def update_clocks(self):
        self.local_time_label.setText('Local: ' + datetime.now().strftime('%H:%M:%S'))
        self.utc_time_label.setText('UTC:   ' + datetime.now(timezone.utc).strftime('%H:%M:%S'))

    def start_csv_logging(self):
        if self.csv_file is None:
            self.csv_file = open(self.log_filename, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow([
                'UTC','Address','CableOut','Units','Direction','Speed','Calibration'
            ])

    def connect_port(self):
        port = self.com_port_combo.currentText()
        try:
            self.ser = serial.Serial(port=port, baudrate=9600, timeout=1)
            self.status_label.setText(f'Status: CONNECTED TO {port}')
            self.log_event(f'Connected to {port}')
            self.start_csv_logging()
            self.timer.start(200)
        except Exception as e:
            self.status_label.setText('Status: CONNECTION FAILED')
            self.log_event(f'ERROR: {e}')

    def disconnect_port(self):
        self.timer.stop()
        if self.ser:
            self.ser.close()
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
        self.status_label.setText('Status: DISCONNECTED')
        self.log_event('Disconnected')

    def read_serial_data(self):
        if self.ser is None:
            return
        try:
            if self.ser.in_waiting:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                self.parse_scc_string(line)
        except Exception as e:
            self.log_event(f'RX ERROR: {e}')

    def parse_scc_string(self, line):
        match = re.match(r'\$CC([A-D])([\d\.]+)([MF])([+-]\d{4})', line)
        if not match:
            return

        address = match.group(1)
        cable_out = float(match.group(2))
        units = match.group(3)
        calibration = match.group(4)

        direction = 'STOPPED'
        speed = 0.0

        current_time = time.time()

        if self.previous_cable is not None and self.previous_time is not None:
            delta_cable = cable_out - self.previous_cable
            delta_time = current_time - self.previous_time

            if delta_time > 0:
                inst_speed = abs(delta_cable / delta_time)
                self.speed_history.append(inst_speed)
                speed = sum(self.speed_history) / len(self.speed_history)

            if delta_cable > 0.01:
                direction = 'PAYING OUT'
            elif delta_cable < -0.01:
                direction = 'HAULING IN'

        self.previous_cable = cable_out
        self.previous_time = current_time

        self.address_label.setText(f'Address: {address}')
        self.cable_label.setText(f'{cable_out:.1f} {units}')
        self.direction_label.setText(f'Direction: {direction}')
        self.speed_label.setText(f'Speed: {speed:.3f} {units}/s')
        self.calibration_label.setText(f'Calibration: {calibration}')

        if self.csv_writer:
            self.csv_writer.writerow([
                datetime.now(timezone.utc).isoformat(),
                address, cable_out, units, direction,
                f'{speed:.3f}', calibration
            ])
            self.csv_file.flush()

    def build_ui(self):
        main_layout = QVBoxLayout()

        logo = QLabel()
        pix = QPixmap('CSA_Logo.png')
        if not pix.isNull():
            logo.setPixmap(pix.scaledToHeight(100))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(logo)

        title = QLabel('Cable Counter Network (CCN) v0.8')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet('font-size:24px;font-weight:bold;')
        main_layout.addWidget(title)

        self.local_time_label = QLabel()
        self.utc_time_label = QLabel()
        main_layout.addWidget(self.local_time_label)
        main_layout.addWidget(self.utc_time_label)

        com_layout = QHBoxLayout()
        self.com_port_combo = QComboBox()
        for p in serial.tools.list_ports.comports():
            self.com_port_combo.addItem(p.device)
        btn_connect = QPushButton('Connect')
        btn_connect.clicked.connect(self.connect_port)
        btn_disconnect = QPushButton('Disconnect')
        btn_disconnect.clicked.connect(self.disconnect_port)
        com_layout.addWidget(QLabel('COM Port:'))
        com_layout.addWidget(self.com_port_combo)
        com_layout.addWidget(btn_connect)
        com_layout.addWidget(btn_disconnect)
        main_layout.addLayout(com_layout)

        self.status_label = QLabel('Status: DISCONNECTED')
        main_layout.addWidget(self.status_label)

        self.address_label = QLabel('Address: ---')
        self.cable_label = QLabel('0.0 m')
        self.cable_label.setStyleSheet('font-size:60px;font-weight:bold;')
        self.direction_label = QLabel('Direction: STOPPED')
        self.speed_label = QLabel('Speed: 0.000 m/s')
        self.calibration_label = QLabel('Calibration: ----')

        main_layout.addWidget(self.address_label)
        main_layout.addWidget(self.cable_label)
        main_layout.addWidget(self.direction_label)
        main_layout.addWidget(self.speed_label)
        main_layout.addWidget(self.calibration_label)

        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton('RESET (V09)'))
        buttons.addWidget(QPushButton('OFFSET (V09)'))
        main_layout.addLayout(buttons)

        self.log_window = QTextEdit()
        self.log_window.setReadOnly(True)
        self.log_window.append('CCN v0.8 GUI Started')
        main_layout.addWidget(self.log_window)

        footer = QLabel('CSA Ocean Sciences | Scott Sharpe | Microsoft Copilot')
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(footer)

        self.setLayout(main_layout)


def main():
    app = QApplication(sys.argv)
    window = CCNMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
