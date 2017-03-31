"""Unit and interactive test for the TruSense S100 Altimeter."""

from time import sleep

from sensors.trusense_altimeter import TrusenseAltimeter, AltiError

from support.session_logger import SessionLogger
from support.configure import TricapConfig

from .tempfile_test_case import TricapTempFilerTestCase

from config import ALTIMETER_STATE


class TestDeviceTruSense(TricapTempFilerTestCase):
    """Test the altimeter."""

    def setUp(self):
        """setUp."""
        super().setUp()
        # self.session_logger = SessionLogger(root_folder=self.tempdir)
        # self.session_logger.create_new_session()
        self.alti = None

    def create_alti(self, settings=None):
        """Create an alti."""
        if settings is None:
            settings = self.base_settings
        self.alti = TrusenseAltimeter(settings)

    @property
    def base_settings(self):
        """The settings from the config file."""
        init_config = TricapConfig()
        return init_config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)

    def tearDown(self):
        """Manually unload objects holding onto needed resourced.

        This is necessary as each testcase instance is not unloaded untill the very end of a
        testsuite, to be able to access certain stats on each testcase for the final reporting.
        """
        # self.session_logger.__del__()
        if self.alti is not None:
            self.alti.disconnect()

        super().tearDown()

    def test_init(self):
        """Test that after the alti is created, it is setup correctly."""
        self.create_alti()
        self.assertEqual(self.alti.state, ALTIMETER_STATE.CONNECTED)
        self.assertEqual(self.alti.measurement, None)

    def test_reset(self):
        """Test resetting the alti."""
        self.create_alti()
        self.alti.start_measuring()
        self.alti.reset(self.base_settings)
        self.assertEqual(self.alti.state, ALTIMETER_STATE.CONNECTED)

    def test_disconnect(self):
        """Test manually disconnecting the alti."""
        self.create_alti()
        self.alti.disconnect()
        self.assertEqual(self.alti.state, ALTIMETER_STATE.NOT_CONNECTED)

    def test_notfound(self):
        """Test that the correct exception is raised when the alti is not found."""
        with self.assertRaises(AltiError):
            return TrusenseAltimeter(self.base_settings, supported_devices={(1659, 8964)})

    def test_invalid_command(self):
        """Test that an exception is raised when an invalid command is written on the port."""
        self.create_alti()
        self.assertRaises(AltiError, self.alti._write, "HAN", "Expected Error")

    def test_settings(self):
        """Test setting and getting parameters."""
        init_config = TricapConfig()
        alti_settings = init_config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)
        alti_settings['num_frames_to_avg'] = '2'

        self.create_alti(alti_settings)
        self.assertEqual(self.alti.config.num_frames_to_avg.choices, None)
        self.assertEqual(str(self.alti.config), "['measurement_timeout', 'num_frames_to_avg']")
        self.assertEqual(dir(self.alti.config), ['measurement_timeout', 'num_frames_to_avg'])
        self.assertEqual(self.alti.config.num_frames_to_avg, 2)
        self.assertEqual(str(self.alti.config.num_frames_to_avg), '2')
        self.alti.config.num_frames_to_avg = 1
        self.assertEqual(self.alti.config.num_frames_to_avg, 1)

        with self.assertRaises(Exception):
            self.alti.config.num_frames_to_avg_ = 2

        init_config = TricapConfig()
        alti_settings = init_config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)
        self.alti.reset(alti_settings)
        sleep(2)
        self.assertEqual(self.alti.state, ALTIMETER_STATE.CONNECTED)
        self.assertEqual(self.alti.get_state_as_string(), "CONNECTED")
        self.assertEqual(self.alti.config.num_frames_to_avg, 2)
        self.assertEqual(self.alti.state, ALTIMETER_STATE.CONNECTED)

    def test_measuring(self):
        """Test taking measurements with the alti."""
        self.create_alti()
        self.alti.start_measuring()
        sleep(5)
        self.assertEqual(self.alti.state, ALTIMETER_STATE.MEASURING)
        self.assertNotEqual(self.alti.measurement, None)
        self.alti.stop_measuring()
        sleep(2)
        self.assertEqual(self.alti.state, ALTIMETER_STATE.CONNECTED)

    def test_timeout(self):
        """Test that the alti goes to error state when it takes too long."""
        self.create_alti()
        # This causes the alti to accept commands and echo OK, but go silent when measurement is started
        self.alti.config.num_frames_to_avg = -1
        self.alti.start_measuring()
        self.assertEqual(self.alti.state, ALTIMETER_STATE.MEASURING)
        sleep(6)
        self.assertEqual(self.alti.state, ALTIMETER_STATE.ERROR)

    def test_integration_with_session_logger(self):
        """Test that the altimeter can be integrated with the session_logger."""
        class AltiMeasurementObserver():
            def __init__(self, session_logger):
                self.session_logger = session_logger

            def update(self, alti):
                self.session_logger.log('Alti Measurement: %f' % alti.measurement)

        self.create_alti()
        session_logger = SessionLogger(root_folder=self.tempdir)
        session_logger.create_new_session()

        alti_observer = AltiMeasurementObserver(session_logger)
        self.alti.attach(alti_observer)

        self.alti.start_measuring()
        sleep(3)
        self.alti.stop_measuring()

        with open(session_logger._log_fp, 'r') as sfile:
            sfile.readline()  # skip the first, description line
            line = sfile.readline()
            parts = line.split(' | ')
            self.assertEqual(parts[1].split(':')[0], 'Alti Measurement')

        # sommer test the detaching while we have it attached
        self.alti.detach(alti_observer)
        self.alti.detach(alti_observer)  # test it twice, try to detach already detached

        session_logger.__del__()
