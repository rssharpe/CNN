"""
CCN - Cable Counter Network
Version: 10.0 DEV20

DEV20
- Independent display and settings per counter source
- Multiple single-counter playback files
- Two- and three-counter simulation
- Configurable simulation ranges per address
- Per-counter readout colors and target alerts
- Draggable counter-card resizing
- Up to three simultaneous live COM sources
- TCP server with view-only remote clients
"""

import sys,os,re,time,csv,json,math
from pathlib import Path
from collections import deque
from datetime import datetime,timezone

import serial,serial.tools.list_ports
from PyQt6.QtWidgets import *
from PyQt6.QtCore import QTimer,Qt
from PyQt6.QtGui import QAction,QActionGroup,QPixmap,QColor,QPainter,QPen,QPalette
from PyQt6.QtNetwork import QHostAddress,QTcpServer,QTcpSocket

# User-configurable defaults and limits shared by the UI and data handlers.
if getattr(sys,'frozen',False):
    local_app_data=os.environ.get(
        'LOCALAPPDATA',str(Path.home()/'AppData'/'Local')
    )
    DATA_DIR=Path(local_app_data)/'CSA'/'Cable Counter Display V1'
else:
    DATA_DIR=Path.cwd()
CONFIG_FILE=DATA_DIR/'ccn_config.json'
LOG_DIR=DATA_DIR/'logs'
RECORDINGS_DIR=DATA_DIR/'recordings'
MANUAL_FILE='CCN_V10_0_DEV20_User_Manual.md'
DEFAULT_DISPLAY_FONT_SIZE=72
MIN_DISPLAY_FONT_SIZE=48
MAX_DISPLAY_FONT_SIZE=120
DISPLAY_FONT_STEP=8
CARD_MIN_WIDTH=360
CARD_MIN_HEIGHT=360
CARD_MAX_WIDTH=2400
CARD_MAX_HEIGHT=1800
MAX_COM_PORTS=3
MAX_SERIAL_BUFFER_BYTES=4096
DEFAULT_TCP_PORT=8765
MAX_TCP_CLIENTS=8
MAX_TCP_LINE_BYTES=65536
TCP_CONNECT_TIMEOUT_MS=8000
DEFAULT_SIMULATION_SETTINGS={
    'A':{'start':0.0,'end':50.0},
    'B':{'start':50.0,'end':100.0},
    'C':{'start':125.0,'end':200.0}
}

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


# Small custom widget that lets a user drag-resize one counter card.
class CardResizeHandle(QWidget):
    def __init__(self,card,resized_callback):
        super().__init__(card)
        self.card=card
        self.resized_callback=resized_callback
        self.drag_origin=None
        self.start_size=None
        self.setFixedSize(20,20)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip('Drag to resize this counter card')

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.drag_origin=event.globalPosition().toPoint()
            self.start_size=self.card.size()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.drag_origin is None or self.start_size is None:
            super().mouseMoveEvent(event)
            return
        delta=event.globalPosition().toPoint()-self.drag_origin
        width=max(CARD_MIN_WIDTH,min(CARD_MAX_WIDTH,self.start_size.width()+delta.x()))
        height=max(CARD_MIN_HEIGHT,min(CARD_MAX_HEIGHT,self.start_size.height()+delta.y()))
        self.card.setFixedSize(width,height)
        event.accept()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.drag_origin is not None:
            self.drag_origin=None
            self.start_size=None
            self.resized_callback(self.card.width(),self.card.height())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid),2))
        right=self.width()-3
        bottom=self.height()-3
        for offset in (0,5,10):
            painter.drawLine(right-offset,bottom,right,bottom-offset)


