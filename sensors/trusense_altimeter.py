"""TruSense S100 Altimeter handler."""
# coding=utf-8

import logging
import threading
from time import sleep

import serial
import serial.tools.list_ports

from config import ALTIMETER_STATE
from functools import partial
from collections import namedtuple
from sensors.base_setting import BaseSetting, SettingSpec


# TODO How to deal with disconnect?
class AltiError(Exception):
    pass


class MiscSettingConfig:
    dict_keys = {'_settings'}

    def __init__(self, widgets):
        self._settings = {key: BaseSetting(widget) for key, widget in widgets.items()}

    def __repr__(self):
        return str(sorted(self._settings))

    def __dir__(self):
        return self._settings.keys()

    def __setattr__(self, key, value):
        if key in self.dict_keys:
            self.__dict__[key] = value
        else:
            self._settings[key].set(value)

    def __getattr__(self, key):
        return self._settings[key]

    __setitem__ = __setattr__
    __getitem__ = __getattr__


class TrusenseAltimeter(object):
    """Handles serial communication with the TruSense S100 Laser Altimeter"""
    _logger = logging.getLogger(__name__)
    errorCodes = {'00': 'S100 Error 00: Invalid Command',
                  '01': 'S100 Error 01: No Target',
                  '10': 'S100 Error 10: Bad Data Checksum',
                  '11': 'S100 Error 11: Already Measuring',
                  '12': 'S100 Error 12: Invalid Parameter',
                  '21': 'S100 Error 21: User Settings Checksum',
                  '22': 'S100 Error 22: Factory Settings Checksum',
                  '23': 'S100 Error 23: BIST Test',
                  '24': 'S100 Error 24: PLL Test',
                  '25': 'S100 Error 25: Tx Power',
                  '26': 'S100 Error 26: Higher Precision',
                  '27': 'S100 Error 27: Receiver',
                  '28': 'S100 Error 28: Supply Voltage too High',
                  '29': 'S100 Error 29: Supply Voltage too Low',
                  '30': 'S100 Error 30: Temperature too High',
                  '31': 'S100 Error 31: Temperature too Low'}

    def __init__(self, settings, data_logger, supported_devices={(1659, 8963)}):
        # SETTINGS
        # default values
        self._setting_strings = ['measurement_timeout', 'num_frames_to_avg']
        self._config = MiscSettingConfig(
            {'measurement_timeout': SettingSpec(choices=None,
                                                get_value=partial(self._get_setting, "num_frames_to_avg"),
                                                set_value=partial(self._set_setting, "num_frames_to_avg")),
             'num_frames_to_avg': SettingSpec(choices=None,
                                              get_value=partial(self._get_setting, "num_frames_to_avg"),
                                              set_value=partial(self._set_setting, "num_frames_to_avg"))})

        self._settings = settings

        self._data_logger = data_logger
        self.state = ALTIMETER_STATE.NOT_CONNECTED
        self._kill_pill = None
        self._read_thread = None
        self._measurement = None

        self._ser = None  # set this to None if something goes wrong with getting the Serial object

        self._ser = serial.Serial(port=self._get_correct_port_name(supported_devices),
                                  baudrate=115200, timeout=1.0, write_timeout=1.0)

        self._logger.info('Altimeter serial port opened.')
        self.state = ALTIMETER_STATE.CONNECTED
        self._connect()
        self._configure()

    @property
    def config(self):
        return self._config

    @property
    def measurement(self):
        return self._measurement

    @staticmethod
    def _get_correct_port_name(supported_devices):
        for port in serial.tools.list_ports.comports():
            if (port.vid, port.pid) in supported_devices:
                return port.device
        raise AltiError('Could not find supported USB serial port.')

    def _connect(self):
        # toggle dtr line, to get the altimeter in the correct state
        self._ser.dtr = 1
        sleep(0.001)
        self._ser.dtr = 0
        # Check for the okay signal
        self._check_ok('Alti did not send OK on startup')

    def _get_setting(self, key):
        return self._settings[key]

    def _set_setting(self, key, value):
        self._settings[key] = value
        self._configure()

    def _check_for_known_error(self, reply):
        if reply[0:3] == b'$ER':
            err_code = reply[4:6].decode(encoding='ascii')
            self._logger.error(TrusenseAltimeter.errorCodes[err_code])

    def _check_ok(self, error_msg):
        reply = self._ser.readline()
        if reply != b'$OK\r\n':
            self._check_for_known_error(reply)
            raise AltiError(error_msg + ' : ' + reply.decode(encoding='ascii'))

    def _write(self, command_str, command_error_str):
        message = '$' + command_str + '\r\n'
        message_bytes = message.encode(encoding='ascii')
        self._ser.write(message_bytes)
        self._check_ok(command_error_str)

    def _configure(self):
        self._write('MM,FCO', 'Error setting measurement mode')
        self._write('TM,FA', 'Error setting target mode')
        self._write('DU,M', 'Error setting distance unit')
        self._write('MT,%d' % int(self._settings['measurement_timeout']), 'Error setting measurement timeout')
        self._write('CA,%d' % int(self._settings['num_frames_to_avg']), 'Error setting continous mode frame averaging')
        self._write('FA,%d' % int(self._settings['num_frames_to_avg']), 'Error setting fast mode frame averaging')

    def reset(self):
        """Get the altimeter object to re-initialise, establishing comms again, etc"""
        if self.state == ALTIMETER_STATE.MEASURING:
            self.stop_measuring()

        self.__init__(self._data_logger)

    def get_state_as_string(self):
        return self.state.name

    def disconnect(self):
        if self._ser and self._ser.is_open:
            self._ser.close()
            self._logger.info('Comms with altimeter have been closed')
        self.state = ALTIMETER_STATE.NOT_CONNECTED

    def _read(self, stop_event):
        consecutive_timeouts = 0
        while not stop_event.is_set():
            msg = self._ser.readline()
            if len(msg) > 0:
                consecutive_timeouts = 0
                dist_str = msg[4:].split(b',')[0]
                self._measurement = float(dist_str)
                self._data_logger.log("Alti measure: %s" % dist_str)
            else:
                consecutive_timeouts += 1
                self._logger.error('Empty message read from alti port, indicates a timeout')
            if consecutive_timeouts >= 5:
                self.state = ALTIMETER_STATE.ERROR
                raise AltiError('Communications with altimeter was lost. 5 Consecutive timeouts ocurred')
        self._write('ST', 'Error stopping measuring mode')
        self.state = ALTIMETER_STATE.CONNECTED

    def start_measuring(self):
        self._write('GO', 'Error starting measuring mode')
        self._kill_pill = threading.Event()
        self._read_thread = threading.Thread(target=self._read,
                                             args=(self._kill_pill,), daemon=True)
        self._read_thread.start()
        self.state = ALTIMETER_STATE.MEASURING

    def stop_measuring(self):
        # Not using asserts, need to have this not fall over when testing the GUI
        if self._read_thread and self._read_thread.is_alive():
            self._kill_pill.set()
            self._read_thread.join()
        self.state = ALTIMETER_STATE.CONNECTED
