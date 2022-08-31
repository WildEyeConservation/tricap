"""Abstract Camera class definition and other classes and definitions to be used by cameras."""

import threading
import logging
import os

from enum import IntEnum
from abc import ABC, abstractmethod
from support.basic import Subject


class CameraException(Exception):
    """Exception to be raised if there is a problem with the camera."""

    pass


CamConfigType = IntEnum("CamConfigType",
                        {"Window": 0, "Section": 1, "Text": 2, "Range": 3, "Toggle": 4, "Radio": 5, "Menu": 6,
                         "Button": 7, "Date": 8})


class AbstractCamera(Subject):
    """Abstract base class for all camera objects.

    Inherits from Subject the ability to notify subscribers of whatever you want.
    """

    def __init__(self, address, settings):
        """Constructor, requires address and camera settings dict."""
        super(AbstractCamera, self).__init__()

        # TODO This is bad OOP Code, fix this!
        self.calibrate_timing = 0

        self.fetch_state = False

        self.update_message = 'Camera observer update message.'

    def calibrate_func(self):
        """Run some kind of calibration."""
        pass

    @abstractmethod
    def is_cam_image_fresh(self):
        """Return true if the image data is new."""
        pass

    @staticmethod
    @abstractmethod
    def autodetect():
        """Find connected cameras."""
        pass

    # @abstractmethod
    # def reset(self):
    #     """Reset the camera, reload the settings."""
    #     pass

    @abstractmethod
    def capture(self, continuous=False, barrier: threading.Barrier = None):
        """Capture an image, typically used by a threading function."""
        pass

    @abstractmethod
    def capture_and_read_exif(self):
        """Capture an image and download it to a target folder."""
        pass

    @abstractmethod
    def get_state_as_string(self):
        """Return the state of the camera as a string."""
        pass

    @abstractmethod
    def get_cam_image_count(self):
        """Get the number of images captured up to this point."""
        pass
