
"""
CCN - Cable Counter Network
Version: 0.9

New in V09
- Raw Cable Display
- Display Cable Display
- Installation Offset
- Zero Display button
- Set Offset button
- Config File (ccn_config.json)
- Enhanced CSV logging
- RESET SCC placeholder
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
        self.speed_history=deque(maxlen=10)
        self.load_config()
        self.setWindowTitle('CCN - Cable Counter Network v0.9')
        self.resize(1000,850)
        self.build_ui()
        self.timer=QTimer(); self.timer.timeout.connect(self.read_serial_data)
        self.clock=QTimer(); self.clock.timeout.connect(self.update_clocks); self.clock.start(1000)
        self.update_clocks()

    def load_config(self):
        try:
            cfg=json.loads(Path(CONFIG_FILE).read_text())
            self.install_offset=cfg.get('installation_offset',0.0)
            self.zero_offset=cfg.get('zero_offset',0.0)
        except: pass

    def save_config(self):
        Path(CONFIG_FILE).write_text(json.dumps({
            'installation_offset':self.install_offset,
            'zero_offset':self.zero_offset
        },indent=2))

    def log(self,msg):
        self.log_window.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    def update_clocks(self):
        self.local_lbl.setText('Local: '+datetime.now().strftime('%H:%M:%S'))
        self.utc_lbl.setText('UTC: '+datetime.now(timezone.utc).strftime('%H:%M:%S'))

    def connect_port(self):
        try:
            p=self.com.currentText(); self.ser=serial.Serial(p,9600,timeout=1)
            self.log(f'Connected to {p}')
            self.status.setText(f'Status: CONNECTED TO {p}')
            self.timer.start(200)
        except Exception as e:
            self.log(f'ERROR: {e}')

    def disconnect_port(self):
        self.timer.stop()
        if self.ser: self.ser.close()
        self.log('Disconnected')

    def zero_display(self):
        self.zero_offset=-(self.raw_cable+self.install_offset)
        self.save_config(); self.update_display_values()
        self.log('Display zeroed')

    def set_offset(self):
        val,ok=QInputDialog.getDouble(self,'Installation Offset','Offset (m):',self.install_offset,-10000,10000,2)
        if ok:
            self.install_offset=val; self.save_config(); self.update_display_values(); self.log(f'Offset set to {val}')

    def read_serial_data(self):
        if not self.ser: return
        if self.ser.in_waiting:
            line=self.ser.readline().decode('utf-8',errors='ignore').strip()
            m=re.match(r'\$CC([A-D])([\d\.]+)([MF])([+-]\d{4})',line)
            if not m: return
            addr,cable,units,cal=m.group(1),float(m.group(2)),m.group(3),m.group(4)
            self.raw_cable=cable
            speed=0.0; direction='STOPPED'; now=time.time()
            if self.previous_cable is not None:
                dc=cable-self.previous_cable; dt=now-self.previous_time
                if dt>0:
                    self.speed_history.append(abs(dc/dt)); speed=sum(self.speed_history)/len(self.speed_history)
                if dc>0.01: direction='PAYING OUT'
                elif dc<-0.01: direction='HAULING IN'
            self.previous_cable=cable; self.previous_time=now
            self.address.setText(f'Address: {addr}')
            self.direction.setText(f'Direction: {direction}')
            self.speed.setText(f'Speed: {speed:.3f} {units}/s')
            self.cal.setText(f'Calibration: {cal}')
            self.update_display_values(units)

    def update_display_values(self, units='M'):
        display=self.raw_cable+self.install_offset+self.zero_offset
        self.raw_lbl.setText(f'RAW CABLE: {self.raw_cable:.1f} {units}')
        self.offset_lbl.setText(f'INSTALL OFFSET: {self.install_offset:.1f} {units}')
        self.display_lbl.setText(f'{display:.1f} {units}')

    def build_ui(self):
        l=QVBoxLayout()
        logo=QLabel(); pix=QPixmap('CSA_Logo.png')
        if not pix.isNull(): logo.setPixmap(pix.scaledToHeight(90)); logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(logo)
        title=QLabel('Cable Counter Network v0.9'); title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(title)
        self.local_lbl=QLabel(); self.utc_lbl=QLabel(); l.addWidget(self.local_lbl); l.addWidget(self.utc_lbl)
        row=QHBoxLayout(); self.com=QComboBox();
        [self.com.addItem(p.device) for p in serial.tools.list_ports.comports()]
        b=QPushButton('Connect'); b.clicked.connect(self.connect_port)
        d=QPushButton('Disconnect'); d.clicked.connect(self.disconnect_port)
        row.addWidget(self.com); row.addWidget(b); row.addWidget(d); l.addLayout(row)
        self.status=QLabel('Status: DISCONNECTED'); l.addWidget(self.status)
        self.address=QLabel('Address: ---'); l.addWidget(self.address)
        self.raw_lbl=QLabel('RAW CABLE: 0.0 M'); l.addWidget(self.raw_lbl)
        self.offset_lbl=QLabel(f'INSTALL OFFSET: {self.install_offset:.1f} M'); l.addWidget(self.offset_lbl)
        self.display_lbl=QLabel('0.0 M'); self.display_lbl.setStyleSheet('font-size:60px;font-weight:bold;'); l.addWidget(self.display_lbl)
        self.direction=QLabel('Direction: STOPPED'); self.speed=QLabel('Speed: 0.000'); self.cal=QLabel('Calibration: ----')
        l.addWidget(self.direction); l.addWidget(self.speed); l.addWidget(self.cal)
        br=QHBoxLayout(); z=QPushButton('ZERO DISPLAY'); z.clicked.connect(self.zero_display); o=QPushButton('SET OFFSET'); o.clicked.connect(self.set_offset); r=QPushButton('RESET SCC (V10)')
        br.addWidget(z); br.addWidget(o); br.addWidget(r); l.addLayout(br)
        self.log_window=QTextEdit(); self.log_window.setReadOnly(True); l.addWidget(self.log_window)
        l.addWidget(QLabel('CSA Ocean Sciences | Scott Sharpe | Microsoft Copilot'))
        self.setLayout(l)

app=QApplication(sys.argv)
w=CCNMainWindow(); w.show(); sys.exit(app.exec())
