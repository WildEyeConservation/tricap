# coding=utf-8
"""D Joubert - 16 November 2016 - Test the tricap camera"""

import logging
import os
import unittest
from time import sleep
import threading
from anytree import RenderTree

from config import CAMERA_STATES, SERVER_LOG_DIR, RET_OK, RET_ERROR
from sensors.gphoto_cam import GPhotoCam
# from sensors.dummy_cam import DummyCam as GPhotoCam
from support.configure import TricapConfig


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
            #            if name == "Canon EOS 6D":
            self._address = address
            break
        self.cam_settings = TricapConfig().get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)


class TestDeviceCanon6DCam(TestBaseCanon6DCam):
    def test_init(self):
        cam = GPhotoCam(self._address, self.cam_settings)

        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)

    def test_reinit(self):
        cam = GPhotoCam(self._address, self.cam_settings)

        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)
        cam.reset(self.cam_settings)
        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)
        self.assertEqual(cam.get_state_as_string(), "INITIALISED")

    def test_capture_func(self):
        cam = GPhotoCam(self._address, self.cam_settings)
        self.assertEqual(cam.is_cam_image_fresh(), False)
        cam.capture(0)
        self.assertEqual(cam.is_cam_image_fresh(), True)
        barrier = threading.Barrier(1)
        kill_pill = threading.Event()
        thread = threading.Thread(target=cam.capture, daemon=True,
                                  kwargs={"continuous": True, "barrier": barrier,
                                          "stop_event": kill_pill})
        thread.start()
        sleep(10)
        kill_pill.set()
        thread.join()

    def test_setting_iso(self):
        """Test setting the iso and other settings for the cameras."""
        cam = GPhotoCam(self._address, self.cam_settings)
        cam.config.viewfinder = 1
        cam.config.viewfinder = '0'
        cam.config.iso = '100'
        self.assertEqual(str(cam.config), str(RenderTree(cam.config.get_tree())))
        self.assertEqual(str(cam.config.iso), '100')
        self.assertLess(cam.config.iso, 101)
        self.assertGreater(cam.config.iso, 99)
        self.assertLessEqual(cam.config.iso, 100)
        self.assertGreaterEqual(cam.config.iso, 100)
        self.assertEqual(cam.config.iso, 100)
        self.assertNotEqual(cam.config.iso, 200)
        self.assertLess(cam.config.iso, '101')
        self.assertGreater(cam.config.iso, '099')
        self.assertLessEqual(cam.config.iso, '100')
        self.assertGreaterEqual(cam.config.iso, '100')
        self.assertEqual(cam.config.iso, '100')
        self.assertNotEqual(cam.config.iso, '200')
        cam.config.iso = 200
        self.assertEqual(cam.config.iso, '200')
        cam.config['iso'] = 100
        self.assertEqual(cam.config.iso, 100)
        self.assertIn('iso', dir(cam.config))
        self.assertEqual(cam.config.iso.choices,
                         ['Auto', '100', '125', '160', '200', '250', '320', '400', '500', '640', '800', '1000', '1250',
                          '1600',
                          '2000', '2500', '3200', '4000', '5000', '6400', '8000', '10000', '12800',
                          'Unknown value 0083',
                          'Unknown value 0085', '25600'])

        self.assertEqual(cam.config['iso'].choices,
                         ['Auto', '100', '125', '160', '200', '250', '320', '400', '500', '640', '800', '1000', '1250',
                          '1600',
                          '2000', '2500', '3200', '4000', '5000', '6400', '8000', '10000', '12800',
                          'Unknown value 0083',
                          'Unknown value 0085', '25600'])
        self.assertEqual(cam.config.ownername.choices, None)

        def set_invalid_field():
            cam.config.isoo = 100

        def set_invalid_iso():
            cam.config.iso = 101

        self.assertRaises(Exception, set_invalid_field)
        self.assertRaises(Exception, set_invalid_iso)
