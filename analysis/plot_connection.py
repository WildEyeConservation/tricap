"""Plot some connection monitor related value from a log file."""

import os
import sys
from datetime import datetime

import matplotlib.pyplot as plt


def get_connection_latencies_and_timestamps(target_fp, address):
    """Get the latencies and timestamps for the address connection monitor from target folder.

    Breaks in connection (i.e. unreachable) are given as 1000.
    """
    if os.path.isfile(target_fp) is False:
        print('target fp is not found : ', target_fp)
        raise Exception

    values = []
    times = []
    with open(target_fp, 'r') as log_file:
        lines = log_file.readlines()
        for line in lines:
            parts = line.split('|')
            if parts[-1][:len(' IP Address')] == ' IP Address':
                more_parts = parts[-1].replace(',', ':').split(':')
                if more_parts[1].strip() == address:
                    if more_parts[3].strip() == 'False':
                        values.append(1000.0)
                    else:
                        values.append(float(more_parts[-1].strip()))

                    times.append(datetime.strptime(parts[0].strip(), '%Y-%m-%d %H:%M:%S,%f'))

    return values, times


if __name__ == '__main__':
    if len(sys.argv) == 3:
        target_fp = os.path.join('C:/Projects/IndlovuCode/tricap/Results', sys.argv[1],
                                 'tricap_master.log')
        address = sys.argv[2]
        sys.argv.pop()
        sys.argv.pop()
    else:
        address = '8.8.8.8'
        target_fp = 'C:/Projects/IndlovuCode/tricap/Results/prelim_test5/tricap_master.log'

    title = 'Latency to %s' % address

    values, times = get_connection_latencies_and_timestamps(target_fp=target_fp, address=address)

    plt.plot(times, values, label=address, linewidth=2.0)
    plt.gcf().autofmt_xdate()
    plt.ylabel('Latency (ms)')
    plt.xlabel('Timestamp')
    plt.title(title)

    ax = plt.gca()
    for item in ([ax.title, ax.xaxis.label, ax.yaxis.label]):
        item.set_fontsize(20)

    for item in (ax.get_xticklabels() + ax.get_yticklabels()):
        item.set_fontsize(15)

    plt.show()
