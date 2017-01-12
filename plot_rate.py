"""Script to generate graphs on capture rates."""

import os

import matplotlib.pyplot as plt

from datetime import datetime

from config import SERVER_LOG_DIR


def get_target_timestamps(fp: str, target_string: str):
    """Get timestamps from text file with target_string description."""
    timestamps = []

    with open(fp) as a_file:
        for line in a_file.readlines():
            parts = line.split(' : ')

            if parts[1] == target_string:
                timestamps.append(datetime.strptime(parts[0].split(' ')[1], '%H:%M:%S.%f'))

    return timestamps


if __name__ == '__main__':
    # setup variables
    target_cam = 0
    target_string = 'before capture\n'
    rate_fp = os.path.join(SERVER_LOG_DIR, 'dummycam_' + str(target_cam) + '_rates.txt')

    # get timestamps
    timestamps = get_target_timestamps(rate_fp, target_string)
    print('number of timestamps : %d' % len(timestamps))

    # process
    deltas = []
    for index in range(1, len(timestamps)):
        deltas.append((timestamps[index] - timestamps[index-1]).total_seconds())
    print('Number of deltas %d' % len(deltas))

    # plot
    plt.plot(deltas)
    plt.show()
