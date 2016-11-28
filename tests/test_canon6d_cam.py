# coding=utf-8
"""D Joubert - 16 November 2016 - Test the tricap camera"""

import logging
import os
import threading
import unittest
from time import sleep

from config import CAMERA_STATES, SERVER_LOG_DIR, RET_OK, RET_ERROR
from sensors.cameras import GPhotoCam


class TestBaseCanon6DCam(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger('test_canon6d_log')
        format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
        formatter = logging.Formatter(format_str)
        log_fp = os.path.join(SERVER_LOG_DIR, 'test_canon6d.log')
        handler = logging.FileHandler(filename=log_fp)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)

        for name, address in GPhotoCam.autodetect():
            if name == "Canon EOS 6D":
                self._address = address
                break


class TestDeviceCanon6DCam(TestBaseCanon6DCam):
    def test_init(self):
        cam = GPhotoCam(self._address, self.logger)

        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)

    def test_set_shutter_speed(self):
        cam = GPhotoCam(self._address, self.logger)

        self.assertEqual(cam.set_setting('shutterspeed', '1/640'), RET_OK)
        self.assertEqual(cam.get_setting('shutterspeed'), '1/640')

        self.assertEqual(cam.set_setting('shutterspeed', '1/X'), RET_ERROR)
        self.assertEqual(cam.get_setting('shutterspeed'), '1/640')

    def test_capture_func(self):
        cam = GPhotoCam(self._address, self.logger)
        thread_worker = cam.create_single_capture_func()
        self.assertEqual(thread_worker(0), RET_OK)

    def test_cap_func_as_thread(self):
        cam = GPhotoCam(self._address, self.logger)
        thread = threading.Thread(target=cam.create_single_capture_func(),
                                  args=[0])
        thread.start()
        thread.join()
        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)

    def test_setting_iso(self):
        cam = GPhotoCam(self._address, self.logger)
        cam.set_setting('iso', '100')
        self.assertEqual(cam.get_setting('iso'), '100')
        cam.set_setting('iso', '200')
        self.assertEqual(cam.get_setting('iso'), '200')

    def test_get_choices_for_iso(self):
        cam = GPhotoCam(self._address, self.logger)
        choices = cam.get_choices_for_setting('iso')
        self.assertEqual('100' in choices, True)
        self.assertEqual('200' in choices, True)


class TestInteractiveCanon6DCam(TestBaseCanon6DCam):
    def test_cable_remove(self):
        input('Press enter to conduct cable remove test')
        cam = GPhotoCam(self._address, self.logger)
        thread_worker = cam.create_single_capture_func()
        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)

        print('Remove the cable - you have 2 seconds')
        sleep(2)
        self.assertEqual(thread_worker(0), RET_ERROR)
