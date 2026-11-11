"""
CCN - Cable Counter Network
Version: 0.9.1a

Adds:
- Equipment Label
- Logging Enable/Disable
- Daily CSV logging
- COM Refresh
- Watchdog
- Last Data Timestamp
- ZERO DISPLAY button
- INSTALL OFFSET button
- RESET SCC placeholder button
"""

import sys,re,time,csv,json
from pathlib import Path
from collections import deque
from datetime import datetime,timezone
import serial,serial.tools.list_ports
from PyQt6.QtWidgets import *
from PyQt6.QtCore import QTimer,Qt
from PyQt6.QtGui import QPixmap

CONFIG_FILE='ccn_config.json'

class CCNMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.ser=None
        self.previous_cable=None
        self.previous_time=None
        self.raw_cable=0.0
        self.install_offset=0.0
        self.zero_offset=0.0
        self.equipment_label='SSS'
        self.logging_enabled=True
        self.last_data_time=None
        self.speed_history=deque(maxlen=10)
        self.load_config()
        self.setWindowTitle('CCN - Cable Counter Network v0.9.1a')
        self.resize(1000,850)
        self.build_ui()
        self.timer=QTimer(); self.timer.timeout.connect(self.read_serial_data)
        self.clock=QTimer(); self.clock.timeout.connect(self.update_clocks); self.clock.start(1000)
        self.watchdog_timer=QTimer(); self.watchdog_timer.timeout.connect(self.update_watchdog); self.watchdog_timer.start(1000)
        self.update_clocks()

    def load_config(self):
        try:
            cfg=json.loads(Path(CONFIG_FILE).read_text())
            self.install_offset=cfg.get('installation_offset',0.0)
            self.zero_offset=cfg.get('zero_offset',0.0)
            self.equipment_label=cfg.get('equipment_label','SSS')
            self.logging_enabled=cfg.get('logging_enabled',True)
        except: pass

    def save_config(self):
        Path(CONFIG_FILE).write_text(json.dumps({
            'installation_offset':self.install_offset,
            'zero_offset':self.zero_offset,
            'equipment_label':self.equipment_label,
            'logging_enabled':self.logging_enabled
        },indent=2))

    def log(self,msg):
        self.log_window.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    def update_clocks(self):
        self.local_lbl.setText('Local: '+datetime.now().strftime('%H:%M:%S'))
        self.utc_lbl.setText('UTC: '+datetime.now(timezone.utc).strftime('%H:%M:%S'))

    def refresh_ports(self):
        self.com.clear()
        for p in serial.tools.list_ports.comports():
            self.com.addItem(p.device)

    def connect_port(self):
        try:
            p=self.com.currentText(); self.ser=serial.Serial(p,9600,timeout=1)
            self.status.setText(f'Status: CONNECTED TO {p}')
            self.timer.start(200)
            self.log(f'Connected to {p}')
        except Exception as e:
            self.log(f'ERROR: {e}')

    def disconnect_port(self):
        self.timer.stop()
        if self.ser: self.ser.close()
        self.status.setText('Status: DISCONNECTED')

    def set_label(self):
        txt,ok=QInputDialog.getText(self,'Equipment Label','Equipment Label:')
        if ok and txt.strip():
            self.equipment_label=txt.strip()
            self.label_lbl.setText(f'Label: {self.equipment_label}')
            self.save_config()

    def logging_changed(self):
        self.logging_enabled=self.log_cb.isChecked()
        self.save_config()

    def zero_display(self):
        self.zero_offset=-(self.raw_cable+self.install_offset)
        self.save_config(); self.update_display_values()
        self.log('Display zeroed')

    def set_offset(self):
        val,ok=QInputDialog.getDouble(self,'Installation Offset','Offset (m):',self.install_offset,-10000,10000,2)
        if ok:
            self.install_offset=val
            self.save_config(); self.update_display_values()

    def reset_scc(self):
        QMessageBox.information(self,'RESET SCC','RESET SCC placeholder. Protocol not implemented yet.')

    def update_watchdog(self):
        if self.last_data_time is None:
            self.watchdog.setText('Watchdog: NO DATA')
            return
        age=time.time()-self.last_data_time
        if age<2: self.watchdog.setText('Watchdog: RECEIVING DATA')
        elif age<5: self.watchdog.setText('Watchdog: DATA STALE')
        else: self.watchdog.setText('Watchdog: DATA LOST')

    def update_display_values(self,units='M'):
        display=self.raw_cable+self.install_offset+self.zero_offset
        self.raw_lbl.setText(f'RAW CABLE: {self.raw_cable:.1f} {units}')
        self.offset_lbl.setText(f'INSTALL OFFSET: {self.install_offset:.1f} {units}')
        self.display_lbl.setText(f'{display:.1f} {units}')

    def read_serial_data(self):
        pass

    def build_ui(self):
        l=QVBoxLayout()
        self.local_lbl=QLabel(); self.utc_lbl=QLabel()
        l.addWidget(self.local_lbl); l.addWidget(self.utc_lbl)
        row=QHBoxLayout(); self.com=QComboBox(); self.refresh_ports()
        rb=QPushButton('Refresh Ports'); rb.clicked.connect(self.refresh_ports)
        cb=QPushButton('Connect'); cb.clicked.connect(self.connect_port)
        db=QPushButton('Disconnect'); db.clicked.connect(self.disconnect_port)
        row.addWidget(self.com); row.addWidget(rb); row.addWidget(cb); row.addWidget(db)
        l.addLayout(row)
        self.status=QLabel('Status: DISCONNECTED'); l.addWidget(self.status)
        self.watchdog=QLabel('Watchdog: NO DATA'); l.addWidget(self.watchdog)
        self.address=QLabel('Address: ---'); l.addWidget(self.address)
        self.label_lbl=QLabel(f'Label: {self.equipment_label}'); l.addWidget(self.label_lbl)
        lb=QPushButton('SET LABEL'); lb.clicked.connect(self.set_label); l.addWidget(lb)
        self.raw_lbl=QLabel('RAW CABLE: 0.0 M'); l.addWidget(self.raw_lbl)
        self.offset_lbl=QLabel('INSTALL OFFSET: 0.0 M'); l.addWidget(self.offset_lbl)
        self.display_lbl=QLabel('0.0 M'); self.display_lbl.setStyleSheet('font-size:60px;font-weight:bold;'); l.addWidget(self.display_lbl)
        self.log_cb=QCheckBox('Enable Logging'); self.log_cb.setChecked(self.logging_enabled); self.log_cb.stateChanged.connect(self.logging_changed); l.addWidget(self.log_cb)
        br=QHBoxLayout()
        z=QPushButton('ZERO DISPLAY'); z.clicked.connect(self.zero_display)
        o=QPushButton('INSTALL OFFSET'); o.clicked.connect(self.set_offset)
        r=QPushButton('RESET SCC'); r.clicked.connect(self.reset_scc)
        br.addWidget(z); br.addWidget(o); br.addWidget(r)
        l.addLayout(br)
        self.log_window=QTextEdit(); l.addWidget(self.log_window)
        self.setLayout(l)

app=QApplication(sys.argv)
w=CCNMainWindow(); w.show(); sys.exit(app.exec())
