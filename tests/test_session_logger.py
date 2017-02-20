"""Test the session logger."""

import os
import time
import logging

from support.session_logger import SessionLogger

from .tempfile_test_case import TempFilerTestCase

from config import SERVER_LOG_DIR


class TestSessionLogger(TempFilerTestCase):
    """Log all session_logger module errors to a local file."""

    # format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    # handler = logging.FileHandler(filename=os.path.join(SERVER_LOG_DIR, 'test_session_logger.log'))
    # handler.setLevel(logging.DEBUG)
    # handler.setFormatter(logging.Formatter(format_str))
    # handler.addFilter(logging.Filter(name='sensors.session_logger'))
    # rootLogger = logging.getLogger('')
    # rootLogger.addHandler(handler)
    # rootLogger.setLevel(logging.DEBUG)

    # def tearDown(self):
    #     """Remove the handlers, release the file."""
    #     session_logger._remove_handlers()
    #     super(TestSessionLogger, self).tearDown()

    def test_init(self):
        """Test that the session_logger starts up correctly."""
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        time.sleep(1)

        expected_fp = os.path.join(self.tempdir, time.strftime("%Y_%m_%d"),
                                   time.strftime("%Y_%m_%d_session00"))
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
        expected_fp = os.path.join(self.tempdir, time.strftime("%Y_%m_%d"),
                                   time.strftime("%Y_%m_%d_session01"))
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
        a_handler = logging.FileHandler(filename=os.path.join(SERVER_LOG_DIR, 'a.log'))
        a_handler.setFormatter(logging.Formatter("%(message)s"))
        a_logger = logging.getLogger('a')
        a_logger.addHandler(a_handler)
        a_logger.propagate = False

        b_handler = logging.FileHandler(filename=os.path.join(SERVER_LOG_DIR, 'b.log'))
        b_handler.setFormatter(logging.Formatter("%(message)s"))
        b_logger = logging.getLogger('b')
        b_logger.addHandler(b_handler)

        session_logger = SessionLogger(root_folder=self.tempdir, log_names_to_track=['a', 'b'])
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


    # def test_folder_prepping(self):
    #     """Check that the created folder contains all that we want it to."""
    #     if os.path.isfile(os.path.join(SERVER_LOG_DIR, 'tricap_master.log')) is False:
    #         with open(os.path.join(SERVER_LOG_DIR, 'tricap_master.log'), 'w') as tfile:
    #             tfile.write('test')
    #
    #     session_logger = SessionLogger(root_folder=self.tempdir)
    #     session_logger.create_new_session()
    #
    #     file_folder_names = os.listdir(session_logger._session_folder)
    #     # config file (initial.cfg)
    #     # _, config_filename_with_ext = os.path.split(CONFIG_FP)
    #     self.assertEqual('initial.cfg' in file_folder_names, True)
    #
    #     self.assertEqual('pre_session_server.log' in file_folder_names, True)
    #     self.assertEqual('session_server.log' in file_folder_names, True)
    #
    #     session_logger._remove_handlers()
