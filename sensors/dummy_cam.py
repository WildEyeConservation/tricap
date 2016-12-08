# coding=utf-8
import os
import pickle
import threading
import time
from collections import namedtuple
from glob import glob

from anytree import PreOrderIter, RenderTree

from config import CAMERA_STATES
from .abstract_cam import AbstractCamera, CameraException
from .base_setting import BaseSetting, SettingSpec

# TODO Implement a Windows Canon6DCam, which uses the Canon EDSDK to communicate with the camera
# TODO Have the DummyCam load variables from the config file, like the normal camera would
CameraSpec = namedtuple("cam", ["name", "model"])


class DummyConfig:
    dictkeys = ["_tree"]

    def __init__(self, tree):
        self._tree = tree

    def __repr__(self):
        return str(RenderTree(self._tree))

    def __dir__(self):
        return [node.name for node in PreOrderIter(self.get_tree()) if node.is_leaf]

    def _get_child_by_name(self, key):
        config_widget = [widget for widget in PreOrderIter(self._tree)
                         if widget.name == key and widget.is_leaf]
        if len(config_widget) != 1:
            raise CameraException("%s does not uniquely identify a single item" % key)

        def set_value(value):
            config_widget[0].value = value

        set_spec = SettingSpec(choices=config_widget[0].choices,
                               set_value=set_value,
                               get_value=lambda: config_widget[0].value)
        return BaseSetting(set_spec)

    def __setattr__(self, key, value):
        if key in DummyConfig.dictkeys:
            self.__dict__[key] = value
        else:
            config_widget = self._get_child_by_name(key)
            config_widget.set(str(value))

    def __getattr__(self, key):
        return self._get_child_by_name(key)

    __setitem__ = __setattr__
    __getitem__ = __getattr__

    def get_tree(self):
        return self._tree


class DummyCam(AbstractCamera):
    """ Serves as a fake camera for testing purposes."""

    cameras = [CameraSpec(name="Dummy Cam", model=None) for i in range(3)]

    @staticmethod
    def configure(cameras):
        DummyCam.cameras = cameras

    @staticmethod
    def autodetect():
        return [(cam.name, index) for index, cam in enumerate(DummyCam.cameras)]

    def __init__(self, address, settings=None):
        super().__init__(address, settings)
        if settings is None:
            settings = {}
        self.state = CAMERA_STATES.INITIALISED
        # TODO : Check if this camera has already been claimed and raise an exception.
        self._camera = DummyCam.cameras[address]
        cam_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '../camModels/Canon 6D - 023052000180.pkl')
        with open(cam_file, 'rb') as f:
            self._model = pickle.load(f)
        self._config = DummyConfig(self._model)
        self._fresh_capture = False
        self._address = address  # if we ever want to do anything with this later
        fnames = glob(os.path.join(os.path.dirname(__file__), '..', 'camModels', 'captureSequence', '*.jpg'))
        # TODO : raise an exception if this list does not contain at least 2 images
        self._imgs = []
        self._counter = 0
        self.data = None
        self.serial_num = 0
        for filename in fnames:
            with open(filename, 'rb') as f:
                self._imgs.append(f.read())

        for setting_name, setting_value in settings.items():
            self.config[setting_name] = setting_value

    @property
    def config(self):
        return self._config

    def reset(self, settings=None):
        self.__init__(self._address, settings)

    def is_cam_image_fresh(self):
        cache = self._fresh_capture
        self._fresh_capture = False
        return cache

    def get_state_as_string(self):
        return self.state.name

    def capture(self, continuous=False, barrier: threading.Barrier = None, stop_event=None):
        while True:
            if stop_event:
                if stop_event.is_set():
                    return
            self.state = CAMERA_STATES.CAPTURING
            time.sleep(1)
            if barrier:
                barrier.wait()
            self._counter += 1
            self.data = self._imgs[self._counter % len(self._imgs)]
            self._fresh_capture = True
            self.state = CAMERA_STATES.INITIALISED
            if not continuous:
                return
