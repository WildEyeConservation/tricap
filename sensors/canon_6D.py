"""A shell for GPhotoCam, implementing properties required specifically for the Canon EOS 6D."""

import time


class Canon6DCam():
    """Canon EOS 6D shell for the gphoto2 cam."""

    def __init__(self, camera_driver):
        """Constructor."""
        self._camera = camera_driver
        # self.config.output = 'Off'  # Do not be in live mode
        self.config.drivemode = 'Single'
        self.config.reviewtime = 'None'
        self.config.imageformat = 'RAW'
        self.capture = self._camera.capture
        self.capture_and_download = self._camera.capture_and_download
        self.get_state_as_string = self._camera.get_state_as_string
        self.is_cam_image_fresh = self._camera.is_cam_image_fresh
        self.cpy_images = self._camera.cpy_images
        self.delete_images = self._camera.delete_images

    def focus_infinity(self):
        """Change the focus of the lens to infinity using series of manual focus events."""
        if self.serial_num == '413051000325':
            print("Focus!")
            self.config.output = 'PC'
            # drive lens to endstop
            self.config.manualfocusdrive = 'Far 3'
            time.sleep(0.08)
            # and two medium steps back
            self.config.manualfocusdrive = 'Near 2'
            time.sleep(0.08)
            self.config.manualfocusdrive = 'Near 2'
            time.sleep(0.08)
            self.config.output = 'Undefined'

    @property
    def config(self):
        return self._camera.config

    @property
    def data(self):
        return self._camera.data

    @property
    def serial_num(self):
        return self._camera.config.eosserialnumber

    def get_cam_image_count(self):
        return self._camera.get_cam_image_count()

    @property
    def state(self):
        return self._camera.state

    def get_camera_context(self):
        return self._camera.get_cam_context()

    def get_camera(self):
        return self._camera.get_cam()