# The main window owns the UI, live sources, timers, and network connections.
class CCNMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.serial_connections={}
        self.serial_buffers={}
        self.port_rows=[]
        self.network_role='local'
        self.network_server=None
        self.network_client=None
        self.network_client_ready=False
        self.network_clients={}
        self.network_client_buffer=bytearray()
        self.network_remote_prefix=''
        self.network_timeout_timer=QTimer(self)
        self.network_timeout_timer.setSingleShot(True)
        self.network_timeout_timer.setInterval(TCP_CONNECT_TIMEOUT_MS)
        self.network_timeout_timer.timeout.connect(
            self.handle_tcp_connect_timeout
        )
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
        self.source_states={}
        self.source_cards={}
        self.source_settings={}
        self.playback_sources={}
        self.simulation_count=0
        self.simulation_tick_count=0
        self.simulation_settings={
            address:values.copy()
            for address,values in DEFAULT_SIMULATION_SETTINGS.items()
        }
        self.alert_blink_on=True
        self.alert_blink_timer=QTimer(self)
        self.alert_blink_timer.setInterval(500)
        self.alert_blink_timer.timeout.connect(self.toggle_alert_blink)

        self.playback_file=''
        self.simulation_timer=QTimer(self)
        self.simulation_timer.timeout.connect(self.simulation_tick)
        self.serial_poll_timer=QTimer(self)
        self.serial_poll_timer.timeout.connect(self.read_serial_data)

        DATA_DIR.mkdir(parents=True,exist_ok=True)
        RECORDINGS_DIR.mkdir(parents=True,exist_ok=True)
        self.load_config()

        self.setWindowTitle('CCN - Cable Counter Network V10_0_DEV20')
        self.resize(1000,900)
        self.build_ui()
        self.build_menus()
        self.apply_theme()
        self.update_network_controls()

        self.clock=QTimer()
        self.clock.timeout.connect(self.update_clocks)
        self.clock.start(1000)

        self.watchdog_timer=QTimer()
        self.watchdog_timer.timeout.connect(self.update_watchdog)
        self.watchdog_timer.start(1000)

        self.update_clocks()

    # --- Saved preferences and application menus ---
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
            saved_source_settings=cfg.get('source_settings',{})
            if isinstance(saved_source_settings,dict):
                self.source_settings={
                    key:value
                    for key,value in saved_source_settings.items()
                    if isinstance(value,dict)
                }
            saved_simulation_settings=cfg.get('simulation_settings',{})
            if isinstance(saved_simulation_settings,dict):
                for address,defaults in DEFAULT_SIMULATION_SETTINGS.items():
                    saved=saved_simulation_settings.get(address,{})
                    if not isinstance(saved,dict):
                        continue
                    try:
                        start=float(saved.get('start',defaults['start']))
                        end=float(saved.get('end',defaults['end']))
                    except (TypeError,ValueError):
                        continue
                    if (
                        math.isfinite(start)
                        and math.isfinite(end)
                        and 0 <= start <= 99999.9
                        and 0 <= end <= 99999.9
                    ):
                        self.simulation_settings[address]={
                            'start':start,
                            'end':end
                        }
        except Exception:
            pass

    def save_config(self):
        Path(CONFIG_FILE).write_text(json.dumps({
            'installation_offset':self.install_offset,
            'zero_offset':self.zero_offset,
            'equipment_label':self.equipment_label,
            'logging_enabled':self.logging_enabled,
            'theme':self.theme,
            'display_font_size':self.display_font_size,
            'source_settings':self.source_settings,
            'simulation_settings':self.simulation_settings
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
        disconnect_all_action=QAction('Disconnect All Ports',self)
        disconnect_all_action.triggered.connect(self.disconnect_all_ports)
        connection_menu.addAction(disconnect_all_action)
        reset_action=QAction('Reset SCC on Connected Port...',self)
        reset_action.triggered.connect(self.reset_scc)
        connection_menu.addAction(reset_action)
        self.connection_menu=connection_menu

        playback_menu=self.menuBar().addMenu('&Playback')
        self.playback_menu=playback_menu
        browse_action=QAction('Browse Playback File...',self)
        browse_action.triggered.connect(
            lambda checked=False: self.browse_playback_file()
        )
        playback_menu.addAction(browse_action)
        add_files_action=QAction('Add Multiple Playback Files...',self)
        add_files_action.triggered.connect(
            lambda checked=False: self.add_playback_files()
        )
        playback_menu.addAction(add_files_action)
        playback_menu.addSeparator()
        play_action=QAction('Play Playback',self)
        play_action.triggered.connect(
            lambda checked=False: self.playback_start_requested()
        )
        playback_menu.addAction(play_action)
        stop_action=QAction('Stop Playback',self)
        stop_action.triggered.connect(
            lambda checked=False: self.playback_stop_requested()
        )
        playback_menu.addAction(stop_action)
        playback_menu.addSeparator()
        simulate_menu=playback_menu.addMenu('Simulated Counters')
        simulate_two_action=QAction('Start 2 Simulated Counters',self)
        simulate_two_action.triggered.connect(
            lambda checked=False: self.simulation_start_requested(2)
        )
        simulate_menu.addAction(simulate_two_action)
        simulate_three_action=QAction('Start 3 Simulated Counters',self)
        simulate_three_action.triggered.connect(
            lambda checked=False: self.simulation_start_requested(3)
        )
        simulate_menu.addAction(simulate_three_action)
        stop_simulation_action=QAction('Stop Simulation',self)
        stop_simulation_action.triggered.connect(
            lambda checked=False: self.simulation_stop_requested()
        )
        simulate_menu.addAction(stop_simulation_action)
        simulate_menu.addSeparator()
        simulation_settings_action=QAction('Simulation Settings...',self)
        simulation_settings_action.triggered.connect(
            lambda checked=False: self.configure_simulation_settings()
        )
        simulate_menu.addAction(simulation_settings_action)

        network_menu=self.menuBar().addMenu('&Network')
        self.network_menu=network_menu
        self.start_server_action=QAction('Start TCP Server...',self)
        self.start_server_action.triggered.connect(
            lambda checked=False: self.prompt_start_tcp_server()
        )
        network_menu.addAction(self.start_server_action)
        self.stop_server_action=QAction('Stop TCP Server',self)
        self.stop_server_action.triggered.connect(
            lambda checked=False: self.stop_tcp_server()
        )
        network_menu.addAction(self.stop_server_action)
        network_menu.addSeparator()
        self.connect_server_action=QAction('Connect to Server...',self)
        self.connect_server_action.triggered.connect(
            lambda checked=False: self.prompt_connect_tcp_client()
        )
        network_menu.addAction(self.connect_server_action)
        self.disconnect_server_action=QAction('Disconnect from Server',self)
        self.disconnect_server_action.triggered.connect(
            lambda checked=False: self.disconnect_tcp_client()
        )
        network_menu.addAction(self.disconnect_server_action)

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
        view_menu.addSeparator()
        reset_cards_action=QAction('Reset Counter Card Sizes',self)
        reset_cards_action.triggered.connect(self.reset_counter_card_sizes)
        view_menu.addAction(reset_cards_action)
        view_menu.addSeparator()
        self.counter_display_menu=view_menu.addMenu('Counter Displays')
        self.counter_display_menu.setEnabled(False)
        self.counter_display_actions={}
        self.live_com_action=QAction('Show Live COM Sources',self)
        self.live_com_action.setCheckable(True)
        self.live_com_action.setChecked(True)
        self.live_com_action.toggled.connect(self.live_ports_group.setVisible)
        view_menu.addAction(self.live_com_action)
        self.playback_view_action=QAction('Show Playback Source',self)
        self.playback_view_action.setCheckable(True)
        self.playback_view_action.setChecked(True)
        self.playback_view_action.toggled.connect(self.playback_group.setVisible)
        view_menu.addAction(self.playback_view_action)
        self.log_terminal_action=QAction('Show Log Terminal',self)
        self.log_terminal_action.setCheckable(True)
        self.log_terminal_action.toggled.connect(self.log_window.setVisible)
        view_menu.addAction(self.log_terminal_action)

        help_menu=self.menuBar().addMenu('&Help')
        manual_action=QAction('User Manual...',self)
        manual_action.triggered.connect(
            lambda checked=False: self.show_user_manual()
        )
        help_menu.addAction(manual_action)
        help_menu.addSeparator()
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
        checkbox_style=''
        if self.theme=='dark':
            checkbox_style=f"""
            QCheckBox::indicator:unchecked {{
                width:16px;
                height:16px;
                background-color:{colors['panel']};
                border:1px solid #9DB3C8;
                border-radius:3px;
            }}
            QCheckBox::indicator:unchecked:hover {{
                border-color:{colors['accent']};
            }}
            """
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
            QFrame#counterCard {{
                background-color: {colors['panel']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
            }}
            {checkbox_style}
        """)
        self.apply_display_font()
        self.update_watchdog()

    def apply_display_font(self):
        for key,card in self.source_cards.items():
            card['display'].setStyleSheet(
                f'font-size:{self.display_font_size}px;font-weight:bold;'
            )
            self.update_direction_style(key)
        self.refresh_alert_styles()

    def counter_alert_level(self,key):
        state=self.source_states[key]
        if not state['alert_enabled'] or state['last_data_time'] is None:
            return 'NONE'
        warning=state['alert_warning_distance']
        critical=state['alert_critical_distance']
        if warning <= 0 or critical < 0 or critical >= warning:
            return 'NONE'
        distance=abs(state['display_cable']-state['alert_target'])
        if distance <= critical:
            return 'CRITICAL'
        if distance <= warning:
            return 'WARNING'
        return 'NONE'

    def refresh_alert_styles(self):
        levels={
            key:self.counter_alert_level(key)
            for key in self.source_cards
        }
        has_critical='CRITICAL' in levels.values()
        if has_critical and not self.alert_blink_timer.isActive():
            self.alert_blink_on=True
            self.alert_blink_timer.start()
        elif not has_critical:
            self.alert_blink_timer.stop()
            self.alert_blink_on=True

        alert_colors={
            'WARNING':{
                'dark':'#FFC857',
                'light':'#9A5A00'
            },
            'CRITICAL':{
                'dark':'#FF6B6B' if self.alert_blink_on else '#FFC857',
                'light':'#B42318' if self.alert_blink_on else '#9A5A00'
            }
        }
        for key,card in self.source_cards.items():
            state=self.source_states[key]
            level=levels[key]
            if level in alert_colors:
                color=alert_colors[level][self.theme]
            else:
                color=state['display_color'] or THEME_PALETTES[self.theme]['display']
            card['display'].setStyleSheet(
                f'font-size:{self.display_font_size}px;font-weight:bold;color:{color};'
            )
            if level=='WARNING':
                card['alert'].setText('WARNING: NEAR TARGET')
                card['alert'].setStyleSheet(
                    f"color:{alert_colors['WARNING'][self.theme]};font-weight:bold;"
                )
                card['alert'].show()
            elif level=='CRITICAL':
                critical_color={
                    'dark':'#FF6B6B',
                    'light':'#B42318'
                }[self.theme]
                card['alert'].setText('CRITICAL: NEAR TARGET')
                card['alert'].setStyleSheet(
                    f'color:{critical_color};font-weight:bold;'
                )
                card['alert'].show()
            else:
                card['alert'].clear()
                card['alert'].hide()

    def toggle_alert_blink(self):
        self.alert_blink_on=not self.alert_blink_on
        self.refresh_alert_styles()

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

    def configure_counter_display(self,key):
        state=self.source_states[key]
        dialog=QDialog(self)
        dialog.setWindowTitle(f"Display and Alerts - {state['label']}")
        layout=QVBoxLayout(dialog)
        form=QFormLayout()

        selected_color=QColor(
            state['display_color'] or THEME_PALETTES[self.theme]['display']
        )
        use_theme_color=QCheckBox('Use theme default color')
        use_theme_color.setChecked(state['display_color'] is None)
        color_button=QPushButton('Choose Readout Color')
        color_preview=QLabel()
        color_preview.setMinimumSize(44,20)

        def update_color_preview():
            color_preview.setStyleSheet(
                f'background-color:{selected_color.name()};'
                'border:1px solid palette(mid);'
            )
            color_button.setEnabled(not use_theme_color.isChecked())

        def choose_readout_color():
            nonlocal selected_color
            color=QColorDialog.getColor(selected_color,dialog,'Readout Text Color')
            if color.isValid():
                selected_color=color
                update_color_preview()

        color_button.clicked.connect(choose_readout_color)
        use_theme_color.toggled.connect(lambda checked: update_color_preview())
        color_row=QHBoxLayout()
        color_row.addWidget(color_button)
        color_row.addWidget(color_preview)
        color_row.addWidget(use_theme_color)
        color_row.addStretch()
        form.addRow('Cable readout:',color_row)
        update_color_preview()

        alert_enabled=QCheckBox('Enable near-target alert')
        alert_enabled.setChecked(state['alert_enabled'])
        form.addRow('Target alert:',alert_enabled)

        target=QDoubleSpinBox()
        target.setRange(-99999.9,99999.9)
        target.setDecimals(1)
        target.setSingleStep(0.1)
        target.setSuffix(f" {state['units']}")
        target.setValue(state['alert_target'])
        form.addRow('Target reading:',target)

        warning=QDoubleSpinBox()
        warning.setRange(0,99999.9)
        warning.setDecimals(1)
        warning.setSingleStep(0.1)
        warning.setSuffix(f" {state['units']}")
        warning.setValue(state['alert_warning_distance'])
        form.addRow('Warning distance:',warning)

        critical=QDoubleSpinBox()
        critical.setRange(0,99999.9)
        critical.setDecimals(1)
        critical.setSingleStep(0.1)
        critical.setSuffix(f" {state['units']}")
        critical.setValue(state['alert_critical_distance'])
        form.addRow('Critical distance:',critical)

        def set_alert_controls_enabled(enabled):
            target.setEnabled(enabled)
            warning.setEnabled(enabled)
            critical.setEnabled(enabled)

        alert_enabled.toggled.connect(set_alert_controls_enabled)
        set_alert_controls_enabled(alert_enabled.isChecked())
        layout.addLayout(form)
        layout.addWidget(QLabel(
            'Warning changes the readout to amber. Critical distance blinks red. '
            'Alerts clear automatically outside the warning distance. '
            "Target and distances use the counter's current units."
        ))
        buttons=QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok|
            QDialogButtonBox.StandardButton.Cancel
        )

        def accept_settings():
            if alert_enabled.isChecked() and (
                warning.value() <= 0
                or critical.value() < 0
                or critical.value() >= warning.value()
            ):
                QMessageBox.warning(
                    dialog,
                    'Invalid Alert Distances',
                    'Warning distance must be greater than critical distance, '
                    'and warning distance must be greater than zero.'
                )
                return
            dialog.accept()

        buttons.accepted.connect(accept_settings)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:
            return

        state['display_color']=(
            None if use_theme_color.isChecked() else selected_color.name()
        )
        state['alert_enabled']=alert_enabled.isChecked()
        state['alert_target']=target.value()
        state['alert_warning_distance']=warning.value()
        state['alert_critical_distance']=critical.value()
        settings_key=self.source_settings_key(*key)
        settings=self.source_settings.setdefault(settings_key,{})
        settings.update({
            'display_color':state['display_color'],
            'alert_enabled':state['alert_enabled'],
            'alert_target':state['alert_target'],
            'alert_warning_distance':state['alert_warning_distance'],
            'alert_critical_distance':state['alert_critical_distance']
        })
        self.save_config()
        self.refresh_alert_styles()

    def save_counter_card_size(self,key,width,height):
        if not (
            CARD_MIN_WIDTH <= width <= CARD_MAX_WIDTH
            and CARD_MIN_HEIGHT <= height <= CARD_MAX_HEIGHT
        ):
            return
        state=self.source_states[key]
        state['card_size']=(width,height)
        settings_key=self.source_settings_key(*key)
        settings=self.source_settings.setdefault(settings_key,{})
        settings['card_size']={'width':width,'height':height}
        self.save_config()

    def reset_counter_card_sizes(self):
        changed=False
        for key,card in self.source_cards.items():
            frame=card['frame']
            frame.setMinimumSize(CARD_MIN_WIDTH,CARD_MIN_HEIGHT)
            frame.setMaximumSize(16777215,16777215)
            frame.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred
            )
            frame.adjustSize()
            frame.updateGeometry()
            self.source_states[key]['card_size']=None
            settings_key=self.source_settings_key(*key)
            settings=self.source_settings.get(settings_key,{})
            if 'card_size' in settings:
                del settings['card_size']
                changed=True
        self.counter_grid.invalidate()
        self.counter_container.adjustSize()
        if changed:
            self.save_config()

    def update_direction_style(self,key):
        colors=THEME_PALETTES[self.theme]['direction']
        direction=self.source_states[key]['direction']
        color=colors.get(direction,colors['STOPPED'])
        font_size=max(15,self.display_font_size//4)
        self.source_cards[key]['direction'].setStyleSheet(
            f'font-size:{font_size}px;font-weight:bold;color:{color};'
        )

    def show_about(self):
        QMessageBox.about(
            self,
            'About CCN',
            'Cable Counter Network V10_0_DEV20\n'
            'Real-time SCC data, playback, and multi-counter display'
        )

    def show_user_manual(self):
        manual_path=Path(__file__).resolve().with_name(MANUAL_FILE)
        try:
            manual_text=manual_path.read_text(encoding='utf-8')
        except OSError as exc:
            QMessageBox.critical(
                self,
                'User Manual Unavailable',
                f'Could not open {MANUAL_FILE}:\n{exc}\n\n'
                'Keep the manual beside the CCN program.'
            )
            return

        dialog=QDialog(self)
        dialog.setWindowTitle('CCN DEV20 User Manual')
        dialog.resize(900,700)
        layout=QVBoxLayout(dialog)
        browser=QTextBrowser(dialog)
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(manual_text)
        layout.addWidget(browser)
        close_button=QPushButton('Close')
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button,0,Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def log(self,msg):
        self.log_window.append(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}')

    def update_clocks(self):
        self.local_lbl.setText('Local: '+datetime.now().strftime('%H:%M:%S'))
        self.utc_lbl.setText('UTC: '+datetime.now(timezone.utc).strftime('%H:%M:%S'))

    # --- Local serial ports ---
    def refresh_ports(self):
        ports=[p.device for p in serial.tools.list_ports.comports()]
        used_ports=set()
        for port_row in self.port_rows:
            combo=port_row['combo']
            connected_port=port_row['connected_port']
            previous_selection=combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(ports)

            if connected_port:
                if connected_port not in ports:
                    combo.addItem(connected_port)
                combo.setCurrentText(connected_port)
                used_ports.add(connected_port)
            else:
                available_ports=[
                    port for port in ports if port not in used_ports
                ]
                selection=(
                    previous_selection
                    if previous_selection in available_ports
                    else available_ports[0] if available_ports else ''
                )
                combo.setCurrentText(selection)
                if selection:
                    used_ports.add(selection)
            combo.blockSignals(False)

    def update_connection_summary(self):
        self.status.setText(
            f'Live COM connections: {len(self.serial_connections)}/{MAX_COM_PORTS}'
        )

    def connect_port(self,port_row):
        try:
            port_name=port_row['combo'].currentText()
            if not port_name:
                QMessageBox.warning(self,'Connect COM Port','Select a COM port first.')
                return
            if port_name in self.serial_connections:
                QMessageBox.warning(
                    self,
                    'Connect COM Port',
                    f'{port_name} is already connected in another row.'
                )
                return

            connection=serial.Serial(
                port_name,
                9600,
                timeout=0,
                write_timeout=1
            )
        except (serial.SerialException,OSError,ValueError) as exc:
            port_row['status'].setText('Connection failed')
            self.log(f'ERROR connecting to {port_row["combo"].currentText()}: {exc}')
            QMessageBox.critical(self,'COM Port Connection Failed',str(exc))
            return

        self.serial_connections[port_name]=connection
        self.serial_buffers[port_name]=bytearray()
        port_row['connected_port']=port_name
        port_row['combo'].setCurrentText(port_name)
        port_row['combo'].setEnabled(False)
        port_row['connect_button'].setEnabled(False)
        port_row['disconnect_button'].setEnabled(True)
        port_row['status'].setText('Connected')
        self.serial_poll_timer.start(100)
        self.update_connection_summary()
        self.log(f'Connected to {port_name}')

    def disconnect_port(self,port_row,error=None):
        port_name=port_row['connected_port']
        if not port_name:
            return

        connection=self.serial_connections.pop(port_name,None)
        self.serial_buffers.pop(port_name,None)
        close_error=None
        if connection:
            try:
                connection.close()
            except (serial.SerialException,OSError) as exc:
                close_error=exc

        port_row['connected_port']=None
        port_row['combo'].setEnabled(True)
        port_row['connect_button'].setEnabled(True)
        port_row['disconnect_button'].setEnabled(False)
        if error:
            port_row['status'].setText('Disconnected after read error')
            self.log(f'ERROR reading from {port_name}; disconnected: {error}')
        elif close_error:
            port_row['status'].setText('Disconnected (close error)')
            self.log(f'ERROR closing {port_name}: {close_error}')
        else:
            port_row['status'].setText('Disconnected')
            self.log(f'Disconnected from {port_name}')

        if not self.serial_connections:
            self.serial_poll_timer.stop()
        self.update_connection_summary()

    def disconnect_all_ports(self):
        for port_row in self.port_rows:
            if port_row['connected_port']:
                self.disconnect_port(port_row)

    # --- TCP server and view-only client ---
    def update_network_controls(self):
        client_mode=self.network_role=='client'
        for port_row in self.port_rows:
            port_row['widget'].setEnabled(not client_mode)
        self.connection_menu.setEnabled(not client_mode)
        self.playback_menu.setEnabled(not client_mode)
        self.playback_file_edit.setReadOnly(client_mode)
        self.start_server_action.setEnabled(self.network_role=='local')
        self.connect_server_action.setEnabled(self.network_role=='local')
        self.stop_server_action.setEnabled(self.network_role=='server')
        self.disconnect_server_action.setEnabled(client_mode)
        for card in self.source_cards.values():
            for name in (
                'rename_button',
                'display_button',
                'zero_button',
                'offset_button',
                'resize_handle'
            ):
                card[name].setEnabled(not client_mode)

    def update_network_status(self):
        if self.network_role=='server' and self.network_server:
            clients=sum(
                1 for state in self.network_clients.values()
                if state['ready']
            )
            text=(
                f'Network: Server on TCP {self.network_server.serverPort()} '
                f'({clients} client(s))'
            )
        elif self.network_role=='client':
            status='connected' if self.network_client_ready else 'connecting'
            text=f'Network: {status} to {self.network_remote_prefix}'
        else:
            text='Network: Local mode'
        self.network_status.setText(text)

    def prompt_start_tcp_server(self):
        port,ok=QInputDialog.getInt(
            self,
            'Start TCP Server',
            'TCP port:',
            DEFAULT_TCP_PORT,
            1024,
            65535
        )
        if ok and self.start_tcp_server(port):
            QMessageBox.information(
                self,
                'TCP Server Started',
                f'Listening on port {port}.\n'
                "On each client PC, enter this computer's LAN IP address "
                'and the same port.'
            )

    def start_tcp_server(self,port=DEFAULT_TCP_PORT):
        if self.network_role!='local':
            QMessageBox.warning(
                self,'Network Mode','Disconnect from the current network mode first.'
            )
            return False
        server=QTcpServer(self)
        server.newConnection.connect(self.accept_tcp_clients)
        address=QHostAddress(QHostAddress.SpecialAddress.AnyIPv4)
        if not server.listen(address,port):
            QMessageBox.critical(
                self,'TCP Server Error',server.errorString()
            )
            server.deleteLater()
            return False

        self.network_server=server
        self.network_role='server'
        self.update_network_controls()
        self.update_network_status()
        self.log(f'TCP server listening on port {server.serverPort()}')
        return True

    def stop_tcp_server(self):
        if self.network_server is None:
            return
        server=self.network_server
        self.network_server=None
        self.network_role='local'
        server.close()
        for client_socket in list(self.network_clients):
            client_socket.abort()
            client_socket.deleteLater()
        self.network_clients.clear()
        server.deleteLater()
        self.update_network_controls()
        self.update_network_status()
        self.log('TCP server stopped')

    def accept_tcp_clients(self):
        while self.network_server and self.network_server.hasPendingConnections():
            client_socket=self.network_server.nextPendingConnection()
            if len(self.network_clients)>=MAX_TCP_CLIENTS:
                client_socket.disconnected.connect(client_socket.deleteLater)
                client_socket.disconnectFromHost()
                continue
            self.network_clients[client_socket]={
                'buffer':bytearray(),
                'ready':False
            }
            client_socket.readyRead.connect(
                lambda socket=client_socket: self.read_tcp_client_hello(socket)
            )
            client_socket.disconnected.connect(
                lambda socket=client_socket: self.remove_tcp_client(socket)
            )

    def read_tcp_client_hello(self,client_socket):
        client=self.network_clients.get(client_socket)
        if client is None:
            return
        client['buffer'].extend(bytes(client_socket.readAll()))
        if len(client['buffer'])>MAX_TCP_LINE_BYTES:
            client_socket.abort()
            return
        while b'\n' in client['buffer']:
            raw_message,_,remaining=client['buffer'].partition(b'\n')
            client['buffer']=bytearray(remaining)
            if len(raw_message)>MAX_TCP_LINE_BYTES:
                client_socket.abort()
                return
            try:
                message=json.loads(raw_message.decode('utf-8'))
            except (UnicodeDecodeError,json.JSONDecodeError):
                client_socket.abort()
                return
            if not isinstance(message,dict):
                client_socket.abort()
                return
            # A client may identify itself, but it cannot send control commands.
            if not client['ready'] and message.get('type')=='hello':
                client['ready']=True
                self.write_tcp_message(
                    client_socket,
                    {'type':'welcome','server':self.windowTitle()}
                )
                self.send_tcp_snapshot(client_socket)
                self.log(
                    f'TCP client connected from '
                    f'{client_socket.peerAddress().toString()}'
                )
                self.update_network_status()
            else:
                client_socket.abort()
                return

    def remove_tcp_client(self,client_socket):
        if self.network_clients.pop(client_socket,None) is not None:
            client_socket.deleteLater()
            self.update_network_status()

    def write_tcp_message(self,client_socket,message):
        try:
            payload=(
                json.dumps(message,separators=(',',':'),allow_nan=False)+'\n'
            ).encode('utf-8')
        except (TypeError,ValueError) as exc:
            self.log(f'NETWORK ERROR: Could not encode message: {exc}')
            return False
        if client_socket.state()!=QTcpSocket.SocketState.ConnectedState:
            return False
        if client_socket.bytesToWrite()>1024*1024:
            self.log('NETWORK ERROR: Disconnecting a slow TCP client')
            client_socket.disconnectFromHost()
            return False
        written=client_socket.write(payload)
        if written!=len(payload):
            self.log(
                f'NETWORK ERROR: TCP message write failed: '
                f'{client_socket.errorString()}'
            )
            client_socket.abort()
            return False
        return True

    def counter_network_message(self,source_id,state):
        return {
            'type':'counter',
            'source':source_id,
            'address':state['address'],
            'label':state['label'],
            'raw_cable':state['raw_cable'],
            'installation_offset':state['installation_offset'],
            'zero_offset':state['zero_offset'],
            'units':state['units'],
            'calibration':state['calibration'],
            'direction':state['direction'],
            'speed':state['speed'],
            'display_color':state['display_color'],
            'alert_enabled':state['alert_enabled'],
            'alert_target':state['alert_target'],
            'alert_warning_distance':state['alert_warning_distance'],
            'alert_critical_distance':state['alert_critical_distance']
        }

    def send_tcp_snapshot(self,client_socket):
        for (source_id,_),state in self.source_states.items():
            if state['last_data_time'] is not None:
                self.write_tcp_message(
                    client_socket,
                    self.counter_network_message(source_id,state)
                )

    def broadcast_counter_state(self,source_id,state):
        if self.network_role!='server':
            return
        message=self.counter_network_message(source_id,state)
        for client_socket,client in list(self.network_clients.items()):
            if client['ready']:
                self.write_tcp_message(client_socket,message)

    def prompt_connect_tcp_client(self):
        host,ok=QInputDialog.getText(
            self,
            'Connect to TCP Server',
            'Server computer name or LAN IP address:'
        )
        if not ok or not host.strip():
            return
        port,ok=QInputDialog.getInt(
            self,
            'Connect to TCP Server',
            'TCP port:',
            DEFAULT_TCP_PORT,
            1,
            65535
        )
        if ok:
            self.connect_tcp_client(host.strip(),port)

    def connect_tcp_client(self,host,port=DEFAULT_TCP_PORT):
        if self.network_role!='local':
            QMessageBox.warning(
                self,'Network Mode','Disconnect from the current network mode first.'
            )
            return False
        if (
            self.serial_connections
            or self.simulation_timer.isActive()
            or any(
                source['timer'].isActive()
                for source in self.playback_sources.values()
            )
        ):
            QMessageBox.warning(
                self,
                'Network Mode',
                'Stop local COM, playback, and simulation sources before '
                'connecting as a client.'
            )
            return False
        if not host or not 1<=port<=65535:
            return False

        client_socket=QTcpSocket(self)
        self.network_client=client_socket
        self.network_client_ready=False
        self.network_client_buffer=bytearray()
        self.network_remote_prefix=f'{host}:{port}'
        self.network_role='client'
        self.network_timeout_timer.start()
        client_socket.connected.connect(self.send_tcp_hello)
        client_socket.readyRead.connect(self.read_tcp_server_messages)
        client_socket.disconnected.connect(self.handle_tcp_server_disconnected)
        client_socket.errorOccurred.connect(self.handle_tcp_server_error)
        self.update_network_controls()
        self.update_network_status()
        client_socket.connectToHost(host,port)
        return True

    def send_tcp_hello(self):
        if self.network_client:
            self.write_tcp_message(
                self.network_client,
                {'type':'hello','version':'DEV20'}
            )

    def read_tcp_server_messages(self):
        client_socket=self.network_client
        if client_socket is None:
            return
        self.network_client_buffer.extend(bytes(client_socket.readAll()))
        if len(self.network_client_buffer)>MAX_TCP_LINE_BYTES:
            self.log('NETWORK ERROR: Server message exceeded the size limit')
            self.disconnect_tcp_client()
            return
        while b'\n' in self.network_client_buffer:
            raw_message,_,remaining=self.network_client_buffer.partition(b'\n')
            self.network_client_buffer=bytearray(remaining)
            if len(raw_message)>MAX_TCP_LINE_BYTES:
                self.disconnect_tcp_client()
                return
            try:
                message=json.loads(raw_message.decode('utf-8'))
            except (UnicodeDecodeError,json.JSONDecodeError) as exc:
                self.log(f'NETWORK ERROR: Invalid server message: {exc}')
                self.disconnect_tcp_client()
                return
            if not isinstance(message,dict):
                self.log('NETWORK ERROR: Invalid server message format')
                self.disconnect_tcp_client()
                return
            if message.get('type')=='welcome':
                self.network_client_ready=True
                self.network_timeout_timer.stop()
                self.update_network_status()
                self.log(f'Connected to TCP server {self.network_remote_prefix}')
            elif (
                message.get('type')=='counter'
                and self.network_client_ready
            ):
                self.apply_remote_counter(message)
            else:
                self.log('NETWORK ERROR: Unexpected message from TCP server')
                self.disconnect_tcp_client()
                return

    def apply_remote_counter(self,message):
        source_id=message.get('source')
        address=message.get('address')
        if (
            not isinstance(source_id,str)
            or not source_id
            or len(source_id)>256
            or address not in ('A','B','C','D')
            or message.get('units') not in ('M','F')
            or not isinstance(message.get('label'),str)
        ):
            self.log('NETWORK ERROR: Invalid counter data received')
            return
        try:
            raw_cable=float(message['raw_cable'])
            installation_offset=float(message['installation_offset'])
            zero_offset=float(message['zero_offset'])
            speed=float(message['speed'])
            alert_target=float(message['alert_target'])
            warning_distance=float(message['alert_warning_distance'])
            critical_distance=float(message['alert_critical_distance'])
        except (KeyError,TypeError,ValueError) as exc:
            self.log(f'NETWORK ERROR: Invalid numeric counter data: {exc}')
            return
        if not all(math.isfinite(value) for value in (
            raw_cable,
            installation_offset,
            zero_offset,
            speed,
            alert_target,
            warning_distance,
            critical_distance
        )):
            self.log('NETWORK ERROR: Non-finite counter data received')
            return
        if (
            raw_cable<0 or raw_cable>99999.9
            or abs(installation_offset)>99999.9
            or abs(zero_offset)>99999.9
            or speed<0 or speed>99999.9
        ):
            self.log('NETWORK ERROR: Counter data is outside supported ranges')
            return
        calibration=message.get('calibration')
        direction=message.get('direction')
        if (
            not isinstance(calibration,str)
            or not re.fullmatch(r'[+-]\d{4}',calibration)
            or direction not in ('PAYING OUT','HAULING IN','STOPPED')
            or len(message['label'])>128
        ):
            self.log('NETWORK ERROR: Invalid counter metadata received')
            return

        display_color=message.get('display_color')
        if display_color is not None and (
            not isinstance(display_color,str)
            or not QColor(display_color).isValid()
        ):
            display_color=None
        alert_enabled=message.get('alert_enabled') is True
        if alert_enabled and (
            warning_distance<=0
            or critical_distance<0
            or critical_distance>=warning_distance
        ):
            alert_enabled=False

        remote_source=f'REMOTE:{self.network_remote_prefix}:{source_id}'
        key,state=self.get_source_state(remote_source,address,persist=False)
        state.update({
            'label':message['label'],
            'raw_cable':raw_cable,
            'installation_offset':installation_offset,
            'zero_offset':zero_offset,
            'units':message['units'],
            'calibration':calibration,
            'direction':direction,
            'speed':speed,
            'last_data_time':time.time(),
            'previous_cable':raw_cable,
            'previous_time':time.time(),
            'display_color':display_color,
            'alert_enabled':alert_enabled,
            'alert_target':alert_target,
            'alert_warning_distance':warning_distance,
            'alert_critical_distance':critical_distance
        })
        self.source_cards[key]['title'].setText(state['label'])
        self.update_counter_display_action(key)
        self.update_counter_card(key)
        self.write_csv(remote_source,state)

    def disconnect_tcp_client(self):
        client_socket=self.network_client
        if client_socket is None:
            return
        self.network_timeout_timer.stop()
        self.network_client=None
        self.network_role='local'
        self.network_client_ready=False
        self.network_client_buffer.clear()
        client_socket.abort()
        client_socket.deleteLater()
        self.update_network_controls()
        self.update_network_status()
        self.log('Disconnected from TCP server')

    def handle_tcp_server_disconnected(self):
        if self.network_client is not None:
            self.disconnect_tcp_client()

    def handle_tcp_server_error(self,error):
        if self.network_client is None:
            return
        message=self.network_client.errorString()
        self.log(f'NETWORK ERROR: {message}')
        if (
            self.network_client.state()
            == QTcpSocket.SocketState.UnconnectedState
        ):
            self.disconnect_tcp_client()
            self.network_status.setText(f'Network: connection failed ({message})')
        else:
            self.network_status.setText(f'Network: connection error ({message})')

    def handle_tcp_connect_timeout(self):
        if self.network_role=='client' and not self.network_client_ready:
            remote=self.network_remote_prefix
            self.log(f'NETWORK ERROR: Timed out connecting to {remote}')
            self.disconnect_tcp_client()
            self.network_status.setText(
                f'Network: connection timed out to {remote}'
            )

    def playback_start_requested(self):
        self.start_playback()

    def playback_stop_requested(self):
        self.stop_playback()

    def simulation_start_requested(self,count):
        self.start_simulation(count)

    def simulation_stop_requested(self):
        self.stop_simulation()

    def set_label(self):
        if self.source_states:
            self.set_source_label(next(iter(self.source_states)))
            return
        text,ok=QInputDialog.getText(self,'Equipment Label','Label:')
        if ok and text.strip():
            self.equipment_label=text.strip()
            self.save_config()

    # --- Per-source state and counter cards ---
    def source_settings_key(self,source_id,address):
        return json.dumps([source_id,address],separators=(',',':'))

    def source_display_name(self,source_id):
        if source_id.startswith('PLAYBACK:'):
            return Path(source_id.split(':',1)[1]).name
        return source_id

    def counter_display_action_text(self,key):
        state=self.source_states[key]
        source_name=self.source_display_name(state['source_id'])
        return f"{state['label']} - {source_name} / {state['address']}"

    def update_counter_display_action(self,key):
        action=self.counter_display_actions.get(key)
        if action is not None:
            action.setText(self.counter_display_action_text(key))

    def get_source_state(self,source_id,address,persist=True):
        key=(source_id,address)
        if key in self.source_states:
            return key,self.source_states[key]

        settings_key=self.source_settings_key(source_id,address)
        settings=self.source_settings.get(settings_key,{})
        if not isinstance(settings,dict):
            settings={}
        if not settings:
            if source_id.startswith('SIM-'):
                label=source_id.replace('SIM-','Simulated Counter ')
            elif source_id.startswith('PLAYBACK:'):
                label=Path(source_id.split(':',1)[1]).stem
            elif not self.source_states:
                label=self.equipment_label
            else:
                label=f'Counter {len(self.source_states)+1}'
            settings={
                'label':label,
                'installation_offset':self.install_offset,
                'zero_offset':self.zero_offset
            }
            self.source_settings[settings_key]=settings

        def numeric_setting(name,default):
            if name not in settings:
                return default
            try:
                value=float(settings.get(name,default))
            except (TypeError,ValueError) as exc:
                self.log(f'Invalid saved counter setting {name}: {exc}')
                return default
            if not math.isfinite(value):
                self.log(f'Invalid non-finite saved counter setting: {name}')
                return default
            return value

        display_color=settings.get('display_color')
        if display_color is not None and (
            not isinstance(display_color,str) or not QColor(display_color).isValid()
        ):
            self.log('Invalid saved counter readout color; using theme default')
            display_color=None

        card_size=None
        saved_card_size=settings.get('card_size')
        if isinstance(saved_card_size,dict):
            try:
                width=int(saved_card_size.get('width'))
                height=int(saved_card_size.get('height'))
                if (
                    CARD_MIN_WIDTH <= width <= CARD_MAX_WIDTH
                    and CARD_MIN_HEIGHT <= height <= CARD_MAX_HEIGHT
                ):
                    card_size=(width,height)
                else:
                    self.log('Invalid saved counter card size; using default size')
            except (TypeError,ValueError) as exc:
                self.log(f'Invalid saved counter card size: {exc}')

        alert_enabled=settings.get('alert_enabled') is True
        alert_target=numeric_setting('alert_target',0.0)
        alert_warning_distance=numeric_setting('alert_warning_distance',0.0)
        alert_critical_distance=numeric_setting('alert_critical_distance',0.0)
        if alert_enabled and (
            alert_target < -99999.9 or alert_target > 99999.9
            or alert_warning_distance <= 0
            or alert_warning_distance > 99999.9
            or alert_critical_distance < 0
            or alert_critical_distance >= alert_warning_distance
        ):
            self.log('Invalid saved near-target alert settings; alert disabled')
            alert_enabled=False

        state={
            'source_id':source_id,
            'address':address,
            'label':settings.get('label','Counter'),
            'raw_cable':0.0,
            'display_cable':0.0,
            'installation_offset':settings.get('installation_offset',self.install_offset),
            'zero_offset':settings.get('zero_offset',self.zero_offset),
            'direction':'STOPPED',
            'speed':0.0,
            'units':'M',
            'calibration':'----',
            'last_data_time':None,
            'previous_cable':None,
            'previous_time':None,
            'speed_history':deque(maxlen=10),
            'display_color':display_color,
            'alert_enabled':alert_enabled,
            'alert_target':alert_target,
            'alert_warning_distance':alert_warning_distance,
            'alert_critical_distance':alert_critical_distance,
            'card_size':card_size
        }
        self.source_states[key]=state
        self.create_counter_card(key,state)
        if persist:
            self.save_config()
        return key,state

    def create_counter_card(self,key,state):
        frame=QFrame()
        frame.setObjectName('counterCard')
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout=QVBoxLayout(frame)

        heading=QHBoxLayout()
        title=QLabel(state['label'])
        title.setStyleSheet('font-size:20px;font-weight:bold;')
        rename_button=QPushButton('Set Label')
        rename_button.clicked.connect(
            lambda checked=False, source_key=key: self.set_source_label(source_key)
        )
        display_button=QPushButton('Display / Alert')
        display_button.clicked.connect(
            lambda checked=False, source_key=key: self.configure_counter_display(source_key)
        )
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(rename_button)
        heading.addWidget(display_button)
        layout.addLayout(heading)

        source_label=QLabel(
            f"Source: {self.source_display_name(state['source_id'])} | Address: {state['address']}"
        )
        layout.addWidget(source_label)

        display=QLabel('0.0 M')
        display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(display)

        alert=QLabel()
        alert.setAlignment(Qt.AlignmentFlag.AlignCenter)
        alert.hide()
        layout.addWidget(alert)

        direction=QLabel('Direction: STOPPED')
        layout.addWidget(direction)
        raw=QLabel('RAW CABLE: 0.0 M')
        offset=QLabel(f"INSTALL OFFSET: {state['installation_offset']:.1f} M")
        speed=QLabel('Speed: 0.000 M/s')
        calibration=QLabel('Calibration: ----')
        layout.addWidget(raw)
        layout.addWidget(offset)
        layout.addWidget(speed)
        layout.addWidget(calibration)

        status_row=QHBoxLayout()
        watchdog=QLabel('Watchdog: NO DATA')
        last_data=QLabel('Last Data: ---')
        status_row.addWidget(watchdog)
        status_row.addStretch()
        status_row.addWidget(last_data)
        layout.addLayout(status_row)

        controls=QHBoxLayout()
        zero_button=QPushButton('ZERO DISPLAY')
        zero_button.setToolTip(
            'Zeroes this displayed reading; it does not change the raw cable value.'
        )
        zero_button.clicked.connect(
            lambda checked=False, source_key=key: self.zero_source_display(source_key)
        )
        offset_button=QPushButton('INSTALL OFFSET')
        offset_button.clicked.connect(
            lambda checked=False, source_key=key: self.set_source_offset(source_key)
        )
        controls.addWidget(zero_button)
        controls.addWidget(offset_button)
        layout.addLayout(controls)

        resize_handle=CardResizeHandle(
            frame,
            lambda width,height,source_key=key: self.save_counter_card_size(
                source_key,width,height
            )
        )
        resize_row=QHBoxLayout()
        resize_row.addStretch()
        resize_row.addWidget(
            resize_handle,0,Qt.AlignmentFlag.AlignRight
        )
        layout.addLayout(resize_row)

        frame.setMinimumSize(CARD_MIN_WIDTH,CARD_MIN_HEIGHT)
        if state['card_size'] is not None:
            frame.setFixedSize(*state['card_size'])

        card_index=len(self.source_cards)
        self.counter_grid.addWidget(frame,card_index//2,card_index%2)
        self.source_cards[key]={
            'frame':frame,
            'title':title,
            'rename_button':rename_button,
            'display_button':display_button,
            'zero_button':zero_button,
            'offset_button':offset_button,
            'display':display,
            'alert':alert,
            'direction':direction,
            'raw':raw,
            'offset':offset,
            'speed':speed,
            'calibration':calibration,
            'watchdog':watchdog,
            'last_data':last_data,
            'resize_handle':resize_handle
        }
        action=QAction(self.counter_display_action_text(key),self)
        action.setCheckable(True)
        action.toggled.connect(frame.setVisible)
        self.counter_display_menu.addAction(action)
        self.counter_display_actions[key]=action
        action.setChecked(True)
        self.counter_display_menu.setEnabled(True)
        self.counter_placeholder.hide()
        self.apply_display_font()
        self.update_network_controls()
        self.update_watchdog()

    def set_source_label(self,key):
        state=self.source_states[key]
        text,ok=QInputDialog.getText(
            self,'Counter Label','Label:',text=state['label']
        )
        if ok and text.strip():
            state['label']=text.strip()
            self.source_settings[self.source_settings_key(*key)]['label']=state['label']
            self.source_cards[key]['title'].setText(state['label'])
            self.update_counter_display_action(key)
            self.save_config()

    def zero_source_display(self,key):
        state=self.source_states[key]
        state['zero_offset']=-(state['raw_cable']+state['installation_offset'])
        self.source_settings[self.source_settings_key(*key)]['zero_offset']=state['zero_offset']
        self.update_counter_card(key)
        self.save_config()
        self.log(
            f"Zeroed display for {state['label']}; raw cable value was unchanged"
        )

    def set_source_offset(self,key):
        state=self.source_states[key]
        value,ok=QInputDialog.getDouble(
            self,
            'Installation Offset',
            'Offset (m):',
            state['installation_offset'],
            -10000,
            10000,
            2
        )
        if ok:
            state['installation_offset']=value
            self.source_settings[self.source_settings_key(*key)]['installation_offset']=value
            self.update_counter_card(key)
            self.save_config()

    def logging_changed(self):
        self.logging_enabled=self.log_cb.isChecked()
        self.save_config()

    def zero_display(self):
        if self.source_states:
            self.zero_source_display(next(iter(self.source_states)))

    def set_offset(self):
        if self.source_states:
            self.set_source_offset(next(iter(self.source_states)))


    def reset_scc(self):
        connected_ports=list(self.serial_connections)
        if not connected_ports:
            QMessageBox.warning(self,'RESET SCC','No COM ports are connected.')
            return
        if len(connected_ports)==1:
            port_name=connected_ports[0]
        else:
            port_name,ok=QInputDialog.getItem(
                self,
                'RESET SCC',
                'Connected port:',
                connected_ports,
                0,
                False
            )
            if not ok:
                return
        value, ok = QInputDialog.getInt(self,'RESET SCC','Reset Value:',0,0,99999)
        if not ok:
            return
        cmd = '!!RT{:05d}\r\n'.format(value)
        try:
            self.serial_connections[port_name].write(cmd.encode('ascii'))
            self.log(f'Sent SCC Reset to {port_name}: {cmd.strip()}')
        except (serial.SerialException,OSError) as exc:
            QMessageBox.critical(self,'RESET SCC',str(exc))

    # --- Status, CSV logging, and card updates ---
    def update_watchdog(self):
        for key,state in self.source_states.items():
            if state['last_data_time'] is None:
                watchdog_state='NO DATA'
            else:
                age=time.time()-state['last_data_time']
                if age<2:
                    watchdog_state='RECEIVING DATA'
                elif age<5:
                    watchdog_state='DATA STALE'
                else:
                    watchdog_state='DATA LOST'
            color=THEME_PALETTES[self.theme]['watchdog'][watchdog_state]
            card=self.source_cards[key]
            card['watchdog'].setText(f'Watchdog: {watchdog_state}')
            card['watchdog'].setStyleSheet(f'color:{color};font-weight:bold;')

    def write_csv(self,source_id,state,log_data=True):
        if not self.logging_enabled or not log_data:
            return
        LOG_DIR.mkdir(parents=True,exist_ok=True)
        fn=LOG_DIR/f"ccn_v10_0_dev20_{datetime.now().strftime('%Y-%m-%d')}.csv"
        exists=fn.exists()
        display=state['raw_cable']+state['installation_offset']+state['zero_offset']
        with open(fn,'a',newline='') as f:
            w=csv.writer(f)
            if not exists:
                w.writerow([
                    'Timestamp','Source','Address','Label','RawCable',
                    'DisplayCable','Offset','Direction','Speed','Units'
                ])
            w.writerow([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                self.source_display_name(source_id),
                state['address'],
                state['label'],
                state['raw_cable'],
                display,
                state['installation_offset'],
                state['direction'],
                state['speed'],
                state['units']
            ])

    def update_counter_card(self,key):
        state=self.source_states[key]
        card=self.source_cards[key]
        state['display_cable']=(
            state['raw_cable']+
            state['installation_offset']+
            state['zero_offset']
        )
        units=state['units']
        card['display'].setText(f"{state['display_cable']:.1f} {units}")
        card['raw'].setText(f"RAW CABLE: {state['raw_cable']:.1f} {units}")
        card['offset'].setText(
            f"INSTALL OFFSET: {state['installation_offset']:.1f} {units}"
        )
        card['direction'].setText(f"Direction: {state['direction']}")
        card['speed'].setText(f"Speed: {state['speed']:.3f} {units}/s")
        card['calibration'].setText(f"Calibration: {state['calibration']}")
        card['last_data'].setText(
            'Last Data: '+datetime.fromtimestamp(state['last_data_time']).strftime('%H:%M:%S')
        )
        self.update_direction_style(key)
        self.refresh_alert_styles()
        self.update_watchdog()

    # All local data sources converge here before display, logging, and broadcast.
    def process_scc_line(
        self,line,source_id='Playback',log_data=True,broadcast=True
    ):

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
        key,state=self.get_source_state(source_id,addr)

        speed = 0.0
        direction = 'STOPPED'
        now = time.time()

        if state['previous_cable'] is not None:
            dc=cable-state['previous_cable']
            dt=now-state['previous_time']
            if dt > 0:
                state['speed_history'].append(abs(dc/dt))
                speed=sum(state['speed_history'])/len(state['speed_history'])

            if dc > 0.01:
                direction = 'PAYING OUT'
            elif dc < -0.01:
                direction = 'HAULING IN'

        state['raw_cable']=cable
        state['units']=units
        state['calibration']=cal
        state['direction']=direction
        state['speed']=speed
        state['last_data_time']=now
        state['previous_cable']=cable
        state['previous_time']=now
        self.update_counter_card(key)
        self.write_csv(source_id,state,log_data)
        if broadcast:
            self.broadcast_counter_state(source_id,state)

        return True

    def read_serial_data(self):
        # A separate buffer is needed for each COM port because reads can split lines.
        for port_name,connection in list(self.serial_connections.items()):
            try:
                waiting=connection.in_waiting
                if waiting:
                    self.serial_buffers[port_name].extend(
                        connection.read(waiting)
                    )

                buffer=self.serial_buffers[port_name]
                while b'\n' in buffer:
                    raw_line,_,remaining=buffer.partition(b'\n')
                    self.serial_buffers[port_name]=buffer=bytearray(remaining)
                    line=raw_line.decode('utf-8',errors='ignore').strip()
                    if line:
                        self.record_raw_string(line)
                        self.process_scc_line(line,port_name)

                if len(buffer)>MAX_SERIAL_BUFFER_BYTES:
                    self.log(
                        f'ERROR: Discarded oversized partial line from {port_name}'
                    )
                    buffer.clear()
            except (serial.SerialException,OSError) as exc:
                port_row=next(
                    row for row in self.port_rows
                    if row['connected_port']==port_name
                )
                self.disconnect_port(port_row,error=exc)

    # --- Playback from recorded SCC lines ---
    def browse_playback_file(self):
        filename,_=QFileDialog.getOpenFileName(
            self,
            'Select Playback File',
            str(RECORDINGS_DIR),
            'Text Files (*.txt *.log *.csv);;All Files (*)'
        )
        if filename:
            self.playback_file=filename
            self.playback_file_edit.setText(filename)
            self.add_playback_source(filename)
        return self.playback_file

    def add_playback_files(self):
        filenames,_=QFileDialog.getOpenFileNames(
            self,
            'Add Counter Playback Files',
            str(RECORDINGS_DIR),
            'Text Files (*.txt *.log *.csv);;All Files (*)'
        )
        added=0
        for filename in filenames:
            if self.add_playback_source(filename):
                added+=1
                self.playback_file=filename
        if filenames:
            self.playback_file_edit.setText(self.playback_file)
            self.log(f'Added {added} playback source(s)')
        return added

    def add_playback_source(self,filename):
        try:
            path=Path(filename).resolve()
            source_id='PLAYBACK:'+str(path)
            if source_id in self.playback_sources:
                self.log(f'Playback source already loaded: {path.name}')
                return False
            lines=path.read_text(encoding='utf-8',errors='ignore').splitlines()
            if not lines:
                self.log(f'PLAYBACK ERROR: Empty file: {path}')
                return False
            timer=QTimer(self)
            timer.timeout.connect(
                lambda playback_id=source_id: self.playback_tick(playback_id)
            )
            self.playback_sources[source_id]={
                'path':path,
                'lines':lines,
                'index':0,
                'timer':timer
            }
            if hasattr(self,'playback_sources_lbl'):
                self.update_playback_summary()
            self.log(f'Playback source loaded: {path.name}')
            return True
        except Exception as e:
            self.log(f'PLAYBACK ERROR: {e}')
            return False

    def start_playback(self, filename=None):
        if filename is None:
            filename=self.playback_file_edit.text().strip() or self.playback_file
        if filename:
            self.playback_file=filename
            source_id='PLAYBACK:'+str(Path(filename).resolve())
            if source_id not in self.playback_sources:
                if not self.add_playback_source(filename):
                    return False
        if not self.playback_sources:
            return False
        for source in self.playback_sources.values():
            source['index']=0
            source['timer'].start(200)
        self.log(f'Playback started: {len(self.playback_sources)} source(s)')
        return True

    def update_playback_summary(self):
        names=[source['path'].name for source in self.playback_sources.values()]
        self.playback_sources_lbl.setText(
            f"Loaded playback files ({len(names)}): " + ', '.join(names)
        )

    def stop_playback(self,source_id=None):
        if source_id is not None:
            source=self.playback_sources.get(source_id)
            if source is not None:
                source['timer'].stop()
                source['index']=0
        else:
            for source in self.playback_sources.values():
                source['timer'].stop()
                source['index']=0
        self.log('Playback stopped')

    def playback_tick(self,source_id):
        source=self.playback_sources[source_id]
        if source['index'] >= len(source['lines']):
            source['timer'].stop()
            return
        line=source['lines'][source['index']].strip()
        source['index']+=1
        if line:
            self.process_scc_line(line,source_id)

    # --- Software-generated counters for demos and network testing ---
    def start_simulation(self,count=2):
        if count not in (2,3):
            return False
        self.simulation_count=count
        self.simulation_tick_count=0
        self.simulation_timer.start(500)
        self.log(f'Started {count} simulated counters')
        return True

    def stop_simulation(self):
        self.simulation_timer.stop()
        self.simulation_count=0
        self.log('Counter simulation stopped')

    def configure_simulation_settings(self):
        dialog=QDialog(self)
        dialog.setWindowTitle('Simulation Settings')
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            'Each simulated counter moves from Start to End and back. '
            'Values are saved between runs.'
        ))

        fields={}
        for address,settings in self.simulation_settings.items():
            group=QGroupBox(f'Counter {address}')
            form=QFormLayout(group)
            start=QDoubleSpinBox()
            start.setRange(0,99999.9)
            start.setDecimals(1)
            start.setSingleStep(0.1)
            start.setSuffix(' M')
            start.setValue(settings['start'])
            end=QDoubleSpinBox()
            end.setRange(0,99999.9)
            end.setDecimals(1)
            end.setSingleStep(0.1)
            end.setSuffix(' M')
            end.setValue(settings['end'])
            form.addRow('Start cable:',start)
            form.addRow('End cable:',end)
            layout.addWidget(group)
            fields[address]=(start,end)

        buttons=QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok|
            QDialogButtonBox.StandardButton.Cancel
        )

        def restore_defaults():
            for address,(start,end) in fields.items():
                defaults=DEFAULT_SIMULATION_SETTINGS[address]
                start.setValue(defaults['start'])
                end.setValue(defaults['end'])

        reset_button=buttons.addButton(
            'Restore Defaults',
            QDialogButtonBox.ButtonRole.ResetRole
        )
        reset_button.clicked.connect(restore_defaults)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:
            return

        self.simulation_settings={
            address:{
                'start':start.value(),
                'end':end.value()
            }
            for address,(start,end) in fields.items()
        }
        self.save_config()
        self.log('Simulation start/end values updated')

    def simulation_tick(self):
        phase=self.simulation_tick_count%40
        travel=phase if phase<=20 else 40-phase
        for index in range(self.simulation_count):
            address=chr(ord('A')+index)
            settings=self.simulation_settings[address]
            fraction=travel/20
            cable=settings['start']+(settings['end']-settings['start'])*fraction
            line=f'$CC{address}{cable:.1f}M+0357'
            self.process_scc_line(line,f'SIM-{index+1}',log_data=False)
        self.simulation_tick_count+=1

    def record_raw_string(self, line):
        try:
            rec_dir = RECORDINGS_DIR
            rec_dir.mkdir(parents=True,exist_ok=True)
            if self.raw_record_file is None:
                fname = rec_dir / f"scc_raw_{datetime.now().strftime('%Y-%m-%d')}.txt"
                self.raw_record_file = open(fname,'a',encoding='utf-8')
            self.raw_record_file.write(line + '\n')
            self.raw_record_file.flush()
        except Exception as e:
            self.log(f'RAW RECORD ERROR: {e}')

    def update_display_values(self,units='M'):
        for key,state in self.source_states.items():
            state['units']=units
            self.update_counter_card(key)

    # --- Main window layout and orderly shutdown ---
    def build_ui(self):
        l=QVBoxLayout()
        header_row=QHBoxLayout()
        logo=QLabel()
        logo_path=Path(__file__).resolve().with_name('CSA_LOGO.png')
        pix=QPixmap(str(logo_path))
        if not pix.isNull():
            logo.setPixmap(pix.scaledToHeight(120))
            logo.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            header_row.addWidget(
                logo,0,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
        credits=QLabel('CSA Ocean Sciences Inc.\nScott Sharpe / Copilot')
        credits.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header_row.addWidget(
            credits,0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header_row.addStretch()
        l.addLayout(header_row)

        self.local_lbl=QLabel(); self.utc_lbl=QLabel()
        clock_row=QHBoxLayout()
        clock_row.addWidget(self.local_lbl)
        clock_row.addWidget(self.utc_lbl)
        clock_row.addStretch()
        l.addLayout(clock_row)

        source_row=QHBoxLayout()
        self.live_ports_group=QGroupBox('Live COM Sources')
        self.live_ports_group.setMaximumWidth(550)
        self.port_rows_layout=QVBoxLayout(self.live_ports_group)
        for index in range(MAX_COM_PORTS):
            self.create_port_row(index)
        self.status=QLabel(f'Live COM connections: 0/{MAX_COM_PORTS}')
        self.port_rows_layout.addWidget(self.status)
        self.network_status=QLabel('Network: Local mode')
        self.port_rows_layout.addWidget(self.network_status)
        source_row.addWidget(self.live_ports_group,0,Qt.AlignmentFlag.AlignTop)
        self.refresh_ports()

        self.playback_group=QGroupBox('Playback Source')
        self.playback_group.setMaximumWidth(400)
        playback_layout=QVBoxLayout(self.playback_group)
        pb_row=QHBoxLayout()
        self.playback_file_edit=QLineEdit()
        self.playback_file_edit.setMinimumWidth(180)
        self.playback_file_edit.setPlaceholderText(
            'Browse or add playback files from the Playback menu'
        )
        pb_row.addWidget(QLabel('Playback File:'))
        pb_row.addWidget(self.playback_file_edit,1)
        playback_layout.addLayout(pb_row)
        self.playback_sources_lbl=QLabel('Loaded playback files (0)')
        self.playback_sources_lbl.setWordWrap(True)
        playback_layout.addWidget(self.playback_sources_lbl)
        source_row.addWidget(self.playback_group,0,Qt.AlignmentFlag.AlignTop)
        source_row.addStretch()
        l.addLayout(source_row)

        self.counter_placeholder=QLabel(
            'No counter data yet. Connect a COM port, load playback, or start a simulation.'
        )
        self.counter_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counter_container=QWidget()
        self.counter_grid=QGridLayout(self.counter_container)
        self.counter_grid.setContentsMargins(6,6,6,6)
        self.counter_grid.setSpacing(10)
        self.counter_area=QScrollArea()
        self.counter_area.setWidgetResizable(True)
        self.counter_area.setMinimumHeight(300)
        self.counter_area.setWidget(self.counter_container)
        l.addWidget(self.counter_placeholder)
        l.addWidget(self.counter_area,1)

        bottom_row=QHBoxLayout()
        self.log_cb=QCheckBox('Enable Logging')
        self.log_cb.setChecked(self.logging_enabled)
        self.log_cb.stateChanged.connect(self.logging_changed)
        bottom_row.addWidget(self.log_cb)
        l.addLayout(bottom_row)

        self.log_window=QTextEdit()
        self.log_window.setReadOnly(True)
        self.log_window.setMaximumHeight(120)
        self.log_window.hide()
        l.addWidget(self.log_window)

        central_widget=QWidget(self)
        central_widget.setLayout(l)
        self.setCentralWidget(central_widget)

    def create_port_row(self,index):
        widget=QWidget()
        layout=QHBoxLayout(widget)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(QLabel(f'Port {index+1}:'))

        combo=QComboBox()
        combo.setMinimumWidth(120)
        connect_button=QPushButton('Connect')
        disconnect_button=QPushButton('Disconnect')
        disconnect_button.setEnabled(False)
        status=QLabel('Disconnected')
        status.setMinimumWidth(150)
        layout.addWidget(combo,1)
        layout.addWidget(connect_button)
        layout.addWidget(disconnect_button)
        layout.addWidget(status)

        port_row={
            'widget':widget,
            'combo':combo,
            'connect_button':connect_button,
            'disconnect_button':disconnect_button,
            'status':status,
            'connected_port':None
        }
        connect_button.clicked.connect(
            lambda checked=False,row=port_row: self.connect_port(row)
        )
        disconnect_button.clicked.connect(
            lambda checked=False,row=port_row: self.disconnect_port(row)
        )
        self.port_rows.append(port_row)
        self.port_rows_layout.addWidget(widget)

    def closeEvent(self,event):
        self.alert_blink_timer.stop()
        self.simulation_timer.stop()
        self.serial_poll_timer.stop()
        self.network_timeout_timer.stop()
        self.clock.stop()
        self.watchdog_timer.stop()
        for source in self.playback_sources.values():
            source['timer'].stop()
        if self.network_role=='server':
            self.stop_tcp_server()
        elif self.network_role=='client':
            self.disconnect_tcp_client()
        self.disconnect_all_ports()
        if self.raw_record_file:
            self.raw_record_file.close()
            self.raw_record_file=None
        event.accept()


# Qt's event loop dispatches button clicks, timers, serial polling, and TCP events.
app=QApplication(sys.argv)
w=CCNMainWindow()
w.show()
sys.exit(app.exec())
