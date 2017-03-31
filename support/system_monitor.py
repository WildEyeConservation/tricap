"""System Monitor - Classes to monitor the state of the system you are running on."""

import os
import re
import logging
from abc import ABCMeta
from .basic import PeriodicMonitor, UnknownOperatingSystem


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


class WindowsFreeRAMMonitor(SystemMonitor):
    """Monitor how much free RAM in MB is available in Windows."""

    def __init__(self, period: float):
        """Constructor, set the type_id to RAM."""
        super(WindowsFreeRAMMonitor, self).__init__(period)

        self.type_id = 'Windows RAM'

    def monitor_step(self):
        """Update the value with the amount of free RAM available."""
        with os.popen('wmic OS get FreePhysicalMemory /Value') as cmd_output:
            lines = cmd_output.readlines()
            val = float(lines[4].split('=')[1].strip())
            self.value = val/1000.0


class WindowsCPUUsageMonitor(SystemMonitor):
    """Monitor how much the CPU is used as a percentage in Windows."""

    def __init__(self, period):
        """Constructor, lower limites the period to 2 seconds."""
        if period < 2:
            period = 2

        super(WindowsCPUUsageMonitor, self).__init__(period)

        self.type_id = 'Windows CPU'
        self.unit = '%'

    def monitor_step(self):
        """Update the value with the percentage of CPU used."""
        with os.popen('wmic cpu get loadpercentage') as cmd_output:
            lines = cmd_output.readlines()
            self.value = float(lines[2].strip())


class WindowsDiskUsageMonitor(SystemMonitor):
    """Monitor how much the space is left on HD in MB in Windows."""

    def __init__(self, period, disk_fp=None):
        """Constructor, can change the defaul disk to check."""
        if disk_fp is None:
            self.disk_fp = 'c:'
        else:
            self.disk_fp = disk_fp

        super(WindowsDiskUsageMonitor, self).__init__(period)

        self.type_id = 'Windows Disk'

    def monitor_step(self):
        """Update the value with the free space on the disk in MB."""
        with os.popen('dir %s' % self.disk_fp) as cmd_output:
            lines = cmd_output.readlines()
            val = lines[-1].split(')')[1].split('bytes')[0]
            val = re.sub("[^0-9]", "", val.strip())
            self.value = float(val)/1000.0/1000.0


class LinuxFreeRAMMonitor(SystemMonitor):
    """Monitor how much free RAM in MB is available in Linux."""

    def __init__(self, period: float):
        """Constructor, set the type_id to RAM."""
        super(LinuxFreeRAMMonitor, self).__init__(period)

        self.type_id = 'Linux RAM'

    def monitor_step(self):
        """Update the value with the amount of free RAM available."""
        with os.popen('free') as cmd_output:
            lines = cmd_output.readlines()
            val = float(lines[1].split(' ')[-1].strip())
            self.value = val/1000.0


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
            line = cmd_output.readline()
            line = cmd_output.readline()
            parts = [part for part in line.split(' ') if part != '']
            # adding together the user and the kernel space cpu stats
            self.value = float(parts[1])+float(parts[3])


class LinuxDiskUsageMonitor(SystemMonitor):
    """Monitor how much the space is left on HD in MB in Linux."""

    def __init__(self, period):
        """Constructor, can change the defaul disk to check."""
        super(LinuxDiskUsageMonitor, self).__init__(period)

        self.type_id = 'Linux Disk'

    def monitor_step(self):
        """Update the value with the available space in MB on the root."""
        with os.popen('df | grep root') as cmd_output:
            lines = cmd_output.readlines()
            parts = lines[0].split(' ')
            parts = [part for part in parts if part != '']
            self.value = float(parts[3])/1000.0


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


def generate_system_monitor(period: float, type_id: str, add_arg: str = None):
    """Generate the appropriate system monitor based on OS type and the type asked for."""
    sys_mon = None
    if os.name == 'nt':
        if type_id == 'RAM':
            sys_mon = WindowsFreeRAMMonitor(period)
        elif type_id == 'CPU':
            sys_mon = WindowsCPUUsageMonitor(period)
        elif type_id == 'Disk':
            sys_mon = WindowsDiskUsageMonitor(period, add_arg)
        elif type_id == 'IO':
            sys_mon = None
        else:
            raise UnknownSysMonTypeID
    elif os.name == 'posix':
        if type_id == 'RAM':
            sys_mon = LinuxFreeRAMMonitor(period)
        elif type_id == 'CPU':
            sys_mon = LinuxCPUUsageMonitor(period)
        elif type_id == 'Disk':
            sys_mon = LinuxDiskUsageMonitor(period)
        elif type_id == 'IO':
            sys_mon = LinuxDiskIOMonitor(period)
        else:
            raise UnknownSysMonTypeID
    else:
        raise UnknownOperatingSystem

    return sys_mon


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
