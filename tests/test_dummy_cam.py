# coding=utf-8
"""D Joubert - 16 November 2016 - Test the tricap camera"""

import logging
import os
import unittest

from config import CAMERA_STATES, SERVER_LOG_DIR, RET_OK, RET_ERROR
from sensors.configure import TricapConfig
from sensors.dummy_cam import DummyCam, CameraSpec
import pickle

class TestBaseDummyCam(unittest.TestCase):
    logger = logging.getLogger('test_dummy_log')
    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    formatter = logging.Formatter(format_str)
    log_fp = os.path.join(SERVER_LOG_DIR, 'test_dummy.log')
    handler = logging.FileHandler(filename=log_fp)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    rootlogger = logging.getLogger('')
    rootlogger.addHandler(handler)
    rootlogger.setLevel(logging.DEBUG)

class TestDummyCam(TestBaseDummyCam):
    def test_dummy(self):
        settings = TricapConfig().get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
        for name, address in DummyCam.autodetect():
            self.assertEqual(name, "Dummy Cam")

        camFile = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../camModels/Canon 6D - 023052000180.pkl')
        with open(camFile, 'rb') as f:
            Canon6Dmodel = pickle.load(f)

        camNames = ["Dummy Cam %d" % i for i in range(3)]
        camSpecs = [CameraSpec(name=_name, model=Canon6Dmodel) for i, _name in enumerate(camNames)]
        DummyCam.configure(camSpecs)

        allNames = []
        for ((name, address), spec) in zip(DummyCam.autodetect(), camSpecs):
            allNames.append(name)
            cam = DummyCam(address, settings)

        self.assertEqual(allNames, camNames)

        # def test_init(self):
        #     cam = DummyCam(self._address)
        #     self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)
        #
        # def test_set_shutter_speed(self):
        #     cam = DummyCam(self._address)
        #
        #     self.assertEqual(cam.set_setting('shutterspeed', '1/640'), RET_OK)
        #     self.assertEqual(cam.get_setting('shutterspeed'), '1/640')
        #
        #     self.assertEqual(cam.set_setting('shutterspeed', '1/X'), RET_ERROR)
        #     self.assertEqual(cam.get_setting('shutterspeed'), '1/640')
        #
        # def test_capture_func(self):
        #     cam = DummyCam(self._address)
        #     self.assertEqual(cam.capture(0), RET_OK)
        #
        # def test_setting_iso(self):
        #     cam = DummyCam(self._address)
        #     cam.set_setting('iso', '100')
        #     self.assertEqual(cam.get_setting('iso'), '100')
        #     cam.set_setting('iso', '200')
        #     self.assertEqual(cam.get_setting('iso'), '200')
        #
        # def test_get_choices_for_iso(self):
        #     cam = DummyCam(self._address)
        #     choices = cam.get_choices_for_setting('iso')
        #     self.assertEqual('100' in choices, True)
        #     self.assertEqual('200' in choices, True)
