"""Script to generate graphs on capture rates."""

import os

import matplotlib.pyplot as plt

from datetime import datetime

from config import SERVER_LOG_DIR


def get_target_timestamps(fp: str, target_string: str):
    """Get timestamps from text file with target_string description."""
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
    timestamps = get_target_timestamps(rate_fp, target_string)

    # process
    deltas = []
    for index in range(1, len(timestamps)):
        if (timestamps[index] - timestamps[index-1]).total_seconds() > 5:
            print('Difference greater than 5')
            print(index)
            print(timestamps[index])
            print(timestamps[index-1])
        deltas.append((timestamps[index] - timestamps[index-1]).total_seconds())

    return deltas
if __name__ == '__main__':
    # setup variables
    # target_cam = 0
    target_cam_string = '413051000325'
    target_string = 'before capture \n'
    # rate_fp = os.path.join(SERVER_LOG_DIR, 'dummycam_' + str(target_cam) + '_rates.txt')
    #
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_' + target_cam_string + '_rates.txt')
    # singletest = get_deltas_from_fp(rate_fp, target_string)

    rate_fp = os.path.join('C:/Projects/IndlovuCode/tricap/Code/tricap/logs/dummycam_0_rates.txt')
    singletest = get_deltas_from_fp(rate_fp, target_string)

    # rate_fp = os.path.join('C:/Tools/battery_all_test1/canon6dcam_' + target_cam_string + '_rates.txt')
    # delta_all_on_battery = get_deltas_from_fp(rate_fp, target_string)
    #
    # rate_fp = os.path.join('C:/Tools/battery_rpi_on_gorilla/canon6dcam_' + target_cam_string + '_rates.txt')
    # delta_rpi_on_gorillla = get_deltas_from_fp(rate_fp, target_string)

    # plot
    linehandles = []
    linehandles.append(plt.plot(singletest, label='singletest')[0])
    # linehandles.append(plt.plot(delta_all_on_battery, label='all_on_battery')[0])
    # linehandles.append(plt.plot(delta_rpi_on_gorillla, label='rpi_on_gorilla')[0])

    plt.legend(handles=linehandles, loc=4)
    plt.show()
