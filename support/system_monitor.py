"""System Monitor - Classes to monitor the state of the system you are running on."""

import os
import logging
from abc import ABCMeta
from .basic import PeriodicMonitor


class UnknownSysMonTypeID(Exception):
    """Exception for when an unknown type id is used for the system monitor generator."""

    pass


class SystemMonitor(PeriodicMonitor):
    """SystemMonitor, abstract observable for checking some system value."""

    __metaclass__ = ABCMeta

    def __init__(self, period: float):
        """Constructor."""
        super(SystemMonitor, self).__init__(period)

        self.type_id = 'SysMon'
        self.unit = 'MB'
        self.value = None
        self.logger = logging.getLogger(__name__)


class LinuxFreeRAMMonitor(SystemMonitor):
    """Monitor how much free RAM in MB is available in Linux."""

    def __init__(self, period: float):
        """Constructor, set the type_id to RAM."""
        super(LinuxFreeRAMMonitor, self).__init__(period)

        self.type_id = 'Linux RAM'

    def monitor_step(self):
        """Update the value with the amount of free RAM available."""
        with os.popen('free') as cmd_output:
            try:
                lines = cmd_output.readlines()
                val = float(lines[1].split(' ')[-1].strip())
                self.value = val/1000.0
            except (ValueError, IndexError) as exp:
                self.logger.error('Error while monitoring system resources: %s', str(exp))


class LinuxCPUUsageMonitor(SystemMonitor):
    """Monitor how much the CPU is used as a percentage in Linux."""

    def __init__(self, period):
        """Constructor, lower limites the period to 2 seconds."""
        if period < 5:
            period = 5

        super(LinuxCPUUsageMonitor, self).__init__(period)

        self.type_id = 'Linux CPU'
        self.unit = '%'

    def monitor_step(self):
        """Update the value with the percentage of CPU used."""
        with os.popen('top -bn2 | grep Cpu') as cmd_output:
            try:
                line = cmd_output.readline()
                line = cmd_output.readline()
                parts = [part for part in line.split(' ') if part != '']
                # adding together the user and the kernel space cpu stats
                self.value = float(parts[1])+float(parts[3])
            except (ValueError, IndexError) as exp:
                self.logger.error('Error while monitoring system resources: %s', str(exp))


class LinuxDiskUsageMonitor(SystemMonitor):
    """Monitor how much the space is left on HD in MB in Linux."""

    def __init__(self, period):
        """Constructor, can change the defaul disk to check."""
        super(LinuxDiskUsageMonitor, self).__init__(period)

        self.type_id = 'Linux Disk'

    def monitor_step(self):
        """Update the value with the available space in MB on the root."""
        with os.popen('df | grep /$') as cmd_output:
            try:
                lines = cmd_output.readlines()
                parts = lines[0].split(' ')
                parts = [part for part in parts if part != '']
                self.value = float(parts[3])/1000.0
            except (ValueError, IndexError) as exp:
                self.logger.error('Error while monitoring system resources: %s', str(exp))


class LinuxDiskIOMonitor(SystemMonitor):
    """Monitor how much time is spent in IO, using /proc/diskstat in Linux."""

    def __init__(self, period):
        """Constructor."""
        super(LinuxDiskIOMonitor, self).__init__(period)

        self.type_id = 'Linux IO'
        self._prev_val = None

    def monitor_step(self):
        """Update the value using /proc/diskstat."""
        with os.popen('cat /proc/diskstats | grep "mmcblk0 "') as cmd_output:
            try:
                lines = cmd_output.readlines()
                if len(lines) == 0:
                    self.value = -1
                else:
                    parts = lines[0].split(' ')
                    val = int(parts[-1].strip())
                    if self._prev_val is None:
                        self.value = 0
                    else:
                        self.value = val-self._prev_val

                    self._prev_val = val
            except (ValueError, IndexError) as exp:
                self.logger.error('Error while monitoring system resources: %s', str(exp))


def generate_system_monitor(period: float, type_id: str):
    """Generate a Linux system monitor for the requested metric."""
    monitor_types = {
        'RAM': LinuxFreeRAMMonitor,
        'CPU': LinuxCPUUsageMonitor,
        'Disk': LinuxDiskUsageMonitor,
        'IO': LinuxDiskIOMonitor,
    }
    try:
        monitor_type = monitor_types[type_id]
    except KeyError as exc:
        raise UnknownSysMonTypeID from exc
    return monitor_type(period)


class SystemMonitorLogger():
    """An observer, hooks up to a sys monitor, log stats to the root logger."""

    def __init__(self, system_monitors, logging_name=''):
        """Constructor, hook up the logger to the monitor."""
        self.logger = logging.getLogger(name=logging_name)

        if type(system_monitors) is not list:
            system_monitors = [system_monitors]

        for sys_mon in system_monitors:
            if sys_mon is not None:
                sys_mon.attach(self)

    def update(self, sys_mon):
        """Update method called by net monitor subject."""
        self.logger.info('Sys Mon: %s: %f', sys_mon.type_id, sys_mon.value)
