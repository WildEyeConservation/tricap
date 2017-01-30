"""network_monitor - monitors the network, logs the status, through observer patterns."""

import os
import threading
import logging

from abc import ABCMeta, abstractmethod

from support.basic import Subject, RepeatingBarrierPasser


class UnknownOperatingSystem(Exception):
    """Exception for when os.name returns an unkown operating system id."""

    pass


class NetworkMonitor(Subject):
    """NetworkMonitor, abstract observable for checking network statuses."""

    __metaclass__ = ABCMeta

    def __init__(self, period: float = 60):
        """Constructor."""
        super(NetworkMonitor, self).__init__()

        self.period = period

        self._stop_event = None
        self._barrier = None
        self._period_timer = None

        self.status = None
        self.signal_strength = None
        self.network_name = None

    def __del__(self):
        """Destructor."""
        self.stop()
    

    @abstractmethod
    def update_status(self):
        """Use whatever means and parsing to update the status of the network connecction."""
        pass

    def monitor(self):
        """In a loop, check the network connection."""
        while True:
            if self._stop_event.is_set():
                return
            self._barrier.wait()
            self.update_status()
            self.notify()

    def start(self):
        """Start the network monitoring in separate threads."""
        self._stop_event = threading.Event()
        self._barrier = threading.Barrier(2)  # one for the timer, one for the status checking
        self._period_timer = RepeatingBarrierPasser(self.period,
                                                    self._stop_event, self._barrier)
        thread = threading.Thread(target=self.monitor, daemon=True)
        self._period_timer.start()
        thread.start()

    def stop(self):
        """Stop the threads involved in the montoring."""
        self._stop_event.set()


class WindowsNetworkMonitor(NetworkMonitor):
    """WindowsNetworkMonitor, checks the status of the windows network."""

    def __init__(self, period: float = 60):
        """constructor."""
        super(WindowsNetworkMonitor, self).__init__(period)

    def update_status(self):
        """Update the status using the windows netsh commands."""
        with os.popen('netsh wlan show interfaces') as cmd_output:
            lines = cmd_output.readlines()
            self.signal_strength = '0%'
            for line in lines:
                parts = line.split(':')
                if len(parts) > 1:
                    id_str = parts[0].strip()
                    if id_str == 'State':
                        self.status = parts[1].strip()
                    elif id_str == 'Signal':
                        self.signal_strength = parts[1].strip()
                    elif id_str == 'SSID':
                        self.network_name = parts[1].strip()


class LinuxNetworkMonitor(NetworkMonitor):
    """LinuxNetworkMonitor, checks the status of the network on a linux system."""

    def __init__(self, period: float = 60):
        """constructor."""
        super(LinuxNetworkMonitor, self).__init__(period)

    def update_status(self):
        """Update the status using linux terminal commands."""
        pass


def generate_net_monitor(period=60):
    """Generate the correct NetworkMonitor based on os."""
    network_monitor = None

    if os.name == 'nt':
        network_monitor = WindowsNetworkMonitor(period)
    elif os.name == 'posix':
        network_monitor = LinuxNetworkMonitor(period)
    else:
        raise UnknownOperatingSystem

    return network_monitor


class NetworkMonitorLogger():
    """An observer, hooks up to a network monitor, log stats to the root logger."""

    def __init__(self, net_monitor, logging_name=''):
        """Constructor, hook up the logger to the monitor."""
        super(NetworkMonitorLogger, self).__init__()
        self.logger = logging.getLogger(name=logging_name)
        net_monitor.attach(self)

    def update(self, net_monitor):
        """Update method called by net monitor subject."""
        self.logger.info('Network Name: SSID %s, Status: %s, Signal Strength: %s',
                         net_monitor.network_name, net_monitor.status, net_monitor.signal_strength)
