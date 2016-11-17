""" D Joubert 16 November 2016 - Unit and interactive test for the TruSense S100 Altimeter"""

import unittest
import logging
import os

from time import sleep

from sensors.trusense_altimeter import TrusenseAltimeter

from config import ALTIMETER_STATE, SERVER_LOG_DIR

class TestDeviceTruSense(unittest.TestCase):

    def setUp(self):
        self.logger = logging.getLogger('test_alti_logger')
        format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
        formatter = logging.Formatter(format_str)
        log_fp = os.path.join(SERVER_LOG_DIR, 'test_alti.log')
        handler = logging.FileHandler(filename=log_fp)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def test_initialization(self):
        alti = TrusenseAltimeter(self.logger)
        self.assertEqual(alti.state, ALTIMETER_STATE.CONNECTED)

    def test_reset(self):
        # TODO Need to elaborate on this test, probably check that some setting is back to default
        alti = TrusenseAltimeter(self.logger)
        alti.reset()
        self.assertEqual(alti.state, ALTIMETER_STATE.CONNECTED)

    def test_disconnect(self):
        alti = TrusenseAltimeter(self.logger)
        alti.disconnect()
        self.assertEqual(alti.state, ALTIMETER_STATE.NOT_CONNECTED)

    def test_measuring(self):
        alti = TrusenseAltimeter(self.logger)
        alti.start_measuring()
        sleep(2)
        self.assertEqual(alti.state, ALTIMETER_STATE.MEASURING)
        self.assertNotEqual(alti.measurement, 0)
        alti.stop_measuring()
        sleep(2)
        self.assertEqual(alti.state, ALTIMETER_STATE.CONNECTED)

    # TODO Test bad messages, error fallovers
