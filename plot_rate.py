"""Script to generate graphs on capture rates."""

import os

import matplotlib.pyplot as plt

from datetime import datetime

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
    timestamps = get_target_timestamps(rate_fp, target_string)

    if len(timestamps) == 0:
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
    target_cam_string = '413051000325'
    target_string = 'before capture \n'
    # target_string = 'after preview fetch \n'
    # folder_path = 'C:/Tools/rigtest2'
    folder_path = 'C:/Tools/rigtest'
    # folder_path = 'C:/Tools/flighttest1'
    # folder_path = 'C:/Tools/flighttest3'
    prefix = 'canon6dcam_'
    postix = '_outside.txt'
    # postix = '_rates.txt'
    # postix = '_flighttest1.txt'
    old_method = False

    all_deltas = []
    linehandles = []
    for cam_str in CAM_STRS:
        rate_fp = os.path.join(folder_path, prefix+cam_str+postix)
        if old_method:
            deltas = get_old_delta(rate_fp, target_string)
        else:
            deltas = get_deltas_from_fp(rate_fp, target_string)
        linehandles.append(plt.plot(deltas, label=cam_str, linewidth=2.0)[0])

    plt.legend(handles=linehandles, loc=1, fontsize=20)
    plt.ylabel('Time (s)')
    plt.xlabel('Image index')
    plt.title('Inter-frame time differences')

    ax = plt.gca()
    for item in ([ax.title, ax.xaxis.label, ax.yaxis.label]):
        item.set_fontsize(20)

    for item in (ax.get_xticklabels() + ax.get_yticklabels()):
        item.set_fontsize(15)

    plt.show()
