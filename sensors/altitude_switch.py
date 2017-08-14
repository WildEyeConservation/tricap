"""Observer for automated switch. The switch uses the altimeter to start taking pictures."""

from support.basic import Observer
from configparser import ConfigParser
import logging
import local_paths
from enum import Enum
from support.configure import TricapConfig
from config import OverrideState

# CAMERA_STATES = Enum("CamState", ["UNINITIALISED", "INITIALISED", "CAPTURING", "ERROR_CONFIG", "ERROR_CAPTURE"])


class AltiSwitch(Observer):
    _logger = logging.getLogger(__name__)  # start the logger

    def __init__(self, sensor_class): #Constructor for alti switch
        super().__init__()  # get variables from parent class
        self.alti = sensor_class  # SimulatorAlti(settings)
        self.alti_switch_state = False  # start with altimeter switch as off
        self.turn_on_altitude = 0
        self.turn_off_altitude = 0
        self.measured_height = 0

        self.get_alti_switch_boundary()

    def set_altitude_switch(self, override=OverrideState.ALTISWITCH.value):
        if override == OverrideState.ALTISWITCH.value:
            if self.measured_height >= self.turn_on_altitude:
                self.alti_switch_state = True  # Turn on the altitude switch
                self._logger.debug('Altitude Switch - capturing')
            elif self.measured_height < self.turn_off_altitude:
                # self.alti_switch_state = False  # Turn off altitude switch
                self._logger.debug('Altitude Switch - Would have stopped capturing')
        elif override == OverrideState.STOPOVERRIDE.value:  # If switch is overwritten, then the system stops capturing
            self.alti_switch_state = False
            self._logger.debug('Altitude Switch = stopped - not capturing')
        else:  # override with start button with manual on switch
            self.alti_switch_state = True
            self._logger.debug('Altitude Switch = manual - capturing')

    def get_altitude_switch_state(self):  # True shows the switch is ON and vice versa
        # self.set_altitude_switch(override)
        return self.alti_switch_state

    def set_altitude_switch_state(self, override=OverrideState.ALTISWITCH.value):
        self.set_altitude_switch(override)

    def update(self, subject):
        self.measured_height = self.alti.measurement
        self.get_alti_switch_boundary()  # Put this function in here if not placed anywhere else

    def get_alti_switch_boundary(self):
        triconfig = TricapConfig()
        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        self.turn_on_altitude = int(web_settings['automatic_turn_on_height'])
        self.turn_off_altitude = int(web_settings['automatic_turn_off_height'])

        # setting_config = ConfigParser()
        # setting_config.read(local_paths.CONFIG_FP)
        # self.turn_on_altitude = int(setting_config['Web']['automatic_turn_on_height'])
        # self.turn_off_altitude = int(setting_config['Web']['automatic_turn_off_height'])
