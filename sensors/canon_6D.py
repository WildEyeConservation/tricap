from sensors.gphoto_cam import GPhotoCam
import threading
from config import CAMERA_STATES
import gphoto2 as gp
import time


class Canon6DCam():
    def __init__(self, cameraDriver):
        self._camera = cameraDriver
        self.config.output = 'Undefined'  # Do not be in live mode
        self.config.drivemode = 'Single'
        self.config.reviewtime = 'None'
        self.capture = self._camera.capture
        self.get_state_as_string = self._camera.get_state_as_string
        self.is_cam_image_fresh = self._camera.is_cam_image_fresh

    def focusInfinity(self, num=2, delay=0.08):
        # self.config.output = 'PC'
        # drive lens to endstop
        self.config.manualfocusdrive = 'Far 3'
        time.sleep(0.08)
        # and two medium steps back
        self.config.manualfocusdrive = 'Near 2'
        time.sleep(0.08)
        self.config.manualfocusdrive = 'Near 2'
        time.sleep(0.08)
        # self.config.output = 'Undefined'

    @property
    def config(self):
        return self._camera.config

    @property
    def data(self):
        return self._camera.data

    @property
    def serial_num(self):
        return self._camera.config.eosserialnumber
