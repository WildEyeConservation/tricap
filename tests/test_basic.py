"""The support.basic tests."""

import unittest
import time

from support.basic import TimeMonitor


class TimeMonitorObserver():
    """An observer of a System Monitor subject."""

    def __init__(self):
        """Constructor."""
        self.value = None

    def update(self, sys_mon):
        """Update."""
        self.value = sys_mon.value

    def print_info(self):  # pragma: no cover
        """Helper method."""
        print('Time status:')
        print('Value: %s' % self.value)


class TimeMonitorTests(unittest.TestCase):
    """Test class to test a time observer."""

    def setUp(self):
        """setUp."""
        self.period = 0.05

    def test_ram_monitor(self):
        """Test a RAM monitor, see that it generates output."""
        observer = TimeMonitorObserver()
        time_mon = TimeMonitor(self.period)
        time_mon.attach(observer)
        time_mon.start()
        time.sleep(time_mon.period*2)
        # print('\nTest Time Monitor Output, please check to see if this is as expected.\n')
        # observer.print_info()
        # print('\n')
        self.assertNotEqual(observer.value, None)
        self.assertEqual(type(observer.value), str)
