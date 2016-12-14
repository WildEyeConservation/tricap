"""Test the session logger."""

import os
import time
import logging

from support.session_logger import SessionLogger

from .tempfile_test_case import TempFilerTestCase

from config import SERVER_LOG_DIR


class TestSessionLogger(TempFilerTestCase):
    """Log all session_logger module errors to a local file."""

    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    handler = logging.FileHandler(filename=os.path.join(SERVER_LOG_DIR, 'test_session_logger.log'))
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(format_str))
    handler.addFilter(logging.Filter(name='sensors.session_logger'))
    rootLogger = logging.getLogger('')
    rootLogger.addHandler(handler)
    rootLogger.setLevel(logging.DEBUG)

    def test_init(self):
        """Test that the session_logger starts up correctly."""
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        expected_fp = os.path.join(self.tempdir, time.strftime("%Y_%m_%d"),
                                   time.strftime("%Y_%m_%d_session00"))
        self.assertEqual(session_logger._session_folder, expected_fp)

        with open(session_logger._log_fp, 'r') as log_file:
            first_line = log_file.readline()
            parts = first_line.split(' | ')
            self.assertEqual(parts[1], 'Session Description : Default Description\n')

    def test_log(self):
        """Check whether logging happens correctly."""
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        session_logger.log('TestTestTest')
        with open(session_logger._log_fp, 'r') as log_file:
            log_file.readline()  # Ignore first line
            second_line = log_file.readline()
            parts = second_line.split(' | ')
            self.assertEqual(parts[1], 'TestTestTest\n')

    def test_bad_root_folder(self):
        """Test what happens when you cause the session_logger to not setup properly."""
        session_logger = SessionLogger(root_folder='I/Do/Not/Exist')
        session_logger.create_new_session()
        self.assertEqual(session_logger.is_ready(), False)

    def test_create_two_sessions(self):
        """Check that the folder names created are correct for subsequent sessions."""
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        session_logger.create_new_session()
        expected_fp = os.path.join(self.tempdir, time.strftime("%Y_%m_%d"),
                                   time.strftime("%Y_%m_%d_session01"))
        self.assertEqual(session_logger._session_folder, expected_fp)

    def test_get_set_session_descriptor(self):
        """Test that the session_descriptor can be set and gotten correctly."""
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.set_description('Test Description')
        session_logger.create_new_session()

        with open(session_logger._log_fp, 'r') as log_file:
            first_line = log_file.readline()
            parts = first_line.split(' | ')
            self.assertEqual(parts[1], 'Session Description : Test Description\n')

        self.assertEqual(session_logger.get_description(), 'Test Description')

        session_logger.create_new_session('Another Test Description')
        with open(session_logger._log_fp, 'r') as log_file:
            first_line = log_file.readline()
            parts = first_line.split(' | ')
            self.assertEqual(parts[1], 'Session Description : Another Test Description\n')

    def test_folder_prepping(self):
        """Check that the created folder contains all that we want it to."""
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        file_folder_names = os.listdir(session_logger._session_folder)
        # config file (initial.cfg)
        # _, config_filename_with_ext = os.path.split(CONFIG_FP)
        self.assertEqual('initial.cfg' in file_folder_names, True)

        self.assertEqual('pre_session_server.log' in file_folder_names, True)
        self.assertEqual('session_server.log' in file_folder_names, True)
