"""Almost unit test for the system monitors, obviously cant test linux on windows, vice versa."""

import unittest
import time
import logging
import os

from support.system_monitor import generate_system_monitor, SystemMonitorLogger

from config import SERVER_LOG_DIR


class SystemMonitorObserver():
    """An observer of a System Monitor subject."""

    def __init__(self):
        """Constructor."""
        self.value = None

    def update(self, sys_mon):
        """Update."""
        self.value = sys_mon.value

    def print_info(self):  # pragma: no cover
        """Helper method."""
        print('Sys_Mon status:')
        print('Value: %s' % self.value)


class TestSysMon(unittest.TestCase):
    """Test class to test a sys mon."""

    def setUp(self):
        """setUp."""
        self.period = 0.25

    def test_ram_monitor(self):
        """Test a RAM monitor, see that it generates output."""
        observer = SystemMonitorObserver()
        sys_mon = generate_system_monitor(self.period, 'RAM')
        sys_mon.attach(observer)
        sys_mon.start()
        time.sleep(sys_mon.period*2)
        # print('\nTest Sys Monitor Output, please check to see if this is as expected.\n')
        # observer.print_info()
        # print('\n')
        self.assertNotEqual(observer.value, None)
        self.assertEqual(type(observer.value), float)

    def test_cpu_monitor(self):
        """Test a CPU monitor, see that it generates output."""
        observer = SystemMonitorObserver()
        sys_mon = generate_system_monitor(self.period, 'CPU')
        sys_mon.attach(observer)
        sys_mon.start()
        time.sleep(sys_mon.period*2)
        # print('\nTest Sys Monitor Output, please check to see if this is as expected.\n')
        # observer.print_info()
        # print('\n')
        self.assertNotEqual(observer.value, None)
        self.assertEqual(type(observer.value), float)

    def test_copy_disk_monitor(self):
        """Test a Disk Usage monitor, see that it generates output.  """
        observer = SystemMonitorObserver()
        sys_mon = generate_system_monitor(self.period, 'Disk')
        sys_mon.attach(observer)
        sys_mon.start()
        time.sleep(sys_mon.period*2)
        # print('\nTest Sys Monitor Output, please check to see if this is as expected.\n')
        # observer.print_info()
        # print('\n')
        self.assertNotEqual(observer.value, None)
        self.assertEqual(type(observer.value), float)


class TestSysMonLogger(unittest.TestCase):
    """Log all sys mon logger output to a local file, so to make it easier, only one test."""

    # Remove the log file if it exists (make sure we are testing it right now)
    log_fp = os.path.join(SERVER_LOG_DIR, 'test_sys_mon_logger.log')
    if os.path.isfile(log_fp):
        os.remove(log_fp)

    logging_name = 'test_sys_mon_logger'

    format_str = "%(message)s"
    handler = logging.FileHandler(filename=log_fp)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(format_str))
    handler.addFilter(logging.Filter(name=logging_name))
    rootLogger = logging.getLogger('')
    rootLogger.addHandler(handler)
    rootLogger.setLevel(logging.DEBUG)

    def setUp(self):
        """setUp."""
        self.period = 2

    def test_sys_mon_logger(self):
        """Test the system monitor logger."""
        sys_mons = []
        sys_mons.append(generate_system_monitor(self.period, 'RAM'))
        sys_mons.append(generate_system_monitor(self.period, 'CPU'))

        SystemMonitorLogger(sys_mons, logging_name=self.logging_name)
        for sys_mon in sys_mons:
            sys_mon.start()

        time.sleep(sys_mons[1].period*2)

        for sys_mon in sys_mons:
            sys_mon.stop()

        with open(self.log_fp, 'r') as log_file:
            lines = log_file.readlines()
            self.assertGreater(len(lines), 0)

            got_ram = False
            got_cpu = False

            if os.name == 'nt':
                ram_str = 'Windows RAM'
                cpu_str = 'Windows CPU'
            elif os.name == 'posix':
                ram_str = 'Linux RAM'
                cpu_str = 'Linux CPU'

            for line in lines:
                parts = line.replace(',', ':').split(':')
                self.assertEqual(parts[0].strip(), 'Sys Mon')
                if parts[1].strip() == ram_str:
                    got_ram = True
                elif parts[1].strip() == cpu_str:
                    got_cpu = True

            self.assertEqual(got_ram, True)
            self.assertEqual(got_cpu, True)
