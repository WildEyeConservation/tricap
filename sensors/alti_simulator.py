"""Simulator Alti - to be used only when testing the GUI."""

import logging
import threading
from time import sleep

from config import ALTIMETER_STATE, RET_OK, RET_ERROR
from functools import partial
from sensors.base_setting import BaseSetting, SettingSpec
from support.basic import Subject

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
    """Creates a flight path to simulate and test the function of the altimeter, switch and GUI"""
    _logger = logging.getLogger(__name__)#start the logger
    # flight_path_points_index = 0 # static variable used for flight path

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

        self.state = ALTIMETER_STATE.NOT_CONNECTED
        self._measurement = 0

        self.state = ALTIMETER_STATE.CONNECTED

        # bring the alti in line with the other monitors
        self.type_id = 'Altitude'
        self.value = 0
        self.unit = 'm'

        self.flight_path_points_index = 0

        self.flight_tempo = 5
        self.flight_points = [160, 140, 150, 119, 151, 121, 171, 80]
        # self.flight_points = [160,100,20,80,0]  # heights of the flight plan

        self.generation_period = 0.5

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

    def get_state_as_string(self):
        return self.state.name

    def get_error(self):
        return ""

    def set_state_string(self, state):
        self.state.name = state

    def set_flight_path_point_index(self, index):
        self.flight_path_points_index = index

        # Tempo is the increase in the height read by altimeter in m/s
        # points are in meters, set repeat to true to repeat sequence

    def simulate_flight_path(self, tempo, points, repeat = True):
        if len(points) <= self.flight_path_points_index:  # restart flight pattern once finished if true
            if repeat:
                self.flight_path_points_index = 0
            else:
                self._measurement -= tempo
                if self._measurement < 0:
                    self._measurement = 0
                return

        if self._measurement <= points[self.flight_path_points_index]:  # SimulatorAlti.flightTrackPosition is  a static variable used
            self._measurement += tempo
            if self._measurement >= points[self.flight_path_points_index]:
                self.flight_path_points_index += 1
        elif self._measurement >= points[self.flight_path_points_index]:
            self._measurement -= tempo
            if self._measurement <= points[self.flight_path_points_index]:
                self.flight_path_points_index += 1

    def _read(self, stop_event):
        while not stop_event.is_set():
            self.simulate_flight_path(self.flight_tempo, self.flight_points, True)  # Repeat flight points at tempo of 5 m/s
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
    # def altitude_switch(self):
    #     if self._measurement > self.altitude_start_upper:
    #         self.start_measuring()
    #     elif self._measurement < self.altitude_stop_lower:
    #         self.stop_measuring()

