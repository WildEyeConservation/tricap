import psutil
import shutil
import datetime
import progressbar
import threading
import os.path
import time
import exifread

drive_list = []
num_files = 0
serial_number = 3*[""]


def copy_directory(src, dest):
    try:
        shutil.copytree(src, dest)
    # Directories are the same
    except shutil.Error as e:
        print('Directory not copied. Error: %s' % e)
    # Any error saying that the directory doesn't exist
    except OSError as e:
        print('Directory not copied. Error: %s' % e)


def copy_thread(drv, num):
    print(drv)
    copy_directory(os.path.join(drive_list[num], 'DCIM'), os.path.join(drv, str(datetime.date.today()), Sortie, 'images', 'Camera'+str(num)))


def number_files(path):
    num_fil = len([f for f in os.listdir(path)
                      if os.path.isfile(os.path.join(path, f))])
    return num_fil

# ******************************************************************************************************************** #
# Start the program
print("Starting")
drive = psutil.disk_partitions()
for k in range(drive.__len__()):
    print(str(k) + ": " + str(drive[k]))

internal = int(input("Choose internal drive from list above and enter number: "))
drive[0], drive[internal] = drive[internal], drive[0]
external = int(input("Choose internal drive from list above and enter number: "))
drive[1], drive[external] = drive[external], drive[1]

for i in range(drive.__len__()):
    if drive[i].fstype == 'exFAT':  # 'FAT32'
        drive_list.append(drive[i].device)

# Change the drive_list based on the exif data serial number
# Read exif data to determine which camera is used
for j in range(drive_list.__len__()):
    first_file = os.listdir(os.path.join(drive_list[j], 'DCIM', '100CANON'))[0]  # Put in threads area
    file = open(os.path.join(drive_list[j], 'DCIM', '100CANON', first_file), 'rb')
    tags = exifread.process_file(file)

    if 'EXIF BodySerialNumber' in tags.keys():
        serial_number[j] = tags['EXIF BodySerialNumber']

if drive_list.__len__() == 3:
    # Change the drive list here
    for j in range(drive_list.__len__()):
        if str(serial_number[j]) == "032024003117":
            serial_number[0], serial_number[j] = serial_number[j], serial_number[0]
            drive_list[0], drive_list[j] = drive_list[j], drive_list[0]
        elif str(serial_number[j]) == "023052000180":
            serial_number[1], serial_number[j] = serial_number[j], serial_number[1]
            drive_list[1], drive_list[j] = drive_list[j], drive_list[1]
        elif str(serial_number[j]) == "413051000325":
            serial_number[2], serial_number[j] = serial_number[j], serial_number[2]
            drive_list[2], drive_list[j] = drive_list[j], drive_list[2]
print(serial_number)

for j in range(drive_list.__len__()):
    path = os.path.join(drive_list[j], 'DCIM', '100CANON')
    num_files1 = len([f for f in os.listdir(path)
                      if os.path.isfile(os.path.join(path, f))])
    path = os.path.join(drive_list[j], 'DCIM', '101CANON')
    num_files2 = len([f for f in os.listdir(path)
                      if os.path.isfile(os.path.join(path, f))])
    num_files += (num_files1 + num_files2)

print(num_files)
threads = []
nums = 0
Sortie = "Sortie0"

if os.path.isdir(os.path.join(drive[1].device, str(datetime.date.today()), 'Sortie0')):
    while os.path.isdir(os.path.join(drive[1].device, str(datetime.date.today()), Sortie)):
        nums += 1
        Sortie = "Sortie" + str(nums)
print(Sortie)

for j in range(drive_list.__len__()):  # starts two threads per drive_list
    print(drive_list[j])
    # threads0 = threading.Thread(target=copy_thread, args=(drive[0].device, j,))  # Internal drive
    threads1 = threading.Thread(target=copy_thread, args=(drive[1].device, j,))  # External drive
    # threads0.start()
    threads1.start()

print("Starting file copy")
time.sleep(2)

bar = progressbar.ProgressBar()
for i in bar(range(num_files)):
    i = 0
    if os.path.isdir(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera0', '100CANON')):
        i += number_files(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera0', '100CANON'))
    if os.path.isdir(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera1', '100CANON')):
        i += number_files(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera1', '100CANON'))
    if os.path.isdir(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera2', '100CANON')):
        i += number_files(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera2', '100CANON'))
    if os.path.isdir(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera0', '101CANON')):
        i += number_files(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera0', '101CANON'))
    if os.path.isdir(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera1', '101CANON')):
        i += number_files(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera1', '101CANON'))
    if os.path.isdir(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera2', '101CANON')):
        i += number_files(os.path.join(drive[1].device, str(datetime.date.today()), Sortie, 'images', 'Camera2', '101CANON'))
    bar.update(i)
    time.sleep(1)

# Rename folder to make more sense for the user
# for r in range(2):
for r in range(1, 2):
    if os.path.isdir(os.path.join(drive[r].device, str(datetime.date.today()), Sortie, 'images', 'Camera0')):
        os.rename(os.path.join(drive[r].device, str(datetime.date.today()), Sortie, 'images', 'Camera0'),
                  os.path.join(drive[r].device, str(datetime.date.today()), Sortie, 'images', 'Camera Left'))
    if os.path.isdir(os.path.join(drive[r].device, str(datetime.date.today()), Sortie, 'images', 'Camera1')):
        os.rename(os.path.join(drive[r].device, str(datetime.date.today()), Sortie, 'images', 'Camera1'),
                  os.path.join(drive[r].device, str(datetime.date.today()), Sortie, 'images', 'Camera Centre'))
    if os.path.isdir(os.path.join(drive[r].device, str(datetime.date.today()), Sortie, 'images', 'Camera2')):
        os.rename(os.path.join(drive[r].device, str(datetime.date.today()), Sortie, 'images', 'Camera2'),
                  os.path.join(drive[r].device, str(datetime.date.today()), Sortie, 'images', 'Camera Right'))

print("Finished")
