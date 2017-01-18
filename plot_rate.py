"""Script to generate graphs on capture rates."""

import os

import matplotlib.pyplot as plt

from datetime import datetime

from config import SERVER_LOG_DIR

def get_old_ts(fp: str, target_string: str):
    """Get timestamps from text file with target_string description."""
    timestamps = []

    with open(fp) as a_file:
        for line in a_file.readlines():
            parts = line.split(' : ')
            if parts[1] == target_string:
                timestamps.append(datetime.strptime(parts[0].split(' ')[1], '%H:%M:%S.%f'))

    return timestamps

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
    above_count = 0
    for index in range(1, len(timestamps)):
        if (timestamps[index] - timestamps[index-1]).total_seconds() > 2.1:
            above_count += 1
        deltas.append((timestamps[index] - timestamps[index-1]).total_seconds())

    print('Above count: %d Above rate: %f' % (above_count, float(above_count)/len(deltas)))

    return deltas

def get_old_delta(fp: str, target_string: str):
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

if __name__ == '__main__':
    # setup variables
    # target_cam = 0
    target_cam_string = '413051000325'
    target_string = 'before capture \n'
    # rate_fp = os.path.join(SERVER_LOG_DIR, 'dummycam_' + str(target_cam) + '_rates.txt')
    #
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_' + target_cam_string + '_rates.txt')
    # singletest = get_deltas_from_fp(rate_fp, target_string)

    print('singletest_413')
    rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_413051000325_rates_1.txt')
    singletest_413 = get_deltas_from_fp(rate_fp, target_string)

    print('singletest_032')
    rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_032024003117_rates_1.txt')
    singletest_032 = get_deltas_from_fp(rate_fp, target_string)

    print('singletest_023')
    rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_023052000180_rates_1.txt')
    singletest_023 = get_deltas_from_fp(rate_fp, target_string)

    # print('singletest_413')
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_413051000325_rates_0.txt')
    # singletest_413_0 = get_old_delta(rate_fp, 'before capture\n')

    print('singletest_413_2')
    rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_413051000325_rates_2.txt')
    singletest_413_2 = get_deltas_from_fp(rate_fp, target_string)

    print('singletest_413_3')
    rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_413051000325_rates_3.txt')
    singletest_413_3 = get_deltas_from_fp(rate_fp, target_string)

    print('singletest_413_17')
    rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_413051000325_rates_17.txt')
    singletest_413_17 = get_deltas_from_fp(rate_fp, target_string)

    print('singletest_413_18')
    rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_413051000325_rates_18.txt')
    singletest_413_18 = get_deltas_from_fp(rate_fp, target_string)
    #
    # print('singletest_413_6')
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_413051000325_rates_6.txt')
    # singletest_413_6 = get_deltas_from_fp(rate_fp, target_string)
    #
    # print('singletest_413_7')
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_413051000325_rates_7.txt')
    # singletest_413_7 = get_deltas_from_fp(rate_fp, target_string)
    #
    # print('singletest_413_8')
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_413051000325_rates_8.txt')
    # singletest_413_8 = get_deltas_from_fp(rate_fp, target_string)
    #
    # print('singletest_023_9')
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_023052000180_rates_9.txt')
    # singletest_023_9 = get_deltas_from_fp(rate_fp, target_string)
    #
    # print('singletest_023_10')
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_023052000180_rates_10.txt')
    # singletest_023_10 = get_deltas_from_fp(rate_fp, target_string)
    #
    # print('singletest_023_11')
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_023052000180_rates_11.txt')
    # singletest_023_11 = get_deltas_from_fp(rate_fp, target_string)
    #
    # print('singletest_023_12')
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_023052000180_rates_12.txt')
    # singletest_023_12 = get_deltas_from_fp(rate_fp, target_string)
    #
    # print('singletest_023_14')
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_023052000180_rates_14.txt')
    # singletest_023_14 = get_deltas_from_fp(rate_fp, target_string)
    #
    # print('singletest_023_15')
    # rate_fp = os.path.join('C:/Tools/singletest/canon6dcam_023052000180_rates_15.txt')
    # singletest_023_15 = get_deltas_from_fp(rate_fp, target_string)

    # rate_fp = os.path.join('C:/Tools/battery_all_test1/canon6dcam_' + target_cam_string + '_rates.txt')
    # delta_all_on_battery = get_deltas_from_fp(rate_fp, target_string)
    #
    # rate_fp = os.path.join('C:/Tools/battery_rpi_on_gorilla/canon6dcam_' + target_cam_string + '_rates.txt')
    # delta_rpi_on_gorillla = get_deltas_from_fp(rate_fp, target_string)

    # plot
    linehandles = []
    # linehandles.append(plt.plot(singletest_413, label='singletest_413')[0])
    # linehandles.append(plt.plot(singletest_023_11, label='singletest_023_11')[0])
    # linehandles.append(plt.plot(singletest_023_12, label='singletest_023_12')[0])
    # linehandles.append(plt.plot(singletest_023_15, label='singletest_023_15')[0])
    # linehandles.append(plt.plot(singletest_032, label='singletest_032')[0])
    linehandles.append(plt.plot(singletest_413_18, label='singletest_413_18')[0])
    # linehandles.append(plt.plot(singletest_413_8, label='singletest_413_8')[0])
    # linehandles.append(plt.plot(singletest_023_9, label='singletest_023_9')[0])
    # linehandles.append(plt.plot(delta_all_on_battery, label='all_on_battery')[0])
    # linehandles.append(plt.plot(delta_rpi_on_gorillla, label='rpi_on_gorilla')[0])

    plt.legend(handles=linehandles, loc=4)
    plt.show()
