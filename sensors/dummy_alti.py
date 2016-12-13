"""Dummy Alti - to be used only when testing the GUI."""

import logging
import threading
from time import sleep

import serial
import serial.tools.list_ports

from config import ALTIMETER_STATE, RET_OK, RET_ERROR
from functools import partial
from collections import namedtuple
from sensors.base_setting import BaseSetting, SettingSpec

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


class DummyAlti(object):
    """Handles serial communication with the TruSense S100 Laser Altimeter"""
    _logger = logging.getLogger(__name__)

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

        self._read_thread = None
        self._kill_pill = None

        self._mchange_dir = 'up'

        self._data_logger = data_logger
        self.state = ALTIMETER_STATE.NOT_CONNECTED
        self._measurement = 0

        self._logger.info('Dummy Alti Port Opened')
        self.state = ALTIMETER_STATE.CONNECTED

    @property
    def config(self):
        return self._config

    @property
    def measurement(self):
        return self._measurement

    def _get_setting(self, key):
        return self._settings[key]

    def _set_setting(self, key, value):
        self._settings[key] = value

    def reset(self):
        """Get the altimeter object to re-initialise, establishing comms again, etc"""
        if self.state == ALTIMETER_STATE.MEASURING:
            self.stop_measuring()

    def get_state_as_string(self):
        return self.state.name

    def _read(self, stop_event):
        while not stop_event.is_set():
            if self._mchange_dir == 'up':
                self._measurement += 20
                if self._measurement > 200:
                    self._mchange_dir = 'down'
            else:
                self._measurement -= 20
                if self._measurement < 0:
                    self._mchange_dir = 'up'

            sleep(0.5)

        self.state = ALTIMETER_STATE.CONNECTED

    def start_measuring(self):
        self._kill_pill = threading.Event()
        self._read_thread = threading.Thread(target=self._read,
                                             args=(self._kill_pill,), daemon=True)
        self._read_thread.start()
        self.state = ALTIMETER_STATE.MEASURING

    def stop_measuring(self):
        if self._read_thread and self._read_thread.is_alive():
            self._kill_pill.set()
            self._read_thread.join()
        self.state = ALTIMETER_STATE.CONNECTED
