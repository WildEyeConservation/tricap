""" D Joubert 18 November 2016 - Innoventix Consulting Test the session logger"""

import unittest
import tempfile
import os
import shutil
import time

from sensors.session_logger import SessionLogger


class TestSessionLogger(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        for root, _, filenames in os.walk(self.tempdir):
            for filename in filenames:
                os.remove(os.path.join(root, filename))

        shutil.rmtree(self.tempdir)

    def test_init(self):
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        expected_fp = os.path.join(self.tempdir, time.strftime("%Y_%m_%d"),
                                   time.strftime("%Y_%m_%d_session00"))
        self.assertEqual(session_logger.get_session_folder(), expected_fp)

        with open(session_logger.get_log_fp(), 'r') as log_file:
            first_line = log_file.readline()
            parts = first_line.split(' | ')
            self.assertEqual(parts[1], 'Session Description : Default Description\n')

    def test_log(self):
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        session_logger.log('TestTestTest')
        with open(session_logger.get_log_fp(), 'r') as log_file:
            log_file.readline() # Ignore first line
            second_line = log_file.readline()
            parts = second_line.split(' | ')
            self.assertEqual(parts[1], 'TestTestTest\n')

    def test_create_new(self):
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        session_logger.create_new_session()
        expected_fp = os.path.join(self.tempdir, time.strftime("%Y_%m_%d"),
                                   time.strftime("%Y_%m_%d_session01"))
        self.assertEqual(session_logger.get_session_folder(), expected_fp)
