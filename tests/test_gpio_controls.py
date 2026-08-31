"""Tests for the physical capture switch."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
GPIO_PATH = ROOT / "sensors" / "toggle_switch.py"


def load_gpio_controls():
    gpio = types.ModuleType("RPi.GPIO")
    gpio.BCM = 1
    gpio.IN = 2
    gpio.OUT = 3
    gpio.PUD_DOWN = 4
    gpio.LOW = 0
    gpio.HIGH = 1
    gpio.setmode = Mock()
    gpio.setup = Mock()
    gpio.output = Mock()
    gpio.cleanup = Mock()
    gpio.input = Mock()

    rpi = types.ModuleType("RPi")
    rpi.GPIO = gpio

    module_name = "skyseeker_gpio_controls_test"
    spec = importlib.util.spec_from_file_location(module_name, GPIO_PATH)
    module = importlib.util.module_from_spec(spec)
    previous_rpi = sys.modules.get("RPi")
    previous_gpio = sys.modules.get("RPi.GPIO")
    sys.modules["RPi"] = rpi
    sys.modules["RPi.GPIO"] = gpio
    try:
        spec.loader.exec_module(module)
    finally:
        if previous_rpi is None:
            sys.modules.pop("RPi", None)
        else:
            sys.modules["RPi"] = previous_rpi
        if previous_gpio is None:
            sys.modules.pop("RPi.GPIO", None)
        else:
            sys.modules["RPi.GPIO"] = previous_gpio
    return module, gpio


class CaptureSwitchTests(unittest.TestCase):

    def test_active_low_switch_requires_two_matching_samples(self):
        controls, gpio = load_gpio_controls()
        monitor = controls.ToggleSwitchMonitor()

        gpio.input.side_effect = [gpio.LOW, gpio.LOW, gpio.HIGH, gpio.HIGH]
        observed = []
        for _ in range(4):
            monitor.monitor_step()
            observed.append(monitor.value)

        self.assertEqual(observed, [0, 1, 1, 0])


if __name__ == "__main__":
    unittest.main()
