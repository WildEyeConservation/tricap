"""network_monitor - monitors the network, logs the status, through observer patterns."""

import os
import logging

from abc import ABCMeta

from support.basic import PeriodicMonitor, UnknownOperatingSystem


class NetworkMonitor(PeriodicMonitor):
    """NetworkMonitor, abstract observable for checking network statuses."""

    __metaclass__ = ABCMeta

    def __init__(self, period: float = 60):
        """Constructor."""
        super(NetworkMonitor, self).__init__(period)

        self.status = None
        self.signal_strength = None
        self.network_name = None


class WindowsNetworkMonitor(NetworkMonitor):
    """WindowsNetworkMonitor, checks the status of the windows network."""

    def __init__(self, period: float = 60):
        """constructor."""
        super(WindowsNetworkMonitor, self).__init__(period)

    def monitor_step(self):
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

    def monitor_step(self):
        """Update the status using linux terminal commands."""
        self.network_name = None

        with os.popen('iwgetid -r') as cmd_output:
            line = cmd_output.readline()
            if len(line) > 0:
                self.network_name = line.strip()

        if self.network_name is not None:
            with os.popen('iwconfig wlan0 | grep "Link Quality" ') as cmd_output:
                ss = cmd_output.readline().split('Signal level')[0].split('=')[1].strip()
                self.signal_strength = str(float(ss.split('/')[0])/float(ss.split('/')[1])*100)+'%'
            self.status = 'connected'
        else:
            self.status = 'disconnected'
            self.signal_strength = None


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


class IPMonitor(PeriodicMonitor):
    """Periodically ping a particular IP address."""

    __metaclass__ = ABCMeta

    def __init__(self, address: str, period: float):
        """Constructor, takes an address string and the period."""
        if period < 0.6:
            period = 0.6
        super(IPMonitor, self).__init__(period)
        self.address = address

        self.reachable = None
        self.latency = None


class WindowsIPMonitor(IPMonitor):
    """Periodically ping an address in windows."""

    def __init__(self, address: str, period: float):
        """Constructor. Period is hard limited to more that 0.6."""
        super(WindowsIPMonitor, self).__init__(address, period)

    def monitor_step(self):
        """Ping the address."""
        with os.popen('ping %s -n 1 -l 32 -w 500' % self.address) as cmd_output:
            lines = cmd_output.readlines()
            if lines[2].strip() == 'Request timed out.':
                self.reachable = False
                self.latency = None
            else:
                self.reachable = True
                self.latency = float(lines[7].split('=')[-1].strip()[:-2])


class LinuxIPMonitor(IPMonitor):
    """Periodically ping an address in Linux."""

    def __init__(self, address: str, period: float):
        """Constructor. Period is hard limited to more that 0.6."""
        super(LinuxIPMonitor, self).__init__(address, period)

    def monitor_step(self):
        """Ping the address."""
        with os.popen('timeout 0.5 ping %s -c 1 -s 32' % self.address) as cmd_output:
            lines = cmd_output.readlines()

            if len(lines) <= 1:  # if the timeout happened
                self.reachable = False
                self.latency = None
                return

            if lines[1].split(' ')[-1].strip() == 'Unreachable':
                self.reachable = False
                self.latency = None
            else:
                self.reachable = True
                self.latency = float(lines[5].split('=')[1].split('/')[1].strip())


def generate_ip_monitor(address, period):
    """Generate the correct IPMonitor based on os."""
    ip_mon = None

    if os.name == 'nt':
        ip_mon = WindowsIPMonitor(address, period)
    elif os.name == 'posix':
        ip_mon = LinuxIPMonitor(address, period)
    else:
        raise UnknownOperatingSystem

    return ip_mon


class IPMonitorLogger():
    """An observer, hooks up to a ip monitor, log stats to the root logger."""

    def __init__(self, ip_monitors, logging_name=''):
        """Constructor, hook up the logger to the monitor."""
        super(IPMonitorLogger, self).__init__()
        self.logger = logging.getLogger(name=logging_name)

        if type(ip_monitors) is not list:
            ip_monitors = [ip_monitors]

        for ip_monitor in ip_monitors:
            ip_monitor.attach(self)

    def update(self, ip_monitor):
        """Update method called by net monitor subject."""
        if ip_monitor.reachable is False:
            self.logger.info('IP Address: %s, Reachable: %s', ip_monitor.address,
                             ip_monitor.reachable)
        else:
            self.logger.info('IP Address: %s, Reachable: %s, Latency(ms): %f',
                             ip_monitor.address, ip_monitor.reachable, ip_monitor.latency)
