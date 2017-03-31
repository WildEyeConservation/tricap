"""Plot some system monitor related value from a log file."""

import os
import sys
from datetime import datetime

import matplotlib.pyplot as plt


def get_sys_vals_and_timestamps(target_fp, type_id):
    """Get the values and timestamps for the type_id sys monitor from target folder."""
    if os.path.isfile(target_fp) is False:
        print('target fp is not found : ', target_fp)
        raise Exception

    values = []
    times = []
    with open(target_fp, 'r') as log_file:
        lines = log_file.readlines()
        for line in lines:
            parts = line.split('|')
            if parts[-1][:len(' Sys Mon')] == ' Sys Mon':
                more_parts = parts[-1].split(':')
                if more_parts[1].strip() == type_id:
                    values.append(float(more_parts[-1].strip()))
                    times.append(datetime.strptime(parts[0].strip(), '%Y-%m-%d %H:%M:%S,%f'))

    return values, times


if __name__ == '__main__':
    if len(sys.argv) == 3:
        target_fp = os.path.join('C:/Projects/IndlovuCode/tricap/Results', sys.argv[1],
                                 'tricap_master.log')
        type_id = sys.argv[2]
        sys.argv.pop()
        sys.argv.pop()
    else:
        type_id = 'Linux CPU'
        target_fp = 'C:/Projects/IndlovuCode/tricap/Results/prelim_test5/tricap_master.log'

    title = type_id

    values, times = get_sys_vals_and_timestamps(target_fp=target_fp, type_id=type_id)

    plt.plot(times, values, label=type_id, linewidth=2.0)
    plt.gcf().autofmt_xdate()
    plt.ylabel('Value')
    plt.xlabel('Timestamp')
    plt.title(title)

    ax = plt.gca()
    for item in ([ax.title, ax.xaxis.label, ax.yaxis.label]):
        item.set_fontsize(20)

    for item in (ax.get_xticklabels() + ax.get_yticklabels()):
        item.set_fontsize(15)

    plt.show()
