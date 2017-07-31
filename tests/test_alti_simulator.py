"""Test the dummy alti."""

from unittest import TestCase
from time import sleep

from sensors.alti_simulator import SimulatorAlti
from support.configure import TricapConfig

# from config import ALTIMETER_STATE


class TestDummyAlti(TestCase):
    """Test the dummy alti."""

    def create_alti(self, settings=None):
        """Create an alti."""
        if settings is None:
            settings = self.base_settings
        self.alti = SimulatorAlti(settings)

    @property
    def base_settings(self):
        """The settings from the config file."""
        init_config = TricapConfig()
        return init_config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)

    def test_state_as_string(self):
        """Test that we can retrieve the state of the alti as a string."""
        self.create_alti()
        self.assertEqual(self.alti.get_state_as_string(), 'CONNECTED')

        self.alti.start_measuring()
        self.assertEqual(self.alti.get_state_as_string(), 'MEASURING')

        self.alti.stop_measuring()
        self.assertEqual(self.alti.get_state_as_string(), 'CONNECTED')

    def test_altitude_switch(self):
        """Test the state when different readings are taken from the altimeter"""
        self.create_alti()
        self.alti._measurement = 160
        self.alti.altitude_switch()
        self.assertEqual(self.alti.get_state_as_string(), 'MEASURING')

        self.alti._measurement = 130
        self.alti.altitude_switch()
        self.assertEqual(self.alti.get_state_as_string(), 'MEASURING')

        self.alti._measurement = 100
        self.alti.altitude_switch()
        self.assertEqual(self.alti.get_state_as_string(), 'CONNECTED')

        self.alti._measurement = 130
        self.alti.altitude_switch()
        self.assertEqual(self.alti.get_state_as_string(), 'CONNECTED')


    def test_measuring_sequence(self):
        """Test that the sequence can be run through with no errors."""
        self.create_alti()
        self.alti.generation_period = 0.01
        self.alti.start_measuring()
        sleep(self.alti.generation_period*100)
        self.alti.stop_measuring()
