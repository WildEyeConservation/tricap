# coding=utf-8
from enum import IntEnum
from abc import ABC, abstractmethod
import threading


class CameraException(Exception):
    pass

CamConfigType = IntEnum("CamConfigType",
                        {"Window": 0, "Section": 1, "Text": 2, "Range": 3, "Toggle": 4, "Radio": 5, "Menu": 6,
                         "Button": 7, "Date": 8})


class AbstractCamera(ABC):
    """ Handler for the Canon EOS 6D Camera. Uses gphoto2 to handle the actual communication. """

    @abstractmethod
    def __init__(self, address, settings):
        pass

    @abstractmethod
    def is_cam_image_fresh(self):
        pass

    @staticmethod
    @abstractmethod
    def autodetect():
        pass

    @abstractmethod
    def get_config_tree(self):
        pass

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def get_choices_for_setting(self, config_str):
        pass

    @abstractmethod
    def capture(self, continuous=False, barrier: threading.Barrier = None):
        pass

    @abstractmethod
    def get_state_as_string(self):
        pass
