# coding=utf-8
"""D Joubert - 16 November 2016 - Test the tricap camera"""

import logging
import os
import unittest
from time import sleep

from config import CAMERA_STATES, SERVER_LOG_DIR, RET_OK, RET_ERROR
from sensors.gphoto_cam import GPhotoCam
from sensors.configure import TricapConfig


class TestBaseCanon6DCam(unittest.TestCase):
    logger = logging.getLogger('test_canon6d_log')
    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    formatter = logging.Formatter(format_str)
    log_fp = os.path.join(SERVER_LOG_DIR, 'test_canon6d.log')
    handler = logging.FileHandler(filename=log_fp)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    rootlogger = logging.getLogger('')
    rootlogger.addHandler(handler)
    rootlogger.setLevel(logging.DEBUG)

    def setUp(self):
        for name, address in GPhotoCam.autodetect():
            if name == "Canon EOS 6D":
                self._address = address
                break

        self.cam_settings = TricapConfig().get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)


class TestDeviceCanon6DCam(TestBaseCanon6DCam):
    def test_init(self):
        cam = GPhotoCam(self._address, self.cam_settings)

        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)

    def test_set_shutter_speed(self):
        cam = GPhotoCam(self._address, self.cam_settings)

        cam.set_setting('shutterspeed', '1/640')
        self.assertEqual(cam.get_setting('shutterspeed'), '1/640')

        with self.assertRaises(ValueError):
            cam.set_setting('shutterspeed', '1/X')

    def test_capture_func(self):
        cam = GPhotoCam(self._address, self.cam_settings)
        self.assertEqual(cam.is_cam_image_fresh(), False)
        cam.capture(0)
        self.assertEqual(cam.is_cam_image_fresh(), True)

    def test_setting_iso(self):
        cam = GPhotoCam(self._address, self.cam_settings)
        cam.set_setting('iso', '100')
        self.assertEqual(cam.get_setting('iso'), '100')
        cam.set_setting('iso', '200')
        self.assertEqual(cam.get_setting('iso'), '200')

    def test_get_choices_for_iso(self):
        cam = GPhotoCam(self._address, self.cam_settings)
        choices = cam.get_choices_for_setting('iso')
        self.assertEqual('100' in choices, True)
        self.assertEqual('200' in choices, True)


class TestInteractiveCanon6DCam(TestBaseCanon6DCam):
    def test_cable_remove(self):
        input('Press enter to conduct cable remove test')
        cam = GPhotoCam(self._address, self.cam_settings)
        thread_worker = cam.capture
        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)

        print('Remove the cable - you have 2 seconds')
        sleep(2)
        self.assertEqual(thread_worker(0), RET_ERROR)
