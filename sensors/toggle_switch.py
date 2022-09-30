"""Everything needed for the toggle switch."""

import RPi.GPIO as GPIO

from support.sms_sender import SMSSender
from support.basic import PeriodicMonitor, Observer
import subprocess

import logging

from config import CAM_MANAGER_STATES, CAMERA_STATES

import time

GPIO.setmode(GPIO.BCM)

SWITCH_PIN = 22
RED_PIN = 17
GREEN_PIN = 27

def gpio_cleanup():
    try:
        GPIO.output(RED_PIN, GPIO.LOW)
        GPIO.output(GREEN_PIN, GPIO.LOW)
        GPIO.cleanup()
    except RuntimeError:
        pass

class ToggleSwitchMonitor(PeriodicMonitor):
    """Monitor how high the altitude is."""
    _logger = logging.getLogger(__name__)  # start the logger

    def __init__(self, period=1):
        """Constructor."""
        super(ToggleSwitchMonitor, self).__init__(period)

        GPIO.setup(SWITCH_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

        self.type_id = 'ToggleSwitch'
        self.value = 0
        self.unit = 'boolean'

        self._logger.info('Toggle switch monitor has been instantiated.')

    def __del__(self):
        """Destructor."""
        gpio_cleanup()

    def monitor_step(self):
        """Update the value."""
        if GPIO.input(SWITCH_PIN):
            # toggle switch is high impedance, which we are interpreting as off
            self.value = 0
        else:
            self.value = 1

class ToggleSwitchObserver(Observer):
    """React to the toggle switch status."""

    _logger = logging.getLogger(__name__)  # start the logger
    def __init__(self, cam_manager, session_logger, toggle_switch_monitor=None):
        """Constructor."""
        super(ToggleSwitchObserver, self).__init__()

        self.toggled_on = False
        self._log_counter = 0
    
        self.cam_manager = cam_manager
        self.session_logger = session_logger
        # self.sms_sender = SMSSender()

        if toggle_switch_monitor is not None:
            toggle_switch_monitor.attach(self)

        self._logger.info('Toggle switch observer has been instantiated.')

    def update(self, subject):      
        self._log_counter += 1
        if self._log_counter == 10:
            self._log_counter = 0
            self._logger.info('Toggle switch - update.')  
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
class CamManagerMonitor(PeriodicMonitor):
    """Monitor how high the altitude is."""
    _logger = logging.getLogger(__name__)  # start the logger

    def __init__(self, cam_manager, period=1):
        """Constructor."""
        super().__init__(period)
        
        self.cam_manager = cam_manager

        self.type_id = 'CamManager'
        self.value = 0
        self.unit = 'boolean'

        self._logger.info('Cam Manager monitor has been instantiated.')

    def monitor_step(self):
        """Update the value."""
        if self.cam_manager.state == CAM_MANAGER_STATES.STARTED:
            self.value = 1
        else:
            self.value = 0

class CamCopyMonitor(PeriodicMonitor):
    """Monitor for each camera."""
    _logger = logging.getLogger(__name__)  # start the logger

    def __init__(self, cam_manager, period=1):
        """Constructor."""
        super().__init__(period)
        self.cam_manager = cam_manager

    def monitor_step(self):
        """Updat the value."""
        self.cam_manager.copy_disk_monitor()

class CamErrorMonitor(PeriodicMonitor):
    """Monitor for each camera."""
    _logger = logging.getLogger(__name__)  # start the logger

    def __init__(self, cam, index, period=1):
        """Constructor."""
        super().__init__(period)

        self.cam = cam

        self.type_id = 'CamError' + str(index)
        self.value = 0
        self.unit = 'error'

    def monitor_step(self):
        """Updat the value."""
        if self.cam.state == CAMERA_STATES.ERROR_CONFIG or \
           self.cam.state == CAMERA_STATES.ERROR_CAPTURE:
            self._logger.warning('Single cam monitor: error')
            self.value = 1
        else:
            self.value = 0

class CamCaptureMonitor(PeriodicMonitor):
    """Monitor for each camera."""
    _logger = logging.getLogger(__name__)  # start the logger

    def __init__(self, cam, index, period=0.3):
        """Constructor."""
        super().__init__(period)

        self.cam = cam
        self._captureCount = 0
        self._monitorCount = 0

        self.type_id = 'CamCapture' + str(index)
        self.value = 0
        self.unit = 'capture'

    def monitor_step(self):
        """Updat the value."""
        if self._captureCount != self.cam.captureCount and self.cam.captureCount != 0:
            # Turn on green LED
            self.value = 1
            self._monitorCount = 0
        else:
            self._monitorCount += 1
            if self._monitorCount == 3:
                # Turn off green LED
                self.value = 0
                
        self._captureCount = self.cam.captureCount

class LEDController(Observer):
    """React to the cam capturing status."""

    _logger = logging.getLogger(__name__)  # start the logger
    def __init__(self, cam_man_monitor, cam_error_monitors, cam_capture_monitors):
        """Constructor."""
        super().__init__()

        self.toggled_on = False

        GPIO.setup(GREEN_PIN, GPIO.OUT)
        GPIO.setup(RED_PIN, GPIO.OUT)

        GPIO.output(GREEN_PIN, GPIO.LOW)

        # self.red_pwm = GPIO.PWM(RED_PIN, 0.5)
        # self.red_pwm.start(50)
        # self.green_pwm = GPIO.PWM(GREEN_PIN, 0.5)

        self.allowed_cam_errors = 0
        self.cam_errors = [0]*len(cam_error_monitors)
        self.cam_captures = [0]*len(cam_capture_monitors)

        self.error_state = 0
        self.capture_state = 0
        self.run_state = 0
        self.prev_error_state = 0
    
        cam_man_monitor.attach(self)
        for cem in cam_error_monitors:
            cem.attach(self)
        for ccm in cam_capture_monitors:
            ccm.attach(self)

        self._logger.info('LED Controller has been instantiated.')

        # self.sms_sender = SMSSender()

    def __del__(self):
        """Destructor."""
        gpio_cleanup()

    def update(self, subject):
        # Check first for the cameras and their error states
        if subject.type_id[:len('CamError')] == 'CamError':
            idx = int(subject.type_id[-1])
            if subject.value == 0:
                self.cam_errors[idx] = 0
            else:
                self.cam_errors[idx] += 1
                print('Error count on %d is %d' %(idx, self.cam_errors[idx]))

        self.error_state = 0
        for idx in range(len(self.cam_errors)):
            if self.cam_errors[idx] > self.allowed_cam_errors:
                self.error_state = 1

        if subject.type_id[:len('CamCapture')] == 'CamCapture':
            idx = int(subject.type_id[-1])
            self.cam_captures[idx] = subject.value

        # self.capture_state = self.cam_captures == [1]*len(self.cam_captures)
        self.capture_state = self.cam_captures == [1, 1, 1]

        if self.error_state == 1:
            GPIO.output(GREEN_PIN, GPIO.HIGH)
            GPIO.output(RED_PIN, GPIO.HIGH)
        elif self.capture_state == 1:
            GPIO.output(GREEN_PIN, GPIO.HIGH)
            GPIO.output(RED_PIN, GPIO.LOW)
        else:
            GPIO.output(GREEN_PIN, GPIO.LOW)
            GPIO.output(RED_PIN, GPIO.HIGH)

        if subject.type_id == 'CamManager':
            if subject.value == 0: # Capture is stopped 
                if self.toggled_on: # Capture was stopped (previous observation was still running)
                    self._logger.info('LEDController - Capture was stopped')
                    self.toggled_on = False
                    if self.error_state == 1:
                        self._logger.info('Restarting...')
                        # subprocess.run(["systemctl", "restart", "tricap.service"])
                        subprocess.call('reboot', shell=True)
            else: # switch is in the on position
                if self.toggled_on is False: # User has flicked the switch on
                    self._logger.info('LEDController - Capture has started')
                    self.toggled_on = True

        # if (self.prev_error_state != self.error_state and self.error_state == 1):
        #     # error state changed and in error
        #     self.sms_sender.send('Error state entered')
        
        self.prev_error_state = self.error_state
