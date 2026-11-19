import os
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialogButtonBox, QDoubleSpinBox,
    QPushButton
)

import CCN_V10_0_DEV21 as ccn
from ato_modbus import modbus_crc16


class FakeSerial:
    def __init__(self):
        self.port='COM9'
        self.buffer=bytearray()
        self.writes=[]

    @property
    def in_waiting(self):
        return len(self.buffer)

    def read(self,size):
        data=bytes(self.buffer[:size])
        del self.buffer[:size]
        return data

    def write(self,data):
        self.writes.append(data)
        return len(data)

    def close(self):
        pass


class TensionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir=tempfile.TemporaryDirectory()
        self.original_paths=(
            ccn.DATA_DIR,
            ccn.CONFIG_FILE,
            ccn.LOG_DIR,
            ccn.RECORDINGS_DIR
        )
        root=Path(self.temp_dir.name)
        ccn.DATA_DIR=root
        ccn.CONFIG_FILE=root/'ccn_config.json'
        ccn.LOG_DIR=root/'logs'
        ccn.RECORDINGS_DIR=root/'recordings'
        self.window=ccn.CCNMainWindow()
        self.window.logging_enabled=False

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()
        (
            ccn.DATA_DIR,
            ccn.CONFIG_FILE,
            ccn.LOG_DIR,
            ccn.RECORDINGS_DIR
        )=self.original_paths
        self.temp_dir.cleanup()

    def test_dev21_uses_its_own_manual_and_log_files(self):
        self.window.logging_enabled=True
        self.window.process_scc_line(
            '$CCA12.5M+0357',source_id='COM9',broadcast=False
        )
        self.window.apply_tension_reading(4.0,'kg','ATO Modbus RTU')

        self.assertIn('DEV21',self.window.windowTitle())
        self.assertTrue(Path(ccn.__file__).with_name(ccn.MANUAL_FILE).is_file())
        self.assertEqual(len(list(ccn.LOG_DIR.glob('ccn_v10_0_dev21_*.csv'))),2)

    def test_tension_sample_pairs_to_selected_counter_and_flags_limit(self):
        self.assertTrue(
            self.window.process_scc_line(
                '$CCA12.5M+0357',
                source_id='COM9',
                broadcast=False
            )
        )
        self.window.tension_counter_key=('COM9','A')
        self.window.tension_settings['high_limit_enabled']=True
        self.window.tension_settings['high_limit']=3.0
        self.window.apply_tension_reading(
            4.0,'kg','Simulation',log_data=False
        )

        self.assertEqual(list(self.window.tension_plot_history),[(12.5,4.0)])
        self.assertEqual(
            self.window.tension_watchdog_label.text(),
            'Status: OVER LIMIT'
        )

    def test_plot_association_distinguishes_same_address_on_two_sources(self):
        self.window.process_scc_line(
            '$CCA1.0M+0357',source_id='COM9',broadcast=False
        )
        self.window.process_scc_line(
            '$CCA2.0M+0357',source_id='COM10',broadcast=False
        )
        self.window.tension_counter_combo=QComboBox()
        self.window.tension_counter_key=('COM10','A')
        self.window.update_tension_counter_options()

        selected_index=self.window.tension_counter_combo.findData(
            ('COM10','A')
        )
        self.assertGreater(selected_index,0)
        self.assertEqual(
            self.window.tension_counter_combo.itemData(selected_index),
            ('COM10','A')
        )
        self.window.tension_counter_combo=None

    def test_simulation_can_reach_lost_watchdog_state(self):
        self.window.tension_settings['simulation_stale']=True
        self.assertTrue(self.window.start_tension_simulation())
        for _ in range(10):
            self.window.tension_simulation_tick()
        self.window.tension_last_data_time=time.time()-6
        self.window.update_tension_watchdog()

        self.assertEqual(
            self.window.tension_watchdog_label.text(),
            'Status: DATA LOST'
        )

    def test_peak_tracks_displayed_readings_and_resets_on_zero(self):
        self.window.apply_tension_reading(-5.0,'kg','Simulation',log_data=False)
        self.window.apply_tension_reading(-2.0,'kg','Simulation',log_data=False)
        self.window.apply_tension_reading(-3.0,'kg','Simulation',log_data=False)
        self.assertEqual(self.window.tension_peak_label.text(),'Peak Tension: -2.00 kg')
        self.window.zero_tension_display()
        self.assertEqual(self.window.tension_peak,0.0)
        self.window.apply_tension_reading(-1.0,'kg','Simulation',log_data=False)
        self.assertEqual(self.window.tension_peak,2.0)
        self.window.reset_tension_peak()
        self.assertEqual(self.window.tension_peak,2.0)
        self.window.tension_last_data_time=time.time()-6
        self.window.reset_tension_peak()
        self.assertIsNone(self.window.tension_peak)

    def test_tension_alarms_colors_sound_and_stale_clear(self):
        settings=self.window.tension_settings
        settings.update({
            'high_limit_enabled':True,'high_limit':10.0,
            'critical_enabled':True,'critical_limit':20.0,
            'warning_color':'#123456','critical_color':'#abcdef'
        })
        with patch.object(self.window,'start_critical_alarm') as alarm:
            self.window.apply_tension_reading(10.0,'kg','Simulation',log_data=False)
            self.assertEqual(self.window.tension_alert_level(),'NONE')
            self.window.apply_tension_reading(11.0,'kg','Simulation',log_data=False)
            self.assertEqual(self.window.tension_alert_level(),'WARNING')
            self.assertIn('#123456',self.window.tension_readout.styleSheet())
            self.window.apply_tension_reading(21.0,'kg','Simulation',log_data=False)
            self.assertEqual(self.window.tension_alert_level(),'CRITICAL')
            self.assertIn('#abcdef',self.window.tension_readout.styleSheet())
            alarm.assert_called_once()
            self.window.tension_last_data_time=time.time()-6
            self.window.update_tension_watchdog()
            self.assertFalse(self.window.critical_alert_active)
            self.assertEqual(self.window.tension_watchdog_label.text(),'Status: DATA LOST')

    def test_stale_tension_does_not_clear_active_counter_alarm(self):
        self.window.process_scc_line(
            '$CCA12.0M+0357',source_id='COM9',broadcast=False
        )
        key=('COM9','A')
        self.window.source_states[key].update({
            'alert_enabled':True,'alert_target':12.0,
            'alert_warning_distance':2.0,'alert_critical_distance':1.0
        })
        self.window.tension_settings.update({
            'critical_enabled':True,'critical_limit':10.0
        })
        with patch.object(self.window,'start_critical_alarm'), \
             patch.object(self.window,'stop_critical_alarm') as stop_alarm:
            self.window.apply_tension_reading(11.0,'kg','Simulation',log_data=False)
            self.window.tension_last_data_time=time.time()-6
            self.window.update_tension_watchdog()
            self.assertTrue(self.window.critical_alert_active)
            stop_alarm.assert_not_called()

    def test_tension_label_is_saved(self):
        with patch.object(ccn.QInputDialog,'getText',return_value=('Winch tension',True)):
            self.window.set_tension_label()
        self.assertEqual(self.window.tension_group.title(),'Winch tension - ATO Modbus RTU')
        config=json.loads(ccn.CONFIG_FILE.read_text())
        self.assertEqual(config['tension_settings']['label'],'Winch tension')

    def test_alarm_dialog_saves_thresholds_and_colors(self):
        def fill_dialog():
            dialog=self.application.activeModalWidget()
            dialog.findChild(QCheckBox,'tension_warning_enabled').setChecked(True)
            dialog.findChild(QDoubleSpinBox,'tension_warning_limit').setValue(10)
            dialog.findChild(QCheckBox,'tension_critical_enabled').setChecked(True)
            dialog.findChild(QDoubleSpinBox,'tension_critical_limit').setValue(20)
            dialog.findChild(QPushButton,'tension_warning_color').click()
            dialog.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Ok
            ).click()

        QTimer.singleShot(0,fill_dialog)
        with patch.object(ccn.QColorDialog,'getColor',return_value=QColor('#123456')):
            self.window.configure_tension_alarms()
        config=json.loads(ccn.CONFIG_FILE.read_text())['tension_settings']
        self.assertTrue(config['high_limit_enabled'])
        self.assertTrue(config['critical_enabled'])
        self.assertEqual(config['high_limit'],10)
        self.assertEqual(config['critical_limit'],20)
        self.assertEqual(config['warning_color'],'#123456')
        self.window.load_config()
        self.assertEqual(self.window.tension_settings['warning_color'],'#123456')
        self.assertEqual(self.window.tension_settings['critical_limit'],20)

    def test_alarm_dialog_rejects_reversed_thresholds(self):
        def fill_dialog():
            dialog=self.application.activeModalWidget()
            dialog.findChild(QCheckBox,'tension_warning_enabled').setChecked(True)
            dialog.findChild(QDoubleSpinBox,'tension_warning_limit').setValue(20)
            dialog.findChild(QCheckBox,'tension_critical_enabled').setChecked(True)
            dialog.findChild(QDoubleSpinBox,'tension_critical_limit').setValue(10)
            dialog.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Ok
            ).click()
            dialog.reject()

        QTimer.singleShot(0,fill_dialog)
        with patch.object(ccn.QMessageBox,'warning') as warning:
            self.window.configure_tension_alarms()
        warning.assert_called_once()
        self.assertFalse(self.window.tension_settings['high_limit_enabled'])

    def test_view_toggle_hides_tension_panel_without_disconnect(self):
        connection=FakeSerial()
        self.window.tension_connection=connection
        self.window.tension_view_action.setChecked(False)

        self.assertTrue(self.window.tension_group.isHidden())
        self.assertIs(self.window.tension_connection,connection)
        self.assertFalse(self.window.tension_view_enabled)
        config=json.loads(ccn.CONFIG_FILE.read_text())
        self.assertFalse(config['tension_view_enabled'])

    def test_reset_tension_zero_restores_scaled_reading_only(self):
        self.window.process_scc_line(
            '$CCA12.0M+0357',source_id='COM9',broadcast=False
        )
        self.window.source_states[('COM9','A')]['zero_offset']=-12.0
        self.window.tension_zero_offset=8.0
        self.window.tension_value=3.0
        self.window.tension_units='kg'
        self.window.reset_tension_display()

        self.assertEqual(self.window.tension_zero_offset,0.0)
        self.assertEqual(self.window.tension_readout.text(),'3.00 kg')
        self.assertEqual(
            self.window.source_states[('COM9','A')]['zero_offset'],
            -12.0
        )

    def test_modbus_poll_updates_tension_readout(self):
        connection=FakeSerial()
        self.window.tension_connection=connection
        self.window.tension_settings['scale_factor']=0.01
        self.window.tension_settings['units']='kg'
        self.window.read_tension_data()
        raw_value=123456
        payload=(
            bytes((1,3,4))
            + raw_value.to_bytes(4,byteorder='big',signed=True)
        )
        crc=modbus_crc16(payload)
        connection.buffer.extend(
            payload+bytes((crc&0xFF,crc>>8))
        )
        self.window.read_tension_data()

        self.assertEqual(len(connection.writes),1)
        self.assertEqual(
            self.window.tension_readout.text(),
            '1234.56 kg'
        )
        self.assertIsNotNone(self.window.tension_last_data_time)

    def test_modbus_poll_ignores_local_rtu_echo(self):
        connection=FakeSerial()
        self.window.tension_connection=connection
        self.window.read_tension_data()
        request=connection.writes[0]
        payload=bytes((1,3,4,0,0,0,7))
        crc=modbus_crc16(payload)
        connection.buffer.extend(
            request+payload+bytes((crc&0xFF,crc>>8))
        )
        self.window.read_tension_data()

        self.assertEqual(self.window.tension_value,7.0)
        self.assertNotIn(
            'Invalid Modbus response CRC',
            self.window.log_window.toPlainText()
        )

    def test_plot_dialog_opens_and_closes(self):
        self.window.tension_plot_history.extend(
            ((10.0,5.0),(12.0,7.0))
        )
        self.window.show_tension_cable_plot()
        self.application.processEvents()

        self.assertIsNotNone(self.window.tension_plot_widget)
        self.window.tension_plot_dialog.close()
        self.application.processEvents()


if __name__=='__main__':
    unittest.main()
