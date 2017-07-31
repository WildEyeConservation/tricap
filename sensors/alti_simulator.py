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
from sensors.altitude_switch import AltiSwitch
from support.basic import Subject, PeriodicMonitor

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


class SimulatorAlti(Subject):
    """Handles serial communication with the TruSense S100 Laser Altimeter"""
    _logger = logging.getLogger(__name__)#start the logger
    i = 0

    def __init__(self, settings, supported_devices={(1659, 8963)}):
        super().__init__()# get variables from parent class
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

        self.state = ALTIMETER_STATE.NOT_CONNECTED
        self._measurement = 0

        self._logger.info('Simulator Alti Port Opened')
        self.state = ALTIMETER_STATE.CONNECTED

        # bring the alti in line with the other monitors
        self.type_id = 'Altitude'
        self.value = 0
        self.unit = 'm'

        self.test_var = 0 # simulator test variables
        self.altitude_start_upper = 150
        self.altitude_stop_lower = 120

        self.flight_points = [160,140,150,200,119,151,121,161,50] # heights of the flight plan

        self.generation_period = 1

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

    # def reset(self):
    #     """Get the altimeter object to re-initialise, establishing comms again, etc"""
    #     if self.state == ALTIMETER_STATE.MEASURING:
    #         self.stop_measuring()

    def get_state_as_string(self):
        return self.state.name

    def set_state_string(self,state):
        self.state.name = state

        # Tempo is the increase in the height read by altimeter in m/s
        # points are in meters, set repeat to true to repeat sequence

    def flight_path(self, tempo, points, repeat = True):
        if (len(points)) <= SimulatorAlti.i:  # restart flight pattern once finished if true
            if repeat:
                SimulatorAlti.i = 0
            else:
                self._measurement -= tempo
                if self._measurement < 0:
                    self._measurement = 0
                return

        if self._measurement <= points[SimulatorAlti.i]:  # SimulatorAlti.i is  a static variable used
            self._measurement += tempo
            if self._measurement > points[SimulatorAlti.i]:
                SimulatorAlti.i += 1
        else:
            self._measurement -= tempo
            if self._measurement < points[SimulatorAlti.i]:
                SimulatorAlti.i += 1

    def _read(self, stop_event):
        while not stop_event.is_set():
            self.flight_path(10, self.flight_points, True) #Repeat flight points at tempo of 10m/s
            self.value = self._measurement
            self.notify()
            sleep(self.generation_period)

        self.state = ALTIMETER_STATE.CONNECTED

    def start_measuring(self):
        self._kill_pill = threading.Event()
        self._read_thread = threading.Thread(target=self._read,
                                             args=(self._kill_pill,), daemon=True)
        self._read_thread.start()
        self.state = ALTIMETER_STATE.MEASURING
        self._logger.debug('Alti - measuring started')

    def stop_measuring(self):
        if self._read_thread and self._read_thread.is_alive():
            self._kill_pill.set()
            self._read_thread.join()
            self._logger.debug('Alti - measuring stopped')
        self.state = ALTIMETER_STATE.CONNECTED

    # if value is higher than hysteresis start value then start the capturing process,
    # else if the value returns below the hysteresis value then the camera stops

    def altitude_switch(self):
        if self._measurement > self.altitude_start_upper:
            self.start_measuring()
        elif self._measurement < self.altitude_stop_lower:
            self.stop_measuring()



        #     if self._mchange_dir == 'up':
        #         self._measurement += 20
        #         if self._measurement > 200 and self.test_var <= 10:
        #             self._measurement = 200
        #             self.test_var += 1
        #         elif self.test_var > 10:
        #             self._mchange_dir = 'down'
        #     else:
        #         self._measurement -= 10
        #         if self._measurement < 100:
        #             self._mchange_dir = 'up'
        #             self.test_var = 0

            # if self._mchange_dir == 'up':
            #     self._measurement += 20
            #     if self._measurement > 200:
            #         self._mchange_dir = 'down'
            # else:
            #     self._measurement -= 20
            #     if self._measurement < 0:
            #         self._mchange_dir = 'up'
