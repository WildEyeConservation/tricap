# coding=utf-8
import threading

from enum import IntEnum
from abc import ABC, abstractmethod
from datetime import datetime


class CameraException(Exception):
    pass

CamConfigType = IntEnum("CamConfigType",
                        {"Window": 0, "Section": 1, "Text": 2, "Range": 3, "Toggle": 4, "Radio": 5, "Menu": 6,
                         "Button": 7, "Date": 8})


class AbstractCamera(ABC):
    """Abstract base class for all camera objects."""

    def __init__(self, address, settings):
        """Constructor, requires address and camera settings dict."""
        self.rate_fp = 'Does/Not/Exist.txt'
        self._rate_file = None

    def init_rate_file_if_needed(self):
        """Initialise the rate file, not done during construction to allow path manipulation."""
        if self._rate_file is None:
            self._rate_file = open(self.rate_fp, 'w')

    def record_timestamp_to_rate_file(self, descriptor: str = 'timestamp'):
        """Record the timestamp to the rate file."""
        self.init_rate_file_if_needed()
        self._rate_file.write('%s : %s\n' % (str(datetime.now()), descriptor))
        self._rate_file.flush()

    @abstractmethod
    def is_cam_image_fresh(self):
        pass

    @staticmethod
    @abstractmethod
    def autodetect():
        pass

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def capture(self, continuous=False, barrier: threading.Barrier = None):
        pass

    @abstractmethod
    def get_state_as_string(self):
        pass

    @abstractmethod
    def get_cam_image_count(self):
        pass
