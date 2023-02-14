"""Camera driver for a generic camera that can be accessed using the libgphoto2
library."""

import os
import logging
import threading
import tempfile
import numpy as np

from time import sleep, time
from datetime import datetime

from config import CAMERA_STATES
from .base_setting import BaseSetting

# Max attempts that can be made to trigger a photo during the capture process
IMAGE_COUNT_DELTA_FOR_WAIT_FOR_PATH = 10
IMAGE_COUNT_DELTA_FOR_FETCH = 5

# noinspection PyUnresolvedReferences
class GpioCam():
    """Handler for a generic gphoto2 based cameras. Uses this library to handle communication."""

    _logger = logging.getLogger(__name__)

    def __init__(self):
        """Constructor, requires address and camera settings dict."""

        self._gp_camera = None
        self._fresh_capture = False
        self.state = CAMERA_STATES.INITIALISED

        self._image_count = 0
        self._prev_im_timestamp = None

    def is_cam_image_fresh(self):
        """Check if the camera image is new."""
        return self._fresh_capture

    def cam_trigger(self):
        """Trigger using GPIO output."""
        # TODO ALKMAAR
        self._image_count += 1
        self._logger.debug(f'cam_trigger {datetime.now().strftime("%Y %m %d %H:%M:%S")}')

    def _trigger_capture(self):
        """Make the camera capture an image but don't wait for it to return.

        Emit GPIO output to trigger capture
        """

        self.cam_trigger()

    def capture(self, stop_capture, barrier: threading.Barrier):
        self._logger.debug(f'capture {datetime.now().strftime("%Y %m %d %H:%M:%S")}')
        self._image_count = 0

        # main loop
        while True:
            if stop_capture.is_set():
                # stop trigger
                self.state = CAMERA_STATES.INITIALISED
                return

            if barrier:
                barrier.wait()

            # trigger required
            self._trigger_capture()                
            self.state = CAMERA_STATES.CAPTURING

    def get_state_as_string(self):
        """Return the state of the camera as a string."""
        return self.state.name

    def get_cam_image_count(self):
        """Return the number of images captured by the camera, as tracked by this object."""
        return self._image_count
