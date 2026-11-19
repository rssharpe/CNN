"""
CCN - Cable Counter Network
Version: 10.0 DEV18

DEV18
- Menu bar
- Light and dark themes
- Adjustable cable display size
- Direction-specific colors
"""

import sys,re,time,csv,json
from pathlib import Path
from collections import deque
from datetime import datetime,timezone

import serial,serial.tools.list_ports
from PyQt6.QtWidgets import *
from PyQt6.QtCore import QTimer,Qt
from PyQt6.QtGui import QAction,QActionGroup,QPixmap

CONFIG_FILE='ccn_config.json'
DEFAULT_DISPLAY_FONT_SIZE=72
MIN_DISPLAY_FONT_SIZE=48
MAX_DISPLAY_FONT_SIZE=120
DISPLAY_FONT_STEP=8

THEME_PALETTES={
    'dark':{
        'window':'#0B1421',
        'panel':'#132235',
        'text':'#E7EDF5',
        'border':'#314760',
        'button':'#1B3047',
        'hover':'#284563',
        'accent':'#57D4E8',
        'display':'#F5F8FC',
        'direction':{
            'PAYING OUT':'#4DDBA2',
            'HAULING IN':'#FFC857',
            'STOPPED':'#ACBDCF'
        },
        'watchdog':{
            'NO DATA':'#FF6B6B',
            'RECEIVING DATA':'#38C98A',
            'DATA STALE':'#F4B942',
            'DATA LOST':'#FF6B6B'
        }
    },
    'light':{
        'window':'#F3F6F8',
        'panel':'#FFFFFF',
        'text':'#162432',
        'border':'#C7D1DB',
        'button':'#E8EEF3',
        'hover':'#D9E4EC',
        'accent':'#006B80',
        'display':'#101820',
        'direction':{
            'PAYING OUT':'#087A4B',
            'HAULING IN':'#9A5A00',
            'STOPPED':'#536474'
        },
        'watchdog':{
            'NO DATA':'#B42318',
            'RECEIVING DATA':'#087A4B',
            'DATA STALE':'#9A5A00',
            'DATA LOST':'#B42318'
        }
    }
}

class CCNMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ser=None
        self.raw_record_file=None
        self.previous_cable=None
        self.previous_time=None
        self.raw_cable=0.0
        self.install_offset=0.0
        self.zero_offset=0.0
        self.equipment_label='SSS'
        self.logging_enabled=True
        self.last_data_time=None
        self.speed_history=deque(maxlen=10)
        self.current_direction='STOPPED'
        self.theme='dark'
        self.display_font_size=DEFAULT_DISPLAY_FONT_SIZE

        self.playback_lines=[]
        self.playback_index=0
        self.playback_file=''
        self.playback_timer=QTimer()
        self.playback_timer.timeout.connect(self.playback_tick)

        self.load_config()

        self.setWindowTitle('CCN - Cable Counter Network V10_0_DEV18')
        self.resize(1000,900)
        self.build_ui()
        self.build_menus()
        self.apply_theme()

        self.timer=QTimer()
        self.timer.timeout.connect(self.read_serial_data)

        self.clock=QTimer()
        self.clock.timeout.connect(self.update_clocks)
        self.clock.start(1000)

        self.watchdog_timer=QTimer()
        self.watchdog_timer.timeout.connect(self.update_watchdog)
        self.watchdog_timer.start(1000)

        self.update_clocks()

    def load_config(self):
        try:
            cfg=json.loads(Path(CONFIG_FILE).read_text())
            self.install_offset=cfg.get('installation_offset',0.0)
            self.zero_offset=cfg.get('zero_offset',0.0)
            self.equipment_label=cfg.get('equipment_label','SSS')
            self.logging_enabled=cfg.get('logging_enabled',True)
            saved_theme=cfg.get('theme','dark')
            self.theme=saved_theme if saved_theme in THEME_PALETTES else 'dark'
            saved_font_size=cfg.get('display_font_size',DEFAULT_DISPLAY_FONT_SIZE)
            if isinstance(saved_font_size,int) and MIN_DISPLAY_FONT_SIZE <= saved_font_size <= MAX_DISPLAY_FONT_SIZE:
                self.display_font_size=saved_font_size
        except Exception:
            pass

    def save_config(self):
        Path(CONFIG_FILE).write_text(json.dumps({
            'installation_offset':self.install_offset,
            'zero_offset':self.zero_offset,
            'equipment_label':self.equipment_label,
            'logging_enabled':self.logging_enabled,
            'theme':self.theme,
            'display_font_size':self.display_font_size
        },indent=2))

    def build_menus(self):
        file_menu=self.menuBar().addMenu('&File')
        exit_action=QAction('Exit',self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        connection_menu=self.menuBar().addMenu('&Connection')
        refresh_action=QAction('Refresh Ports',self)
        refresh_action.triggered.connect(self.refresh_ports)
        connection_menu.addAction(refresh_action)
        connection_menu.addSeparator()
        connect_action=QAction('Connect',self)
        connect_action.triggered.connect(self.connect_port)
        connection_menu.addAction(connect_action)
        disconnect_action=QAction('Disconnect',self)
        disconnect_action.triggered.connect(self.disconnect_port)
        connection_menu.addAction(disconnect_action)

        playback_menu=self.menuBar().addMenu('&Playback')
        browse_action=QAction('Browse Playback File...',self)
        browse_action.triggered.connect(
            lambda checked=False: self.browse_playback_file()
        )
        playback_menu.addAction(browse_action)
        playback_menu.addSeparator()
        play_action=QAction('Play Playback',self)
        play_action.triggered.connect(lambda checked=False: self.start_playback())
        playback_menu.addAction(play_action)
        stop_action=QAction('Stop Playback',self)
        stop_action.triggered.connect(self.stop_playback)
        playback_menu.addAction(stop_action)

        view_menu=self.menuBar().addMenu('&View')
        appearance_menu=view_menu.addMenu('Appearance')
        theme_group=QActionGroup(self)
        theme_group.setExclusive(True)
        self.theme_actions={}
        for theme,title in (('dark','Dark / Night'),('light','Light / Day')):
            action=QAction(title,self)
            action.setCheckable(True)
            theme_group.addAction(action)
            appearance_menu.addAction(action)
            action.triggered.connect(
                lambda checked=False, selected_theme=theme: self.set_theme(selected_theme)
            )
            self.theme_actions[theme]=action
        self.theme_actions[self.theme].setChecked(True)

        size_menu=view_menu.addMenu('Cable Display Size')
        increase_action=QAction('Increase',self)
        increase_action.triggered.connect(
            lambda: self.adjust_display_font(DISPLAY_FONT_STEP)
        )
        size_menu.addAction(increase_action)
        decrease_action=QAction('Decrease',self)
        decrease_action.triggered.connect(
            lambda: self.adjust_display_font(-DISPLAY_FONT_STEP)
        )
        size_menu.addAction(decrease_action)
        size_menu.addSeparator()
        reset_size_action=QAction('Reset to Default',self)
        reset_size_action.triggered.connect(self.reset_display_font)
        size_menu.addAction(reset_size_action)

        help_menu=self.menuBar().addMenu('&Help')
        about_action=QAction('About CCN',self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def set_theme(self,theme):
        if theme not in THEME_PALETTES:
            return
        self.theme=theme
        self.theme_actions[theme].setChecked(True)
        self.apply_theme()
        self.save_config()
        self.log(f'Display theme set to {theme}')

    def apply_theme(self):
        colors=THEME_PALETTES[self.theme]
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {colors['window']};
                color: {colors['text']};
            }}
            QLabel {{
                background-color: transparent;
            }}
            QLineEdit, QComboBox, QTextEdit {{
                background-color: {colors['panel']};
                color: {colors['text']};
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 4px;
                selection-background-color: {colors['accent']};
            }}
            QPushButton {{
                background-color: {colors['button']};
                color: {colors['text']};
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 5px 8px;
            }}
            QPushButton:hover {{
                background-color: {colors['hover']};
                border-color: {colors['accent']};
            }}
            QMenuBar {{
                background-color: {colors['panel']};
                color: {colors['text']};
            }}
            QMenuBar::item:selected, QMenu::item:selected {{
                background-color: {colors['hover']};
            }}
            QMenu {{
                background-color: {colors['panel']};
                color: {colors['text']};
                border: 1px solid {colors['border']};
            }}
        """)
        self.apply_display_font()
        self.update_watchdog()

    def apply_display_font(self):
        display_color=THEME_PALETTES[self.theme]['display']
        self.display_lbl.setStyleSheet(
            f'font-size:{self.display_font_size}px;font-weight:bold;color:{display_color};'
        )
        self.update_direction_style()

    def adjust_display_font(self,change):
        new_size=max(
            MIN_DISPLAY_FONT_SIZE,
            min(MAX_DISPLAY_FONT_SIZE,self.display_font_size+change)
        )
        if new_size != self.display_font_size:
            self.display_font_size=new_size
            self.apply_display_font()
            self.save_config()

    def reset_display_font(self):
        if self.display_font_size != DEFAULT_DISPLAY_FONT_SIZE:
            self.display_font_size=DEFAULT_DISPLAY_FONT_SIZE
            self.apply_display_font()
            self.save_config()

    def update_direction_style(self):
        colors=THEME_PALETTES[self.theme]['direction']
        color=colors.get(self.current_direction,colors['STOPPED'])
        font_size=max(15,self.display_font_size//4)
        self.direction.setStyleSheet(
            f'font-size:{font_size}px;font-weight:bold;color:{color};'
        )

    def show_about(self):
        QMessageBox.about(
            self,
            'About CCN',
            'Cable Counter Network V10_0_DEV18\n'
            'Real-time SCC data and playback'
        )

    def log(self,msg):
        self.log_window.append(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}')

    def update_clocks(self):
        self.local_lbl.setText('Local: '+datetime.now().strftime('%H:%M:%S'))
        self.utc_lbl.setText('UTC: '+datetime.now(timezone.utc).strftime('%H:%M:%S'))

    def refresh_ports(self):
        self.com.clear()
        for p in serial.tools.list_ports.comports():
            self.com.addItem(p.device)

    def connect_port(self):
        try:
            p=self.com.currentText()
            self.ser=serial.Serial(p,9600,timeout=1)
            self.timer.start(200)
            self.status.setText(f'Status: CONNECTED TO {p}')
            self.log(f'Connected to {p}')
        except Exception as e:
            self.log(f'ERROR: {e}')

    def disconnect_port(self):
        self.timer.stop()
        if self.ser:
            self.ser.close()
        self.status.setText('Status: DISCONNECTED')
        self.log('Disconnected')

    def set_label(self):
        text,ok=QInputDialog.getText(self,'Equipment Label','Label:')
        if ok and text.strip():
            self.equipment_label=text.strip()
            self.label_lbl.setText(f'Label: {self.equipment_label}')
            self.save_config()

    def logging_changed(self):
        self.logging_enabled=self.log_cb.isChecked()
        self.save_config()

    def zero_display(self):
        self.zero_offset=-(self.raw_cable+self.install_offset)
        self.save_config()
        self.update_display_values()

    def set_offset(self):
        val,ok=QInputDialog.getDouble(self,'Installation Offset','Offset (m):',self.install_offset,-10000,10000,2)
        if ok:
            self.install_offset=val
            self.save_config()
            self.update_display_values()


    def reset_scc(self):
        if not self.ser:
            QMessageBox.warning(self,'RESET SCC','Not connected to SCC')
            return
        value, ok = QInputDialog.getInt(self,'RESET SCC','Reset Value:',0,0,99999)
        if not ok:
            return
        cmd = '!!RT{:05d}\r\n'.format(value)
        try:
            self.ser.write(cmd.encode('ascii'))
            self.log('Sent SCC Reset: ' + cmd.strip())
        except Exception as e:
            QMessageBox.critical(self,'RESET SCC',str(e))

    def update_watchdog(self):
        if self.last_data_time is None:
            state='NO DATA'
        else:
            age=time.time()-self.last_data_time
            if age<2:
                state='RECEIVING DATA'
            elif age<5:
                state='DATA STALE'
            else:
                state='DATA LOST'
        color=THEME_PALETTES[self.theme]['watchdog'][state]
        self.watchdog.setText(f'Watchdog: {state}')
        self.watchdog.setStyleSheet(f'color:{color};font-weight:bold;')

    def write_csv(self,addr,direction,speed,units):
        
        if not self.logging_enabled:
            return
        Path('logs').mkdir(exist_ok=True)
        fn=Path('logs')/f"ccn_{datetime.now().strftime('%Y-%m-%d')}.csv"
        exists=fn.exists()
        display=self.raw_cable+self.install_offset+self.zero_offset
        with open(fn,'a',newline='') as f:
            w=csv.writer(f)
            if not exists:
                w.writerow(['Timestamp','Address','Label','RawCable','DisplayCable','Offset','Direction','Speed','Units'])
            w.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'),addr,self.equipment_label,self.raw_cable,display,self.install_offset,direction,speed,units])


    def process_scc_line(self, line):

        m = re.match(
            r'\$CC([A-D])([\d\.]+)([MF])([+-]\d{4})',
            line
        )

        if not m:
            return False

        addr = m.group(1)
        cable = float(m.group(2))
        units = m.group(3)
        cal = m.group(4)

        self.raw_cable = cable
        self.last_data_time = time.time()

        self.last_data_lbl.setText(
            'Last Data: ' + datetime.now().strftime('%H:%M:%S')
        )

        speed = 0.0
        direction = 'STOPPED'

        now = time.time()

        if self.previous_cable is not None:

            dc = cable - self.previous_cable
            dt = now - self.previous_time

            if dt > 0:
                self.speed_history.append(abs(dc / dt))
                speed = sum(self.speed_history) / len(self.speed_history)

            if dc > 0.01:
                direction = 'PAYING OUT'
            elif dc < -0.01:
                direction = 'HAULING IN'

        self.previous_cable = cable
        self.previous_time = now

        self.address.setText(f'Address: {addr}')
        self.current_direction=direction
        self.direction.setText(f'Direction: {direction}')
        self.update_direction_style()
        self.speed.setText(f'Speed: {speed:.3f} {units}/s')
        self.cal.setText(f'Calibration: {cal}')

        self.update_display_values(units)

        self.write_csv(addr, direction, speed, units)

        return True

    def read_serial_data(self):
        if not self.ser or not self.ser.in_waiting:
            return
        line=self.ser.readline().decode('utf-8',errors='ignore').strip()
        self.record_raw_string(line)
        self.process_scc_line(line)

    def browse_playback_file(self):
        filename,_=QFileDialog.getOpenFileName(
            self,
            'Select Playback File',
            'recordings',
            'Text Files (*.txt *.log *.csv);;All Files (*)'
        )
        if filename:
            self.playback_file=filename
            self.playback_file_edit.setText(filename)
            self.log(f'Playback file selected: {filename}')
        return self.playback_file

    def start_playback(self, filename=None):
        try:
            if filename is None:
                filename=self.playback_file_edit.text().strip()
            if filename:
                self.playback_file=filename
            if not self.playback_file:
                return False
            self.playback_lines=Path(self.playback_file).read_text(encoding='utf-8',errors='ignore').splitlines()
            self.playback_index=0
            self.playback_timer.start(200)
            self.log(f'Playback started: {self.playback_file}')
            return True
        except Exception as e:
            self.log(f'PLAYBACK ERROR: {e}')
            return False

    def stop_playback(self):
        self.playback_timer.stop()
        self.playback_index=0
        self.log('Playback stopped')

    def playback_tick(self):
        if self.playback_index >= len(self.playback_lines):
            self.stop_playback()
            return
        line=self.playback_lines[self.playback_index].strip()
        self.playback_index += 1
        if line:
            self.process_scc_line(line)

    def record_raw_string(self, line):
        try:
            rec_dir = Path(__file__).resolve().parent / 'recordings'
            rec_dir.mkdir(exist_ok=True)
            if self.raw_record_file is None:
                fname = rec_dir / f"scc_raw_{datetime.now().strftime('%Y-%m-%d')}.txt"
                self.raw_record_file = open(fname,'a',encoding='utf-8')
            self.raw_record_file.write(line + '\n')
            self.raw_record_file.flush()
        except Exception as e:
            self.log(f'RAW RECORD ERROR: {e}')

    def update_display_values(self,units='M'):
        display=self.raw_cable+self.install_offset+self.zero_offset
        self.raw_lbl.setText(f'RAW CABLE: {self.raw_cable:.1f} {units}')
        self.offset_lbl.setText(f'INSTALL OFFSET: {self.install_offset:.1f} {units}')
        self.display_lbl.setText(f'{display:.1f} {units}')

    def build_ui(self):
        l=QVBoxLayout()
        logo=QLabel()
        pix=QPixmap('CSA_LOGO.png')
        if not pix.isNull():
            logo.setPixmap(pix.scaledToHeight(120))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.addWidget(logo)
        self.local_lbl=QLabel(); self.utc_lbl=QLabel()
        l.addWidget(self.local_lbl); l.addWidget(self.utc_lbl)
        row=QHBoxLayout()
        self.com=QComboBox()
        self.refresh_ports()
        rb=QPushButton('Refresh Ports'); rb.clicked.connect(self.refresh_ports)
        cb=QPushButton('Connect'); cb.clicked.connect(self.connect_port)
        db=QPushButton('Disconnect'); db.clicked.connect(self.disconnect_port)
        row.addWidget(self.com); row.addWidget(rb); row.addWidget(cb); row.addWidget(db)
        l.addLayout(row)
        play_row=QHBoxLayout()

        play_btn=QPushButton('Play Playback')
        stop_btn=QPushButton('Stop Playback')

        play_btn.clicked.connect(lambda checked=False: self.start_playback())
        stop_btn.clicked.connect(self.stop_playback)

        play_row.addWidget(play_btn)
        play_row.addWidget(stop_btn)

        l.addLayout(play_row)
        self.status=QLabel('Status: DISCONNECTED'); l.addWidget(self.status)

        pb_row=QHBoxLayout()
        pb_lbl=QLabel('Playback File:')
        self.playback_file_edit=QLineEdit()
        pb_btn=QPushButton('Browse')

        pb_btn.clicked.connect(lambda checked=False: self.browse_playback_file())
        pb_row.addWidget(pb_lbl)
        pb_row.addWidget(self.playback_file_edit)
        pb_row.addWidget(pb_btn)
        l.addLayout(pb_row)

        self.watchdog=QLabel('Watchdog: NO DATA'); l.addWidget(self.watchdog)
        self.last_data_lbl=QLabel('Last Data: ---'); l.addWidget(self.last_data_lbl)
        self.address=QLabel('Address: ---'); l.addWidget(self.address)
        self.label_lbl=QLabel(f'Label: {self.equipment_label}'); l.addWidget(self.label_lbl)
        lb=QPushButton('Set Label'); lb.clicked.connect(self.set_label); l.addWidget(lb)
        self.raw_lbl=QLabel('RAW CABLE: 0.0 M'); l.addWidget(self.raw_lbl)
        self.offset_lbl=QLabel('INSTALL OFFSET: 0.0 M'); l.addWidget(self.offset_lbl)
        self.display_lbl=QLabel('0.0 M'); self.display_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); l.addWidget(self.display_lbl)
        self.direction=QLabel('Direction: STOPPED'); l.addWidget(self.direction)
        self.speed=QLabel('Speed: 0.000'); l.addWidget(self.speed)
        self.cal=QLabel('Calibration: ----'); l.addWidget(self.cal)
        self.log_cb=QCheckBox('Enable Logging'); self.log_cb.setChecked(self.logging_enabled); self.log_cb.stateChanged.connect(self.logging_changed); l.addWidget(self.log_cb)
        br=QHBoxLayout()
        z=QPushButton('ZERO DISPLAY'); z.clicked.connect(self.zero_display)
        o=QPushButton('INSTALL OFFSET'); o.clicked.connect(self.set_offset)
        r=QPushButton('RESET SCC'); r.clicked.connect(self.reset_scc)
        br.addWidget(z); br.addWidget(o); br.addWidget(r)
        l.addLayout(br)
        
        self.log_window=QTextEdit(); l.addWidget(self.log_window)

        footer = QLabel('CSA Ocean Sciences Inc.\nScott Sharpe / Copilot')
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(footer)

        central_widget=QWidget(self)
        central_widget.setLayout(l)
        self.setCentralWidget(central_widget)


app=QApplication(sys.argv)
w=CCNMainWindow()
w.show()
sys.exit(app.exec())
