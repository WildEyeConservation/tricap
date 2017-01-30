# coding=utf-8
import threading
import logging
import os

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
        self.rate_fp = 'Does/Not/Exist/Error.txt'
        self._rate_logger = None

        # TODO This is bad OOP Code, fix this!
        self.calibrate_func = None
        self.calibrate_timing = 0

    def init_rate_file_if_needed(self):
        """Initialise the rate file, not done during construction to allow path manipulation."""

        if self._rate_logger is None:
            format_str = "%(asctime)s : %(message)s "
            handler = logging.FileHandler(filename=self.rate_fp)
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(logging.Formatter(format_str))
            self._rate_logger = logging.getLogger(self.rate_fp)
            self._rate_logger.propagate = False  # prevent rate messages from popping up in root log
            self._rate_logger.addHandler(handler)
            self._rate_logger.info('Rate Logging Started')
            fp, filename = os.path.split(self.rate_fp)
            logging.getLogger().info('Rate logging started for a camera at %s.', filename)

    def record_timestamp_to_rate_file(self, descriptor: str = 'timestamp'):
        """Record the timestamp to the rate file."""
        self.init_rate_file_if_needed()
        self._rate_logger.info('%d : %s' % (self.get_cam_image_count(), descriptor))
        # self._rate_file.write('%d : %s : %s\n' % (self.get_cam_image_count(), str(datetime.now()), descriptor))
        # self._rate_file.flush()

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
