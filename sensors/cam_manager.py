# coding=utf-8
""" D Joubert 16 November 2016 - Camera managers for Tricap app"""

# TODO Settings page should show warning for all incorrectly formatted settings

import logging
import threading

from config import CAM_MANAGER_STATES

# TODO : Create a camera factory that will import cameras according to its config and make them available via its own
# autodetect function

try:
    from .canon_6D import Canon6DCam
    from .gphoto_cam import GPhotoCam as Camera
except ImportError:
    logging.getLogger(__name__).warning('Could not import gphoto based libs.')
    
from .dummy_cam import DummyCam
from .dummy_cam import DummyShell


class MultiConfig:
    dictkeys = ["_cameras", "_context"]

    def __init__(self, cameras):
        self._cameras = cameras

    def __setattr__(self, key, value):
        if key in self.dictkeys:
            self.__dict__[key] = value
        else:
            for camera in self._cameras:
                camera.config[key] = value

    def __getattr__(self, key):
        if key in self.dictkeys:
            return self.__dict__[key]
        else:
            return self._cameras[0].config[key]

    __setitem__ = __setattr__
    __getitem__ = __getattr__

    def get_tree(self):
        return self._cameras[0].config.get_tree()


class TriCapCamsManager:
    """TriCapCamsManager manages TriCap camera objects"""
    supportedCameras = {"Canon EOS 6D", "Dummy Cam"}
    _logger = logging.getLogger(__name__)

    def __init__(self, man_settings: dict, cam_settings: dict, use_dummy_cams=False):
        self.state = CAM_MANAGER_STATES.STOPPED

        self._capture_thread = None
        self._kill_pill = None

        self._cameras = None
        self._cam_threads = None
        self._capture_thread = None
        self._kill_pill = None
        self._cam_settings = cam_settings
        self._man_settings = man_settings        
        self.use_dummy_cams = use_dummy_cams
        self._initialise()

    def _initialise(self):
        self._find_cameras()

        # clear the threads
        self._cam_threads = []
        self._capture_thread = None

        self._image_capture_interval = float(self._man_settings['image_capture_interval'])

    def is_cam_image_fresh(self, cam_num):
        return self._cameras[cam_num].is_cam_image_fresh()

    def get_data(self, cam_num):
        return self._cameras[cam_num].data

    def get_cam_image_fp(self, cam_num):
        return self._cameras[cam_num].get_cam_image_fp()

    def get_cameras_as_list(self):
        return self._cameras

    def _find_cameras(self):
        self._cameras = []
        # Do not catch exceptions here. If any detected camera fails to instantiate, it is a critical error and we want
        # to halt and catch fire.

        if self.use_dummy_cams:
            for name, address in DummyCam.autodetect():
                if name in TriCapCamsManager.supportedCameras:
                    self._logger.info('Adding camera %s at address %s ' % (name, address))
                    tricap_cam = DummyShell(DummyCam(address, self._cam_settings))
                    self._cameras.append(tricap_cam)	
        else:
            for name, address in Camera.autodetect():
                if name in TriCapCamsManager.supportedCameras:
                    self._logger.info('Adding camera %s at address %s ' % (name, address))
                    tricap_cam = Canon6DCam(Camera(address, self._cam_settings))
                    self._cameras.append(tricap_cam)

    def reset(self, man_settings: dict, cam_settings: dict):
        self._man_settings = man_settings
        self._cam_settings = cam_settings

        if self.state == CAM_MANAGER_STATES.STARTED:
            self.stop_capturing()

        self._initialise()

    def start_capturing(self):
        if len(self._cameras) == 0:
            self.state = CAM_MANAGER_STATES.ERROR_NO_CAMS
        elif self.state == CAM_MANAGER_STATES.STOPPED:
            barrier = threading.Barrier(len(self._cameras))
            self._kill_pill = threading.Event()
            for cam in self._cameras:
                thread = threading.Thread(target=cam.capture, daemon=True,
                                          kwargs={"continuous": True, "barrier": barrier,
                                                  "stop_event": self._kill_pill})
                thread.start()
            self.state = CAM_MANAGER_STATES.STARTED

    def stop_capturing(self):
        if self.state == CAM_MANAGER_STATES.STARTED:
            self._kill_pill.set()
            self.state = CAM_MANAGER_STATES.STOPPED

    def get_image_capture_interval(self):
        return self._man_settings['image_capture_interval']

    def set_image_capture_interval(self, value):
        self._man_settings['image_capture_interval'] = value

    def get_num_cams(self):
        return len(self._cameras)

    def get_cam_ids(self):
        cam_ids = []
        for cam in self._cameras:
            if cam.serial_num is not None:
                cam_ids.append(cam.serial_num)
            else:
                cam_ids.append('Unknown')
        return cam_ids

    @property
    def config(self):
        return MultiConfig(self._cameras)
