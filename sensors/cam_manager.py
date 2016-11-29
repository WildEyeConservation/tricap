# coding=utf-8
""" D Joubert 16 November 2016 - Camera managers for Tricap app"""

# TODO Wrong place, but the overall logger should be attached to the session logger, so that those
# error messages get captured to the session folder as well. Or maybe separately, so you can still
# read the alti messages?

# TODO Settings page should show warning for all incorrectly formatted settings

import threading
import time
import logging

from config import CAM_MANAGER_STATES, DEFAULT_IMAGE_CAPTURE_INTERVAL
from config import RET_OK, RET_ERROR
from .cameras import Camera


class TriCapCamsManager(object):
    """TriCapCamsManager manages TriCap camera objects"""
    supportedCameras = {"Canon EOS 6D", "Dummy Cam"}
    _logger = logging.getLogger(__name__)

    def __init__(self):
        self.state = CAM_MANAGER_STATES.STOPPED

        self._capture_thread = None
        self._kill_pill = None
        self._image_capture_interval = None

        self._cameras = None
        self._cam_threads = None
        self._capture_thread = None
        self._image_capture_interval = None
        self._kill_pill = None

        self._initialise()

    def _initialise(self):
        self._find_cameras()

        # clear the threads
        self._cam_threads = []
        self._capture_thread = None

        # TODO This should be read from the init config file
        self._image_capture_interval = DEFAULT_IMAGE_CAPTURE_INTERVAL

    def set_image_capture_interval(self, interval):
        if isinstance(interval, str):
            interval = float(interval)

        self._image_capture_interval = interval

        return RET_OK

    def is_cam_image_fresh(self, cam_num):
        return self._cameras[cam_num].is_cam_image_fresh()

    def get_cam_image_fp(self, cam_num):
        return self._cameras[cam_num].get_cam_image_fp()

    def get_image_capture_interval(self):
        return self._image_capture_interval

    def get_cameras_as_list(self):
        return self._cameras

    def _find_cameras(self):
        self._cameras = []

        try:
            for name, address in Camera.autodetect():
                if name in TriCapCamsManager.supportedCameras:
                    self._logger.info('Adding camera %s at address %s ' % (name, address))
                    tricap_cam = Camera(address)
                    self._cameras.append(tricap_cam)
        except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
            self._logger.error("_find_cameras failed.", exc_info=True)
            return RET_ERROR

        return RET_OK

    def reset(self):
        if self.state == CAM_MANAGER_STATES.STARTED:
            self.stop_capturing()

        self._initialise()

    def _cap_thread_generator(self):
        for index, cam in enumerate(self._cameras):
            thread = threading.Thread(target=cam.capture,
                                      args=[index])
            yield thread

    def _start_capture_with_wait_thread(self):
        # define a worker function to run in a separate thread
        def worker(stop_event):
            # TODO How long do we need to wait for a stop event? Is there another way to do this?
            while not stop_event.wait(0.01):
                prev_time = time.time()

                cam_threads = list(self._cap_thread_generator())
                for t in cam_threads:
                    t.start()
                for t in cam_threads:
                    t.join()

                current_time_diff = time.time() - prev_time

                self._logger.debug('Capture time: ' + str(current_time_diff))
                if current_time_diff < self._image_capture_interval:
                    time.sleep(self._image_capture_interval - current_time_diff)

        self._capture_thread = threading.Thread(target=worker, args=[self._kill_pill])
        self._capture_thread.start()

    def start_capturing(self):
        if len(self._cameras) == 0:
            self.state = CAM_MANAGER_STATES.ERROR_NO_CAMS
        elif self.state == CAM_MANAGER_STATES.STOPPED:
            self._kill_pill = threading.Event()
            self._start_capture_with_wait_thread()
            self.state = CAM_MANAGER_STATES.STARTED

    def stop_capturing(self):
        if self.state == CAM_MANAGER_STATES.STARTED:
            self._kill_pill.set()
            self._capture_thread.join()
            self.state = CAM_MANAGER_STATES.STOPPED

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

    def get_choices_for_setting(self, config_str):
        choices = None

        if self.get_num_cams() > 0:
            choices = self._cameras[0].get_choices_for_setting(config_str)

        return choices

    def get_setting(self, setting_str):
        # TODO I don't like throwing an exception for every value that is not from the camera
        if setting_str == 'image_capture_interval':
            return self._image_capture_interval
        return self._cameras[0].get_setting(setting_str)

    def set_setting(self, setting_str, val_str):
        if setting_str == 'image_capture_interval':
            self._image_capture_interval = float(val_str)
            return RET_OK

        ret_val = RET_OK
        for camera in self._cameras:
            if camera.set_setting(setting_str, val_str) != RET_OK:
                ret_val = RET_ERROR
        return ret_val
