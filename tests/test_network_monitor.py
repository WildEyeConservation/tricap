"""Almost unit test for the network monitor, obviously cant test linux on windows."""

import unittest
import time
import os
import logging

from support.network_monitor import generate_net_monitor, NetworkMonitorLogger

from config import SERVER_LOG_DIR


class NetMonitorObserver():
    """An observer of a Network Monitor subject."""

    def __init__(self):
        """Constructor."""
        self.name = None
        self.status = None
        self.signal_strength = None

    def update(self, net_monitor):
        """Update."""
        self.name = net_monitor.network_name
        self.status = net_monitor.status
        self.signal_strength = net_monitor.signal_strength

    def print_info(self):
        """Helper method."""
        print('net_monitor status:')
        print('network name: %s' % self.name)
        print('network status: %s' % self.status)
        print('network signal_strength: %s' % self.signal_strength)


class TestNetMonitor(unittest.TestCase):
    """Test class to test the network monitor."""

    def setUp(self):
        """setUp."""
        self.period = 0.25
        self.net_monitor = generate_net_monitor(period=self.period)

    def tearDown(self):
        """tearDown."""
        self.net_monitor.stop()
        self.net_monitor = None

    def test_net_monitor(self):
        """Test a net monitor, see that it generates output."""
        observer = NetMonitorObserver()
        self.net_monitor.attach(observer)
        self.net_monitor.start()
        time.sleep(self.period*2)
        print('\nTest Network Monitor Output, please check to see if this is as expected.\n')
        observer.print_info()
        print('\n')
        self.assertNotEqual(observer.status, None)
        if observer.status != 'disconnected':
            self.assertNotEqual(observer.name, None)
            self.assertNotEqual(observer.signal_strength, None)


class TestNetMonLogger(unittest.TestCase):
    """Log all net mon logger output to a local file, so to make it easier, only one test."""

    # Remove the log file if it exists (make sure we are testing it right now)
    log_fp = os.path.join(SERVER_LOG_DIR, 'test_net_mon_logger.log')
    if os.path.isfile(log_fp):
        os.remove(log_fp)

    logging_name = 'test_net_mon_logger'

    format_str ="%(message)s"
    handler = logging.FileHandler(filename=log_fp)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(format_str))
    handler.addFilter(logging.Filter(name=logging_name))
    rootLogger = logging.getLogger('')
    rootLogger.addHandler(handler)
    rootLogger.setLevel(logging.DEBUG)

    def setUp(self):
        """setUp."""
        self.period = 1
        self.net_monitor = generate_net_monitor(period=self.period)

    def tearDown(self):
        """tearDown."""
        self.net_monitor.stop()
        self.net_monitor = None

    def test_net_mon_logger(self):
        """Test a net monitor, see that it generates output."""
        observer = NetworkMonitorLogger(self.net_monitor, logging_name=self.logging_name)
        self.net_monitor.start()
        time.sleep(self.period*2)
        self.net_monitor.stop()

        with open(self.log_fp, 'r') as log_file:
            lines = log_file.readlines()
            self.assertGreater(len(lines), 0)
            print('\nNet Mon Logger, please verify that output is as expected:')
            print(lines)
            print('\n')
            line = lines[0]
            parts = line.replace(',', ':').split(':')
            self.assertEqual(parts[0].strip(), 'Network Name')
            self.assertEqual(parts[2].strip(), 'Status')
            self.assertEqual(parts[4].strip(), 'Signal Strength')
