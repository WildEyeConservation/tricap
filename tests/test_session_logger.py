"""Test the session logger."""

import os
import time
import logging

from support.session_logger import SessionLogger

from .tricap_tempfile_test_case import TriCapTempFilerTestCase


class TestSessionLogger(TriCapTempFilerTestCase):
    """Log all session_logger module errors to a local file."""

    def test_init(self):
        """Test that the session_logger starts up correctly."""
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        time.sleep(1)

        expected_fp = os.path.join(self.tempdir, time.strftime("%Y-%m-%d"),
                                   time.strftime("%Y-%m-%d_session00"))
        self.assertEqual(session_logger._session_folder, expected_fp)

        with open(session_logger._log_fp, 'r') as log_file:
            first_line = log_file.readline()
            parts = first_line.split(' | ')
            self.assertEqual(parts[1], 'Session Description : Default Description\n')

        session_logger._remove_handlers()

    def test_log(self):
        """Check whether logging happens correctly."""
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        session_logger.log('TestTestTest')
        time.sleep(1)
        with open(session_logger._log_fp, 'r') as log_file:
            log_file.readline()  # Ignore first line
            second_line = log_file.readline()
            parts = second_line.split(' | ')
            self.assertEqual(parts[1], 'TestTestTest\n')

        session_logger._remove_handlers()

    def test_bad_root_folder(self):
        """Test what happens when you cause the session_logger to not setup properly."""
        session_logger = SessionLogger(root_folder='I/Do/Not/Exist')
        session_logger.create_new_session()
        self.assertEqual(session_logger.is_ready(), False)

        session_logger._remove_handlers()

    def test_create_two_sessions(self):
        """Check that the folder names created are correct for subsequent sessions."""
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        session_logger.create_new_session()
        expected_fp = os.path.join(self.tempdir, time.strftime("%Y-%m-%d"),
                                   time.strftime("%Y-%m-%d_session01"))
        self.assertEqual(session_logger._session_folder, expected_fp)

        session_logger._remove_handlers()

    def test_get_set_session_descriptor(self):
        """Test that the session_descriptor can be set and gotten correctly."""
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.set_description('Test Description')
        session_logger.create_new_session()
        time.sleep(1)

        with open(session_logger._log_fp, 'r') as log_file:
            first_line = log_file.readline()
            parts = first_line.split(' | ')
            self.assertEqual(parts[1], 'Session Description : Test Description\n')

        self.assertEqual(session_logger.get_description(), 'Test Description')

        session_logger.create_new_session('Another Test Description')
        time.sleep(1)
        with open(session_logger._log_fp, 'r') as log_file:
            first_line = log_file.readline()
            parts = first_line.split(' | ')
            self.assertEqual(parts[1], 'Session Description : Another Test Description\n')

        session_logger._remove_handlers()

    def test_folder_prepping(self):
        """Check that the created folder contains all that we want it to."""
        # create two new loggers
        original_folder = os.path.join(self.tempdir, 'original')
        os.mkdir(original_folder)

        a_handler = logging.FileHandler(filename=os.path.join(original_folder, 'a.log'))
        a_handler.setFormatter(logging.Formatter("%(message)s"))
        a_logger = logging.getLogger('a')
        a_logger.addHandler(a_handler)
        a_logger.propagate = False

        b_handler = logging.FileHandler(filename=os.path.join(original_folder, 'b.log'))
        b_handler.setFormatter(logging.Formatter("%(message)s"))
        b_logger = logging.getLogger('b')
        b_logger.addHandler(b_handler)

        sl_folder = os.path.join(self.tempdir, 'session_logger')
        session_logger = SessionLogger(root_folder=sl_folder, log_names_to_track=['a', 'b'])
        session_logger.create_new_session()

        a_logger.debug('Test A')
        b_logger.info('Test B')

        pre_file_folder_names = os.listdir(os.path.join(session_logger._session_folder, 'pre'))
        file_folder_names = os.listdir(session_logger._session_folder)

        self.assertEqual('a.log' in pre_file_folder_names, True)
        self.assertEqual('b.log' in pre_file_folder_names, True)

        self.assertEqual('initial.cfg' in file_folder_names, True)
        self.assertEqual('a.log' in file_folder_names, True)
        self.assertEqual('b.log' in file_folder_names, True)

        with open(os.path.join(session_logger._session_folder, a_handler.stream.name), 'r') as af:
            self.assertEqual(af.readline(), 'Test A\n')

        with open(os.path.join(session_logger._session_folder, b_handler.stream.name), 'r') as bf:
            self.assertEqual(bf.readline(), 'Test B\n')

        session_logger._remove_handlers()

        a_logger.removeHandler(a_handler)
        a_handler.close()
        b_logger.removeHandler(b_handler)
        b_handler.close()

    def test_deletion(self):
        """Test that deleting/destroying a session handler stops logging to the session_folder."""
        # create two new loggers
        original_folder = os.path.join(self.tempdir, 'original')
        os.mkdir(original_folder)
        a_handler = logging.FileHandler(filename=os.path.join(original_folder, 'a.log'))
        a_handler.setFormatter(logging.Formatter("%(message)s"))
        a_logger = logging.getLogger('a')
        a_logger.addHandler(a_handler)

        sl_folder = os.path.join(self.tempdir, 'session_logger')
        session_logger = SessionLogger(root_folder=sl_folder, log_names_to_track=['a'])
        session_logger.create_new_session()

        a_logger.debug('Test A')

        file_folder_names = os.listdir(session_logger._session_folder)
        self.assertEqual('a.log' in file_folder_names, True)

        with open(os.path.join(session_logger._session_folder, 'a.log'), 'r') as af:
            lines = af.readlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0], 'Test A\n')

        session_folder = session_logger._session_folder

        # delete the session logger - can't use del session_logger, unittest keeps a reference?
        session_logger.__del__()

        a_logger.debug('Test A Again')

        with open(os.path.join(session_folder, 'a.log'), 'r') as af:
            lines = af.readlines()
            self.assertEqual(len(lines), 1)

        a_logger.removeHandler(a_handler)
        a_handler.close()

    def test_strange_log_cases(self):
        """Test adding logs such as the root and a non-file logging log."""
        a_handler = logging.StreamHandler()
        a_handler.setFormatter(logging.Formatter("%(message)s"))
        a_logger = logging.getLogger('a')
        a_logger.addHandler(a_handler)

        sl_folder = os.path.join(self.tempdir, 'session_logger')
        session_logger = SessionLogger(root_folder=sl_folder, log_names_to_track=['a', 'root'])
        session_logger.create_new_session()

        # check that we ignored the stream logger
        self.assertEqual(len(session_logger._additional_fhs), 1)
        self.assertEqual(session_logger.log_names_tracked, [''])

        session_logger._remove_handlers()

    def test_bad_log_name(self):
        """Test that the session_logger does not fall over when a bad logger is named."""
        sl_folder = os.path.join(self.tempdir, 'session_logger')
        session_logger = SessionLogger(root_folder=sl_folder, log_names_to_track=['notexist'])
        session_logger.create_new_session()
        session_logger._remove_handlers()
