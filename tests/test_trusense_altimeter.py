""" D Joubert 16 November 2016 - Unit and interactive test for the TruSense S100 Altimeter"""

import unittest
import logging
import os
import tempfile
import shutil

from time import sleep

from sensors.trusense_altimeter import TrusenseAltimeter, AltiError

from support.session_logger import SessionLogger

from config import ALTIMETER_STATE, SERVER_LOG_DIR


class TestDeviceTruSense(unittest.TestCase):
    logger = logging.getLogger('test_alti_logger')
    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    formatter = logging.Formatter(format_str)
    log_fp = os.path.join(SERVER_LOG_DIR, 'test_alti.log')
    handler = logging.FileHandler(filename=log_fp)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    rootlogger = logging.getLogger('')
    rootlogger.addHandler(handler)
    rootlogger.setLevel(logging.DEBUG)

    def setUp(self):
        self.logger = TestDeviceTruSense.logger
        self.tempdir = tempfile.mkdtemp()
        self.session_logger = SessionLogger(root_folder=self.tempdir)
        self.session_logger.create_new_session()

    def tearDown(self):
        for root, _, filenames in os.walk(self.tempdir):
            for filename in filenames:
                os.remove(os.path.join(root, filename))

        shutil.rmtree(self.tempdir)

    def test_initialization(self):
        self.logger.info("Starting test init")
        alti = TrusenseAltimeter(self.session_logger)
        self.assertEqual(alti.state, ALTIMETER_STATE.CONNECTED)
        self.assertEqual(alti.measurement, None)
        self.logger.info("Done with test init")

    def test_reset(self):
        self.logger.info("Starting test reset")
        # TODO Need to elaborate on this test, probably check that some setting is back to default
        alti = TrusenseAltimeter(self.session_logger)
        alti.reset()
        self.assertEqual(alti.state, ALTIMETER_STATE.CONNECTED)
        self.logger.info("Done with test reset")

    def test_disconnect(self):
        self.logger.info("Starting test disc")
        alti = TrusenseAltimeter(self.session_logger)
        alti.disconnect()
        self.assertEqual(alti.state, ALTIMETER_STATE.NOT_CONNECTED)
        self.logger.info("Done with test disc")

    def test_notfound(self):
        def init_invalid():
            return TrusenseAltimeter(self.session_logger, supported_devices={(1659, 8964)})

        self.assertRaises(AltiError, init_invalid)

    def test_invalid_command(self):
        alti = TrusenseAltimeter(self.session_logger)
        self.assertRaises(AltiError, alti._write, "HAN", "Expected Error")

    def test_measuring(self):
        self.logger.info("Starting test meas")
        alti = TrusenseAltimeter(self.session_logger)
        self.assertEqual(alti.config.num_frames_to_avg.choices, None)
        self.assertEqual(str(alti.config), "['measurement_timeout', 'num_frames_to_avg']")
        self.assertEqual(dir(alti.config), ['measurement_timeout', 'num_frames_to_avg'])
        self.assertEqual(alti.config.num_frames_to_avg, 2)
        self.assertEqual(str(alti.config.num_frames_to_avg), '2')
        alti.config.num_frames_to_avg = 1
        self.assertEqual(alti.config.num_frames_to_avg, 1)

        def set_invalid_setting():
            alti.config.num_frames_to_avg_ = 2

        self.assertRaises(Exception, set_invalid_setting)
        alti.start_measuring()
        sleep(5)
        self.assertEqual(alti.state, ALTIMETER_STATE.MEASURING)
        self.assertNotEqual(alti.measurement, None)
        alti.reset()
        sleep(2)
        self.assertEqual(alti.state, ALTIMETER_STATE.CONNECTED)
        self.assertEqual(alti.get_state_as_string(), "CONNECTED")
        self.assertEqual(alti.config.num_frames_to_avg, 2)
        self.assertEqual(alti.state, ALTIMETER_STATE.CONNECTED)
        self.logger.info("Done with test meas")

    def test_timeout(self):
        alti = TrusenseAltimeter(self.session_logger)
        # This causes the alti to accept commands and echo OK, but go silent when measurement is started
        alti.config.num_frames_to_avg = -1
        alti.start_measuring()
        self.assertEqual(alti.state, ALTIMETER_STATE.MEASURING)
        sleep(6)
        self.assertEqual(alti.state, ALTIMETER_STATE.ERROR)
