import os

# file_to_split = 'C:/Tools/flighttest1/canon6dcam_413051000325_rates.txt'
file_to_split = 'C:/Tools/flighttest1/canon6dcam_023052000180_rates.txt'
# file_to_split = 'C:/Tools/flighttest1/canon6dcam_032024003117_rates.txt'

count = 0
n_file = None
with open(file_to_split, 'r') as sfile:
    for line in sfile.readlines():
        parts = line.split(' : ')
        if parts[1] == 'Rate Logging Started \n':
            n_fp = 'C:/Tools/flighttest1/canon6dcam_023052000180_%d.txt' % count
            count += 1
            n_file = open(n_fp, 'w')
        else:
            n_file.write(line)
