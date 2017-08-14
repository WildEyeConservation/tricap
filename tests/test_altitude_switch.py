"""Test the dummy alti."""

from unittest import TestCase
from time import sleep

from sensors.alti_simulator import SimulatorAlti
from sensors.altitude_switch import AltiSwitch
from support.configure import TricapConfig
from config import OverrideState


class TestAltiSwitch(TestCase):
    """Test the altitude switch with switch state and override status."""

    def create_alti(self, settings=None):
        """Create an alti."""
        if settings is None:
            settings = self.base_settings
        self.alti = SimulatorAlti(settings)
        self.switch = AltiSwitch(self.alti)

    @property
    def base_settings(self):
        """The settings from the config file."""
        init_config = TricapConfig()
        return init_config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)

    def test_altitude_switch(self):
        """Test the state when different readings are taken from the altimeter"""
        self.create_alti()

        self.alti._measurement = 160
        self.switch.update(self)
        self.switch.set_altitude_switch()
        self.assertTrue(self.switch.get_altitude_switch_state() == True)

        self.alti._measurement = 130
        self.switch.update(self)
        self.switch.set_altitude_switch()
        self.assertTrue(self.switch.get_altitude_switch_state() == True)

        # self.alti._measurement = 100
        # self.switch.update(self)
        # self.switch.set_altitude_switch()
        # self.assertTrue(self.switch.get_altitude_switch_state() == False)
        #
        # self.alti._measurement = 130
        # self.switch.update(self)
        # self.switch.set_altitude_switch()
        # self.assertTrue(self.switch.get_altitude_switch_state() == False)

    def test_override_state(self):
        """ Test the override functionality of the altitude switch with boundries of 150 and 120"""
        self.create_alti()

        self.alti._measurement = 130
        self.switch.update(self)
        self.switch.set_altitude_switch_state(OverrideState.ALTISWITCH.value)
        self.assertTrue(self.switch.get_altitude_switch_state() == False)

        self.alti._measurement = 160
        self.switch.update(self)
        self.switch.set_altitude_switch_state(OverrideState.ALTISWITCH.value)
        self.assertTrue(self.switch.get_altitude_switch_state() == True)

        self.switch.set_altitude_switch_state(OverrideState.STOPOVERRIDE.value)
        self.assertTrue(self.switch.get_altitude_switch_state() == False)

        self.switch.set_altitude_switch_state(OverrideState.MANUALSTART.value)
        self.assertTrue(self.switch.get_altitude_switch_state() == True)

