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

def get_timestamps_from_flasklogs(target_fp):
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
            parts = line.split(' | _log | ')
            try:
                ts = datetime.strptime(parts[0], '%Y-%m-%d %H:%M:%S,%f')
            except ValueError:
                continue
            if len(times) == 0 or ts > times[-1]:
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


def get_wlan_signal_strength(target_fp):
    """Get the signal strength of the wireless lan connection."""
    if os.path.isfile(target_fp) is False:
        print('target fp is not found : ', target_fp)
        raise Exception

    values = []
    times = []
    with open(target_fp, 'r') as log_file:
        lines = log_file.readlines()
        for line in lines:
            parts = line.split('|')
            if parts[-1][:len(' Network Name')] == ' Network Name':
                more_parts = parts[-1].replace(',', ':').split(':')
                # import pdb; pdb.set_trace()

                if more_parts[-1].strip()[-1] == '%':
                    values.append(float(more_parts[-1].strip()[:-1]))
                else:
                    values.append(0)

                times.append(datetime.strptime(parts[0].strip(), '%Y-%m-%d %H:%M:%S,%f'))

    return values, times


if __name__ == '__main__':
    plot_syslog = False
    plot_flask = False
    plot_count = 7
    target_folder = 'C:/Projects/IndlovuCode/tricap/Results/prelim_test5'

    if len(sys.argv) > 1:
        target_folder = os.path.join('C:/Projects/IndlovuCode/tricap/Results', sys.argv[1])

    if len(sys.argv) > 2:
        if sys.argv[2] == '1':
            plot_syslog = True
            plot_count += 1

    if len(sys.argv) > 3:
        if sys.argv[3] == '1':
            plot_flask = True
            plot_count += 1


    # target_fp = os.path.join(target_folder, 'tricap_master.log.2017-02-01')
    target_fp = os.path.join(target_folder, 'tricap_master.log')

    fig, axarr = plt.subplots(plot_count, sharex=True)

    # inter frame deltas
    if_all_deltas, if_all_ts = get_deltas_and_timestamps(target_folder=target_folder,
                                                         target_string='before capture \n')

    print('number of deltas')
    linehandles = []
    for index, deltas in enumerate(if_all_deltas):
        linehandles.append(axarr[0].plot(if_all_ts[index], deltas)[0])
        print(len(deltas))

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

    # values, times = get_sys_vals_and_timestamps(target_fp=target_fp, type_id='Linux IO')
    # axarr[4].plot(times, values)
    # axarr[4].set_title('Linux IO')

    # signal strength
    values, times = get_wlan_signal_strength(target_fp=target_fp)
    axarr[4].plot(times, values)
    axarr[4].set_title('Signal Strength')
    # connection values
    values, times = get_connection_latencies_and_timestamps(target_fp=target_fp, address='8.8.8.8')
    axarr[5].plot(times, values)
    axarr[5].set_title('8.8.8.8 Latency')

    values, times = get_connection_latencies_and_timestamps(target_fp=target_fp,
                                                            address='192.168.88.1')
    axarr[6].plot(times, values)
    axarr[6].set_title('192.168.88.1 Latency')

    axis_index = 6
    if plot_syslog:
        values, times, syslog_msgs = get_timestamps_from_syslog(os.path.join(target_folder, 'syslog'))

        def on_syslog_pick(event):
            """Syslog event to run."""
            for ind in event.ind:
                print('on syslog :', ind, syslog_msgs[ind])

        axis_index += 1
        plotline = axarr[axis_index].plot(times, values, picker=True)
        fig.canvas.mpl_connect('pick_event', on_syslog_pick)
        axarr[axis_index].set_title('syslog events')

    # flask log event
    if plot_flask:
        values, times, flask_msgs = get_timestamps_from_flasklogs(os.path.join(target_folder, 'tricap_flask.log'))

        def on_flask_pick(event):
            """Flask event to run."""
            for ind in event.ind:
                print('on flasklog :', ind, flask_msgs[ind])

        axis_index += 1
        plotline = axarr[axis_index].plot(times, values, picker=True)
        fig.canvas.mpl_connect('pick_event', on_flask_pick)
        axarr[axis_index].set_title('flask requests')

    fig.autofmt_xdate()
    plt.show()
