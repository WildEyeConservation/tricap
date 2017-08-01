# Observer for automated switch. The switch uses the altimeter to start taking pictures.
from support.basic import Observer
from configparser import ConfigParser
import logging


class AltiSwitch(Observer):
    _logger = logging.getLogger(__name__)  # start the logger

    def __init__(self, sensor_class): #Constructor for alti switch
        super().__init__()  # get variables from parent class
        self.alti = sensor_class  # SimulatorAlti(settings)
        self.alti_switch = False  # start with altimeter switch as off
        self.altitude_start_upper = 0
        self.altitude_stop_lower = 0
        self.measured_height = 0

        self.alti_switch_boundry()


    def altitude_switch(self, override = 0):
        if override == 0:
            if self.measured_height >= self.altitude_start_upper:
                self.alti_switch = True
                self._logger.debug('AltiSwitch - capturing')
            elif self.measured_height < self.altitude_stop_lower:
                self.alti_switch = False
                self._logger.debug('AltiSwitch - not capturing')
        elif override == 1:  # If switch is overwritten, then the system stops capturing
            self.alti_switch = False
        else:  # override with start button
            self.alti_switch = True


    def get_alti_switch_state(self, override = 0): # True shows the switch is ON and vice versa
        self.altitude_switch(override)
        return self.alti_switch

    def update(self, subject):
        self.measured_height = self.alti.measurement
        #self.alti_switch_boundry() # Put this function in here if not placed anywhere else

    def alti_switch_boundry(self):
        setting_config = ConfigParser()
        setting_config.read('initial.cfg')
        self.altitude_start_upper = int(setting_config['Web']['upper_bound_switch_height'])
        self.altitude_stop_lower = int(setting_config['Web']['lower_bound_switch_height'])