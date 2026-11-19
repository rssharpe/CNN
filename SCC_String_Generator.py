import re
import sys
import time

import serial
import serial.tools.list_ports
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def format_scc_line(address, cable, units, calibration):
    if address not in ('A', 'B', 'C', 'D'):
        raise ValueError('Address must be A, B, C, or D.')
    if units not in ('M', 'F'):
        raise ValueError('Units must be M or F.')
    if not re.fullmatch(r'[+-]\d{4}', calibration):
        raise ValueError('Calibration must contain a sign and four digits.')
    if not 0 <= cable <= 99999.9:
        raise ValueError('Cable value must be between 0 and 99999.9.')
    return f'$CC{address}{cable:07.1f}{units}{calibration}\r\n'


class SCCStringGenerator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.serial_port = None
        self.last_sent_at = None

        self.setWindowTitle('SCC String Generator - Serial Test Tool')
        self.resize(640, 520)
        self.build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.send_next_line)
        self.interval.valueChanged.connect(self.update_timer_interval)

    def build_ui(self):
        central = QWidget(self)
        layout = QVBoxLayout(central)
        form = QFormLayout()

        self.port = QComboBox()
        self.port.setEditable(True)
        self.refresh_button = QPushButton('Refresh Ports')
        port_row = QHBoxLayout()
        port_row.addWidget(self.port, 1)
        port_row.addWidget(self.refresh_button)
        port_widget = QWidget()
        port_widget.setLayout(port_row)
        self.refresh_button.clicked.connect(self.refresh_ports)
        form.addRow('Generator COM port:', port_widget)

        self.address = QComboBox()
        self.address.addItems(['A', 'B', 'C', 'D'])
        form.addRow('SCC address:', self.address)

        self.units = QComboBox()
        self.units.addItems(['M', 'F'])
        form.addRow('Units:', self.units)

        self.calibration = QLineEdit('+0357')
        form.addRow('Calibration:', self.calibration)

        self.cable = QDoubleSpinBox()
        self.cable.setRange(0, 99999.9)
        self.cable.setDecimals(1)
        self.cable.setSingleStep(0.1)
        self.cable.setValue(0.7)
        form.addRow('Starting cable value:', self.cable)

        self.direction = QComboBox()
        self.direction.addItems(['PAYING OUT', 'HAULING IN', 'STOPPED'])
        form.addRow('Direction:', self.direction)

        self.speed = QDoubleSpinBox()
        self.speed.setRange(0, 1000)
        self.speed.setDecimals(2)
        self.speed.setSingleStep(0.1)
        self.speed.setValue(0.5)
        form.addRow('Speed (units/second):', self.speed)

        self.interval = QSpinBox()
        self.interval.setRange(100, 5000)
        self.interval.setSuffix(' ms')
        self.interval.setValue(500)
        form.addRow('Send interval:', self.interval)

        layout.addLayout(form)

        help_text = QLabel(
            'Connect the generator to one end of a virtual COM pair and CCN '
            'to the other. The generator sends at 9600 baud, 8-N-1.'
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        button_row = QHBoxLayout()
        self.start_button = QPushButton('Start Sending')
        self.stop_button = QPushButton('Stop')
        self.start_button.clicked.connect(self.start_generator)
        self.stop_button.clicked.connect(self.stop_generator)
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)
        layout.addLayout(button_row)

        self.status = QLabel('Status: Stopped')
        layout.addWidget(self.status)
        self.preview = QLabel('Last SCC line: ---')
        layout.addWidget(self.preview)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(150)
        layout.addWidget(self.output)

        self.setCentralWidget(central)
        self.refresh_ports()

    def refresh_ports(self):
        selected = self.port.currentText()
        self.port.clear()
        for port_info in serial.tools.list_ports.comports():
            self.port.addItem(port_info.device)
        if selected:
            self.port.setCurrentText(selected)

    def start_generator(self):
        port_name = self.port.currentText().strip()
        if not port_name:
            QMessageBox.warning(self, 'No COM Port', 'Select a COM port first.')
            return
        try:
            format_scc_line(
                self.address.currentText(),
                self.cable.value(),
                self.units.currentText(),
                self.calibration.text().strip()
            )
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid SCC Settings', str(exc))
            return

        try:
            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0,
                write_timeout=1
            )
        except (serial.SerialException, OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                'COM Port Error',
                f'Could not open {port_name}: {exc}'
            )
            self.serial_port = None
            return

        self.last_sent_at = time.monotonic()
        self.status.setText(f'Status: Sending on {port_name}')
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.update_timer_interval(self.interval.value())
        self.send_next_line()
        if self.serial_port is not None:
            self.timer.start()

    def update_timer_interval(self, interval_ms):
        self.timer.setInterval(interval_ms)

    def send_next_line(self):
        if self.serial_port is None:
            return

        now = time.monotonic()
        elapsed = 0 if self.last_sent_at is None else now - self.last_sent_at
        mode = self.direction.currentText()
        change = self.speed.value() * elapsed
        if mode == 'PAYING OUT':
            self.cable.setValue(self.cable.value() + change)
        elif mode == 'HAULING IN':
            self.cable.setValue(self.cable.value() - change)
        self.last_sent_at = now

        try:
            line = format_scc_line(
                self.address.currentText(),
                self.cable.value(),
                self.units.currentText(),
                self.calibration.text().strip()
            )
            self.serial_port.write(line.encode('ascii'))
        except (serial.SerialException, OSError, ValueError) as exc:
            self.stop_generator()
            QMessageBox.critical(self, 'Serial Send Error', str(exc))
            return

        self.preview.setText(f'Last SCC line: {line.strip()}')
        self.output.append(line.strip())
        if self.output.document().blockCount() > 20:
            cursor = self.output.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def stop_generator(self):
        self.timer.stop()
        if self.serial_port is not None:
            self.serial_port.close()
            self.serial_port = None
        self.last_sent_at = None
        self.status.setText('Status: Stopped')
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def closeEvent(self, event):
        self.stop_generator()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = SCCStringGenerator()
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
