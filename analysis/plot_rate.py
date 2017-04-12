"""Script to generate graphs on capture rates."""

import os
import sys

import matplotlib.pyplot as plt

from datetime import datetime


class PlotRateException(Exception):
    """An exception for if something goes wrong with plotting the rate."""

    pass


def get_old_ts(fp: str, target_string: str):
    """Get timestamps from text file with target_string description using the old method."""
    timestamps = []

    with open(fp) as a_file:
        for line in a_file.readlines():
            parts = line.split(' : ')
            if parts[1] == target_string:
                timestamps.append(datetime.strptime(parts[0].split(' ')[1], '%H:%M:%S.%f'))

    return timestamps


def get_old_delta(fp: str, target_string: str):
    """Get timestamps from text file with target_string description using the old method."""
    timestamps = get_old_ts(fp, target_string)

    # process
    deltas = []
    above_count = 0
    for index in range(1, len(timestamps)):
        if (timestamps[index] - timestamps[index-1]).total_seconds() > 2.1:
            print('Event at ', timestamps[index])
            above_count += 1
        deltas.append((timestamps[index] - timestamps[index-1]).total_seconds())

    print('Above count: %d Above rate: %f' % (above_count, float(above_count)/len(deltas)))

    return deltas


def get_target_timestamps(fp: str, target_string: str):
    """Get timestamps from text file with target_string description."""
    if os.path.isfile(fp) is False:
        raise Exception

    timestamps = []

    image_count = 0

    with open(fp) as a_file:
        for line in a_file.readlines():
            parts = line.split(' : ')

            if len(parts) < 3:
                continue

            if parts[2] == target_string:
                try:
                    timestamps.append(datetime.strptime(parts[0].split(' : ')[0], '%Y-%m-%d %H:%M:%S,%f'))
                except ValueError as e:
                    timestamps.append(datetime.strptime(parts[0].split(' : ')[0], '%Y-%m-%d %H:%M:%S'))
                if image_count == 0:
                    image_count = int(parts[1])
                else:
                    image_count += 1
                    if image_count != int(parts[1]):
                        print("ImageCount error %d != %d" % (image_count, int(parts[1])))

    return timestamps


def get_deltas_from_fp(fp: str, target_string: str):
    """Get timestamps from text file with target_string description."""
    timestamps = get_target_timestamps(fp, target_string)

    if len(timestamps) == 0:
        print("No timestamps obtained from file ", fp)
        raise Exception

    # process
    deltas = []
    above_count = 0
    for index in range(1, len(timestamps)):
        if (timestamps[index] - timestamps[index-1]).total_seconds() > 2.1:
            above_count += 1
            print('Event at ', timestamps[index])
        deltas.append((timestamps[index] - timestamps[index-1]).total_seconds())

    print('Above count: %d Above rate: %f' % (above_count, float(above_count)/len(deltas)))

    return deltas, timestamps[1:]


def get_deltas_and_timestamps(target_folder, target_string):
    """Get the deltas and the timestamps from the target folder for multiple cam rate files."""
    if os.path.isdir(target_folder) is False:
        print("Error, target folder does not exist.")
        raise PlotRateException

    capture_fps = []
    for filename_with_ext in os.listdir(target_folder):
        filename, ext = os.path.splitext(filename_with_ext)
        if ext == '.txt' and filename != 'readme' and filename != 'ReadMe' and filename != 'launch_test' and filename != 'python_launch_test':
            capture_fps.append(os.path.join(target_folder, filename_with_ext))

    if len(capture_fps) == 0:
        print("Error, no text files found within the target folder")
        raise PlotRateException

    all_deltas = []
    all_ts = []
    for capture_fp in capture_fps:
        deltas, ts = get_deltas_from_fp(capture_fp, target_string)
        all_deltas.append(deltas)
        all_ts.append(ts)

    return all_deltas, all_ts


if __name__ == '__main__':
    if len(sys.argv) == 3:
        target_folder = os.path.join('C:/Projects/IndlovuCode/tricap/Results', sys.argv[1])
        target_string = sys.argv[2] + ' \n'
        sys.argv.pop()
        sys.argv.pop()
    else:
        target_string = 'before capture \n'
        target_folder = 'C:/Projects/IndlovuCode/tricap/Results/prelim_test5'

    # setup variables
    _, test_name = os.path.split(target_folder)
    title = 'Inter-frame time differences for %s' % test_name

    all_deltas, all_ts = get_deltas_and_timestamps(target_folder=target_folder,
                                                   target_string=target_string)

    linehandles = []
    for index, deltas in enumerate(all_deltas):
        linehandles.append(plt.plot(all_ts[index], deltas, label=str(index), linewidth=2.0)[0])

    plt.gcf().autofmt_xdate()
    plt.legend(handles=linehandles, loc=1, fontsize=20)
    plt.ylabel('Time (s)')
    plt.xlabel('Timestamps')
    plt.title(title)

    ax = plt.gca()
    for item in ([ax.title, ax.xaxis.label, ax.yaxis.label]):
        item.set_fontsize(20)

    for item in (ax.get_xticklabels() + ax.get_yticklabels()):
        item.set_fontsize(15)

    plt.show()
