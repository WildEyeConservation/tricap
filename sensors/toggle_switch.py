"""Everything needed for the toggle switch."""

import RPi.GPIO as GPIO

from support.sms_sender import SMSSender
from support.basic import PeriodicMonitor, Observer

import logging

from config import CAM_MANAGER_STATES

SWITCH_PIN = 22
RED_PIN = 17
GREEN_PIN = 27

class ToggleSwitchMonitor(PeriodicMonitor):
    """Monitor how high the altitude is."""
    _logger = logging.getLogger(__name__)  # start the logger

    def __init__(self, period=1):
        """Constructor."""
        super(ToggleSwitchMonitor, self).__init__(period)

        GPIO.setup(SWITCH_PIN, GPIO.IN)

        self.type_id = 'ToggleSwitch'
        self.value = 0
        self.unit = 'boolean'

        self._logger.info('Toggle switch monitor has been instantiated.')

    def monitor_step(self):
        """Update the value."""
        if GPIO.input(SWITCH_PIN):
            # toggle switch is on
            self.value = 1
        else:
            self.value = 0

class ToggleSwitchObserver(Observer):
    """React to the toggle switch status."""

    _logger = logging.getLogger(__name__)  # start the logger
    def __init__(self, cam_manager, session_logger, toggle_switch_monitor=None):
        """Constructor."""
        super(ToggleSwitchObserver, self).__init__()

        self.toggled_on = False
    
        self.cam_manager = cam_manager
        self.session_logger = session_logger
        self.sms_sender = SMSSender()

        if toggle_switch_monitor is not None:
            toggle_switch_monitor.attach(self)

        self._logger.info('Toggle switch observer has been instantiated.')

    def update(self, subject):        
        if subject.value == 0: # switch is in the off position
            if self.toggled_on: # User has flicked the switch off
                self._logger.info('Toggle switch - stopping capture.')
                self.cam_manager.stop_capturing()                
                self.toggled_on = False
        else: # switch is in the on position
            if self.toggled_on is False: # User has flicked the switch on
                self._logger.info('Toggle switch - starting capture.')
                self.session_logger.create_new_session()
                self.cam_manager.start_capturing()
                self.toggled_on = True

# TODO The LED Light Monitor should be separate
class CamCapturingMonitor(PeriodicMonitor):
    """Monitor how high the altitude is."""
    _logger = logging.getLogger(__name__)  # start the logger

    def __init__(self, cam_manager, period=1):
        """Constructor."""
        super().__init__(period)
        
        self.cam_manager = cam_manager

        self.type_id = 'CamCapturing'
        self.value = 0
        self.unit = 'boolean'

        self._logger.info('Toggle switch monitor has been instantiated.')

    def monitor_step(self):
        """Update the value."""
        if self.cam_manager.CAM_MANAGER_STATES.STARTED:
            self.value = 1
        else:
            self.value = 0


class LEDController(Observer):
    """React to the cam capturing status."""

    _logger = logging.getLogger(__name__)  # start the logger
    def __init__(self, boolean_monitor=None):
        """Constructor."""
        super().__init__()

        self.toggled_on = False

        GPIO.setup(GREEN_PIN, GPIO.OUT)
        GPIO.setup(RED_PIN, GPIO.OUT)

        GPIO.output(GREEN_PIN, GPIO.LOW)
        GPIO.output(RED_PIN, GPIO.HIGH)
    
        if boolean_monitor is not None:
            boolean_monitor.attach(self)

        self._logger.info('LED Controller has been instantiated.')

    def update(self, subject):        
        if subject.value == 0: # Capture is stopped 
            if self.toggled_on: # Capture was stopped (previous observation was still running)
                self._logger.info('LED controller - off state.')
                GPIO.output(GREEN_PIN, GPIO.LOW)
                GPIO.output(RED_PIN, GPIO.HIGH)
                self.toggled_on = False
        else: # switch is in the on position
            if self.toggled_on is False: # User has flicked the switch on
                self._logger.info('Toggle switch - starting capture.')
                GPIO.output(GREEN_PIN, GPIO.HIGH)
                GPIO.output(RED_PIN, GPIO.LOW)
                self.toggled_on = True
