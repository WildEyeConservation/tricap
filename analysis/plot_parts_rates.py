"""Rate plotting for the parts of the capture process."""

import os
import sys
import matplotlib.pyplot as plt
from plot_rate import get_target_timestamps, get_deltas_from_fp


def get_section_deltas(capture_fp, target_string1, target_string2, event_limit=2.1, return_ts_id=0):
    """Get the sectional deltas from a rate file."""
    ts1 = get_target_timestamps(capture_fp, target_string1)
    ts2 = get_target_timestamps(capture_fp, target_string2)

    deltas = []
    for index in range(len(ts1)):
        if index >= len(ts2):
            break
        deltas.append((ts2[index]-ts1[index]).total_seconds())
        if deltas[-1] > event_limit:
            print('Event at ', ts2[index])

    if return_ts_id == 0:
        ret_ts = ts1
    else:
        ret_ts = ts2

    return deltas, ret_ts


if __name__ == '__main__':
    if len(sys.argv) == 2:
        target_folder = os.path.join('C:/Projects/IndlovuCode/tricap/Results', sys.argv[1])
    else:
        target_folder = 'C:/Projects/IndlovuCode/tricap/Results/singlecam_test2'

    if os.path.isdir(target_folder) is False:
        print('No Dir')
        raise Exception

    capture_fp = None
    for filename_with_ext in os.listdir(target_folder):
        cap_id = 'rate.txt'
        if filename_with_ext[-len(cap_id):] == cap_id:
            capture_fp = os.path.join(target_folder, filename_with_ext)
            break

    if capture_fp is None:
        print('No FP')
        raise Exception

    print('before capture <-> before preview fetch')
    deltas1, ts1 = get_section_deltas(capture_fp, 'before capture \n', 'before preview fetch \n', event_limit=1.5, return_ts_id = 1)
    print('before preview fetch <-> after preview fetch')
    deltas2, ts2 = get_section_deltas(capture_fp, 'before preview fetch \n', 'after preview fetch \n', event_limit=0.5, return_ts_id = 0)
    print('before capture')
    deltas3, ts3 = get_deltas_from_fp(capture_fp, 'before capture \n')

    fig, axarr = plt.subplots(3, sharex=True)

    axarr[0].plot(ts1, deltas1, '-', linewidth=2.0)
    axarr[0].set_title('before capture <-> before preview fetch')
    axarr[1].plot(ts2, deltas2, '-', linewidth=2.0)
    axarr[1].set_title('before preview fetch <-> after preview fetch')
    axarr[2].plot(ts3, deltas3, '-', linewidth=2.0)
    axarr[2].set_title('inter-frame delta')
    fig.autofmt_xdate()
    plt.show()
