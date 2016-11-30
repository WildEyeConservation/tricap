# coding=utf-8
import time
from collections import namedtuple

from config import RET_ERROR, RET_OK, CAMERA_STATES, DUMMY_IMAGE_PATH

# TODO Implement a Windows Canon6DCam, which uses the Canon EDSDK to communicate with the camera
# TODO Have the DummyCam load variables from the config file, like the normal camera would
CameraSpec = namedtuple("cam", ["name", "serial_number"])


class DummyCam(object):
    """ Serves as a fake camera for testing purposes."""

    cameras = [CameraSpec(name="Dummy Cam", serial_number=i) for i in range(3)]

    @staticmethod
    def configure(cameras):
        DummyCam.cameras = cameras

    @staticmethod
    def autodetect():
        return [(cam.name, index) for index, cam in enumerate(DummyCam.cameras)]

    def __init__(self, address, settings):
        self.state = CAMERA_STATES.INITIALISED
        self.serial_num = DummyCam.cameras[address].serial_number
        self._fresh_capture = False
        self._address = address  # if we ever want to do anything with this later
        self._settings_dict = settings
        for setting_name, setting_value in settings:
            self._set_config_value_by_string(setting_name, setting_value)

    def reset(self):
        self.state = CAMERA_STATES.INITIALISED

    def is_cam_image_fresh(self):
        return self._fresh_capture

    def get_cam_image_fp(self):
        self._fresh_capture = False
        return DUMMY_IMAGE_PATH

    @staticmethod
    def get_state_as_string():
        return "Base Cam has no state."

    def set_setting(self, setting_str, setting_val):
        self._settings_dict[setting_str] = setting_val
        return RET_OK

    def get_setting(self, setting_str):
        if setting_str in self._settings_dict.keys():
            return self._settings_dict[setting_str]
        else:
            return None

    @staticmethod
    def get_choices_for_setting(setting_str):
        # just a couple of hard coded ones
        if setting_str == 'shutterspeed':
            return ['1/4', '1/640', '1/2500']
        elif setting_str == 'iso':
            return ['100', '200', '500']
        else:
            return None

    def capture(self):
        if self.state == CAMERA_STATES.INITIALISED:
            self.state = CAMERA_STATES.CAPTURING
            # prepare the small jpeg filename
            time.sleep(1)
            self._fresh_capture = True
            self.state = CAMERA_STATES.INITIALISED
            return RET_OK
        else:
            return RET_ERROR
