"""Script to generate graphs on capture rates."""

import os

import matplotlib.pyplot as plt

from datetime import datetime


class PlotRateException(Exception):
    """An exception for if something goes wrong with plotting the rate."""

    pass


CAM_413_STR = '413051000325'
CAM_023_STR = '023052000180'
CAM_032_STR = '032024003117'

CAM_STRS = [CAM_413_STR, CAM_023_STR, CAM_032_STR]


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
                timestamps.append(datetime.strptime(parts[0].split(' ')[1], '%H:%M:%S,%f'))
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
        deltas.append((timestamps[index] - timestamps[index-1]).total_seconds())

    print('Above count: %d Above rate: %f' % (above_count, float(above_count)/len(deltas)))

    return deltas


if __name__ == '__main__':
    # setup variables
    target_folder = 'C:/Projects/IndlovuCode/tricap/Results/prelim_test3'
    _, test_name = os.path.split(target_folder)
    title = 'Inter-frame time differences for %s' % test_name
    target_string = 'before capture \n'
    # prefix = 'canon6dcam_'
    # postix = '_outside.txt'

    if os.path.isdir(target_folder) is False:
        print("Error, target folder does not exist.")
        raise PlotRateException

    capture_fps = []
    for filename_with_ext in os.listdir(target_folder):
        filename, ext = os.path.splitext(filename_with_ext)
        if ext == '.txt' and filename != 'readme':
            capture_fps.append(os.path.join(target_folder, filename_with_ext))

    if len(capture_fps) == 0:
        print("Error, no text files found within the target folder")
        raise PlotRateException

    all_deltas = []
    linehandles = []
    for capture_fp in capture_fps:
        deltas = get_deltas_from_fp(capture_fp, target_string)
        _, capture_filename_with_ext = os.path.split(capture_fp)
        linehandles.append(plt.plot(deltas, label=capture_filename_with_ext, linewidth=2.0)[0])

    plt.legend(handles=linehandles, loc=1, fontsize=20)
    plt.ylabel('Time (s)')
    plt.xlabel('Image index')
    plt.title(title)

    ax = plt.gca()
    for item in ([ax.title, ax.xaxis.label, ax.yaxis.label]):
        item.set_fontsize(20)

    for item in (ax.get_xticklabels() + ax.get_yticklabels()):
        item.set_fontsize(15)

    plt.show()
