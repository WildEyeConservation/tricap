"""Plot some system monitor related value from a log file."""

import os
from datetime import datetime

import matplotlib.pyplot as plt

if __name__ == '__main__':
    target_fp = 'C:/Projects/IndlovuCode/tricap/Results/prelim_test1/tricap_master.log'
    type_id = 'Linux Disk'
    title = 'Linux Disk Usage'

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

    times_vals = zip(times, values)
    for tv in times_vals:
        print(tv)

    plt.plot(times, values, label=type_id, linewidth=2.0)
    plt.gcf().autofmt_xdate()
    plt.ylabel('Sample')
    plt.xlabel('Disk Space Free')
    plt.title('Disk Space Free')

    ax = plt.gca()
    for item in ([ax.title, ax.xaxis.label, ax.yaxis.label]):
        item.set_fontsize(20)

    for item in (ax.get_xticklabels() + ax.get_yticklabels()):
        item.set_fontsize(15)

    plt.show()
