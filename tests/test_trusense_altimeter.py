""" D Joubert 16 November 2016 - Unit and interactive test for the TruSense S100 Altimeter"""

import unittest
import logging
import os
import tempfile
import shutil

from time import sleep

from sensors.trusense_altimeter import TrusenseAltimeter
from sensors.session_logger import SessionLogger

from config import ALTIMETER_STATE, SERVER_LOG_DIR

class TestDeviceTruSense(unittest.TestCase):

    logger = logging.getLogger('test_alti_logger')
    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    formatter = logging.Formatter(format_str)
    log_fp = os.path.join(SERVER_LOG_DIR, 'test_alti.log')
    handler = logging.FileHandler(filename=log_fp)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    def setUp(self):
        self.logger=TestDeviceTruSense.logger
        self.tempdir = tempfile.mkdtemp()
        self.session_logger = SessionLogger(root_folder = self.tempdir)
        self.session_logger.create_new_session()

    def tearDown(self):
        for root, _, filenames in os.walk(self.tempdir):
            for filename in filenames:
                os.remove(os.path.join(root, filename))

        shutil.rmtree(self.tempdir)

    def test_initialization(self):
        self.logger.info("Starting test init")
        alti = TrusenseAltimeter(self.logger, self.session_logger)
        self.assertEqual(alti.state, ALTIMETER_STATE.CONNECTED)
        self.logger.info("Done with test init")

    def test_reset(self):
        self.logger.info("Starting test reset")
        # TODO Need to elaborate on this test, probably check that some setting is back to default
        alti = TrusenseAltimeter(self.logger, self.session_logger)
        alti.reset()
        self.assertEqual(alti.state, ALTIMETER_STATE.CONNECTED)
        self.logger.info("Done with test reset")

    def test_disconnect(self):
        self.logger.info("Starting test disc")
        alti = TrusenseAltimeter(self.logger, self.session_logger)
        alti.disconnect()
        self.assertEqual(alti.state, ALTIMETER_STATE.NOT_CONNECTED)
        self.logger.info("Done with test disc")

    def test_measuring(self):
        self.logger.info("Starting test meas")
        alti = TrusenseAltimeter(self.logger, self.session_logger)
        alti.start_measuring()
        sleep(2)
        self.assertEqual(alti.state, ALTIMETER_STATE.MEASURING)
	# TODO This test should still provide valid result even if the measure plane is too close.
        self.assertNotEqual(alti.measurement, 0)
        alti.stop_measuring()
        sleep(2)
        self.assertEqual(alti.state, ALTIMETER_STATE.CONNECTED)
        self.logger.info("Done with test meas")

        # TODO Test session logger, if it takes the input?

    # TODO Test bad messages, error fallovers
