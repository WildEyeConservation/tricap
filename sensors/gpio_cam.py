"""Camera driver for a generic camera that can be accessed using the libgphoto2
library."""

import os
import logging
import threading
import tempfile
import numpy as np
import RPi.GPIO as GPIO

from time import sleep, time
from datetime import datetime

from config import CAMERA_STATES
from .base_setting import BaseSetting

# Max attempts that can be made to trigger a photo during the capture process
IMAGE_COUNT_DELTA_FOR_WAIT_FOR_PATH = 10
IMAGE_COUNT_DELTA_FOR_FETCH = 5

DETECT_IN = 22
TRIGGER_OUT = 17
LED_OUT = 27

# noinspection PyUnresolvedReferences
class GpioCam():
    """Handler for a generic gphoto2 based cameras. Uses this library to handle communication."""

    _logger = logging.getLogger(__name__)

    def __init__(self):
        """Constructor, requires address and camera settings dict."""

        self._gp_camera = None
        self._camera = None
        self._fresh_capture = False
        self.state = CAMERA_STATES.INITIALISED

        self._image_count = 0
        self._trigger_count = 0
        self._prev_im_timestamp = None

        GPIO.setup(DETECT_IN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(TRIGGER_OUT, GPIO.OUT)
        GPIO.setup(LED_OUT, GPIO.OUT)

        GPIO.output(TRIGGER_OUT, GPIO.LOW)
        GPIO.output(LED_OUT, GPIO.HIGH)

        GPIO.add_event_detect(DETECT_IN, GPIO.RISING, callback=self.capture_detected, bouncetime=100)

    def __del__(self):
        """Destructor."""
        GPIO.cleanup()

    @property
    def config(self):
        return {}

    @property
    def data(self):
        return {}

    @property
    def serial_num(self):
        return ''

    def is_cam_image_fresh(self):
        """Check if the camera image is new."""
        return self._fresh_capture

    def cam_trigger(self):
        """Trigger using GPIO output."""

        GPIO.output(TRIGGER_OUT, GPIO.HIGH)

        self._trigger_count += 1
        # self._logger.debug(f'cam_trigger {datetime.now().strftime("%Y %m %d %H:%M:%S")}')
        sleep(1e-3)

    def _trigger_capture(self):
        """Make the camera capture an image but don't wait for it to return.

        Emit GPIO output to trigger capture
        """

        self.cam_trigger()

    def capture(self, barrier: threading.Barrier):
        self._logger.debug(f'capture {datetime.now().strftime("%Y %m %d %H:%M:%S")}')
        self._trigger_count = 0
        self._image_count = 0

        self.state = CAMERA_STATES.CAPTURING

        while True:
            GPIO.output(TRIGGER_OUT, GPIO.LOW)
            if barrier:
                barrier.wait()

            # trigger required
            self._trigger_capture()

    def capture_detected(self, channel):
        self._image_count += 1
        # self._logger.debug(f'capture_detected {datetime.now().strftime("%Y %m %d %H:%M:%S")} {channel}')
        GPIO.output(LED_OUT, GPIO.LOW)
        sleep(200e-3)
        GPIO.output(LED_OUT, GPIO.HIGH)

    def get_state_as_string(self):
        """Return the state of the camera as a string."""
        return self.state.name

    def get_cam_image_count(self):
        """Return the number of images captured by the camera, as tracked by this object."""
        return self._image_count

    def get_disk_info(self):
        return {}
