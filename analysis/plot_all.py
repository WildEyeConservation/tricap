"""Plot all the information on one big sheet."""

import os
import sys
import re

import matplotlib.pyplot as plt
from datetime import datetime, timedelta

from plot_rate import get_deltas_and_timestamps
from plot_connection import get_connection_latencies_and_timestamps
from plot_sys import get_sys_vals_and_timestamps

REJECTION_PATTERNS = ['brcmfmac: brcmf_sdio_hdparse: seq .*: sequence number error, expect']


def check_if_useful_syslog(message: str):
    """Use RegEx to reject boring syslog messages."""
    for pat in REJECTION_PATTERNS:
        if re.search(pat, message) is not None:
            return False

    return True


def get_timestamps_from_syslog(target_fp):
    """Get timestamps of events from syslog."""
    if os.path.isfile(target_fp) is False:
        print("target_fp does not exist ", target_fp)
        raise Exception

    times = []
    vals = []
    msgs = []
    with open(target_fp, 'r') as log_file:
        lines = log_file.readlines()
        for line in lines:
            parts = line.split(' rpi3-desktop ')
            if check_if_useful_syslog(parts[1]) is True:
                ts = datetime.strptime(parts[0].replace("  1", ' 01'), '%b %d %H:%M:%S').replace(year=2017)
                if ts not in times:
                    ts_before = ts - timedelta(microseconds=1)

                    ts_after = ts + timedelta(microseconds=1)

                    times.append(ts_before)
                    vals.append(0)
                    msgs.append(line)
                    times.append(ts)
                    vals.append(1)
                    msgs.append(line)
                    times.append(ts_after)
                    vals.append(0)
                    msgs.append(line)

    return vals, times, msgs


if __name__ == '__main__':
    if len(sys.argv) == 2:
        target_folder = os.path.join('C:/Projects/IndlovuCode/tricap/Results', sys.argv[1])
        sys.argv.pop()
        sys.argv.pop()
    else:
        target_folder = 'C:/Projects/IndlovuCode/tricap/Results/prelim_test5'

    # target_fp = os.path.join(target_folder, 'tricap_master.log.2017-02-01')
    target_fp = os.path.join(target_folder, 'tricap_master.log')

    fig, axarr = plt.subplots(8, sharex=True)

    # inter frame deltas
    if_all_deltas, if_all_ts = get_deltas_and_timestamps(target_folder=target_folder,
                                                         target_string='before capture \n')

    linehandles = []
    for index, deltas in enumerate(if_all_deltas):
        linehandles.append(axarr[0].plot(if_all_ts[index], deltas)[0])

    axarr[0].set_title('Inter-frame deltas')

    # sys vals
    values, times = get_sys_vals_and_timestamps(target_fp=target_fp, type_id='Linux RAM')
    axarr[1].plot(times, values)
    axarr[1].set_title('Linux RAM')

    values, times = get_sys_vals_and_timestamps(target_fp=target_fp, type_id='Linux CPU')
    axarr[2].plot(times, values)
    axarr[2].set_title('Linux CPU')

    values, times = get_sys_vals_and_timestamps(target_fp=target_fp, type_id='Linux Disk')
    axarr[3].plot(times, values)
    axarr[3].set_title('Linux Disk')

    values, times = get_sys_vals_and_timestamps(target_fp=target_fp, type_id='Linux IO')
    axarr[4].plot(times, values)
    axarr[4].set_title('Linux IO')

    # connection values
    values, times = get_connection_latencies_and_timestamps(target_fp=target_fp, address='8.8.8.8')
    axarr[5].plot(times, values)
    axarr[5].set_title('8.8.8.8 Latency')

    values, times = get_connection_latencies_and_timestamps(target_fp=target_fp,
                                                            address='192.168.88.1')
    axarr[6].plot(times, values)
    axarr[6].set_title('192.168.88.1 Latency')

    # sys log event
    values, times, syslog_msgs = get_timestamps_from_syslog(os.path.join(target_folder, 'syslog.1'))

    def on_syslog_pick(event):
        """Syslog event to run."""
        for ind in event.ind:
            print('on syslog :', ind, syslog_msgs[ind])

    plotline = axarr[7].plot(times, values, picker=True)
    fig.canvas.mpl_connect('pick_event', on_syslog_pick)
    axarr[7].set_title('syslog events')

    fig.autofmt_xdate()
    plt.show()
