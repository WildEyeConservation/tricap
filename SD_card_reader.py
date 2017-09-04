import psutil, shutil, datetime, progressbar, threading, os.path
import time, exifread, platform
from math import ceil

sd_card_list = []
num_files = 0
camera_serial_number = 3 * [""]
user_input = " "
path_list = []
path_count = 0
path_common = ['100CANON', '101CANON', '102CANON', '103CANON', '104CANON']


def copy_directory(source, destination):
    try:
        shutil.copytree(source, destination)
    # Directories are the same
    except shutil.Error as e:
        print('Directory not copied. Error: %s' % e)
    # Any error saying that the directory doesn't exist
    except OSError as e:
        print('Directory not copied. Error: %s' % e)


def copy_thread(drive, camera_num):
    print(drive)
    copy_directory(os.path.join(sd_card_list[camera_num], 'DCIM'),
                   os.path.join(drive, str(datetime.date.today()), Sortie, 'images', 'Camera' + str(camera_num)))


def count_number_of_files(path):
    total_number_of_files = len([f for f in os.listdir(path)
                                 if os.path.isfile(os.path.join(path, f))])
    return total_number_of_files

# ******************************************************************************************************************** #
# Start the program
print("Starting")
storage_drives = psutil.disk_partitions()
for k in range(storage_drives.__len__()):
    if platform.system() == 'Windows':
        print(str(k) + ": " + str(storage_drives[k]))
    else:
        print(str(k) + ": " + str(storage_drives[k].mountpoint) + "\n")

internal = int(input("Choose internal drive from list above and enter number: "))
storage_drives[0], storage_drives[internal] = storage_drives[internal], storage_drives[0]
external = int(input("Choose external drive from list above and enter number: "))
storage_drives[1], storage_drives[external] = storage_drives[external], storage_drives[1]

while user_input != "":
    user_input = input("Enter one SD card number not already entered from list above or press ENTER to continue: ")
    try:
        sd_card_list.append(storage_drives[int(user_input)].mountpoint)
    except ValueError:
        continue

# Change the drive_list based on the exif data serial number
# Read exif data to determine which camera is used
print("Arranging data.")

for n in range(sd_card_list.__len__()):
    for m in range(5):
        if os.path.isdir(os.path.join(sd_card_list[n], "DCIM", "10" + str(m) + "CANON")):
            path_list.append(os.path.join(sd_card_list[n], "DCIM", "10" + str(m) + "CANON"))
print(path_list)

for j in range(sd_card_list.__len__()):
    first_file = os.listdir(os.path.join(sd_card_list[j], 'DCIM', '100CANON'))[0]  # Put in threads area
    file = open(os.path.join(sd_card_list[j], 'DCIM', '100CANON', first_file), 'rb')
    tags = exifread.process_file(file)

    if 'EXIF BodySerialNumber' in tags.keys():
        camera_serial_number[j] = tags['EXIF BodySerialNumber']

if sd_card_list.__len__() == 3:
    # Change the drive list here
    for j in range(sd_card_list.__len__()):
        if str(camera_serial_number[j]) == "032024003117":
            camera_serial_number[0], camera_serial_number[j] = camera_serial_number[j], camera_serial_number[0]
            sd_card_list[0], sd_card_list[j] = sd_card_list[j], sd_card_list[0]
        elif str(camera_serial_number[j]) == "023052000180":
            camera_serial_number[1], camera_serial_number[j] = camera_serial_number[j], camera_serial_number[1]
            sd_card_list[1], sd_card_list[j] = sd_card_list[j], sd_card_list[1]
        elif str(camera_serial_number[j]) == "413051000325":
            camera_serial_number[2], camera_serial_number[j] = camera_serial_number[j], camera_serial_number[2]
            sd_card_list[2], sd_card_list[j] = sd_card_list[j], sd_card_list[2]
print(camera_serial_number)

for path_number in range(path_list.__len__()):
    path = os.path.join(path_list[path_number])
    temp_num_files = len([f for f in os.listdir(path)
                          if os.path.isfile(os.path.join(path, f))])
    num_files += temp_num_files

Sortie = "Sortie0"
nums = 0
if os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), 'Sortie0')):
    while os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie)):
        nums += 1
        Sortie = "Sortie" + str(nums)
print(Sortie)

for j in range(sd_card_list.__len__()):  # starts two threads per drive_list
    print("Copying " + sd_card_list[j] + " to:")
    threads0 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, j,))  # Internal drive
    threads0.start()
    threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, j,))  # External drive
    threads1.start()

print("File copy started.")
time.sleep(2)

# Progressbar time is calculated on external time
bar = progressbar.ProgressBar(maxval=num_files)
try:
    for copied in bar(range(num_files)):
        copied = 0
        for g in range(ceil(path_list.__len__()/sd_card_list.__len__())):
            if os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera0', path_common[g])):
                copied += count_number_of_files(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera0', path_common[g]))
            if os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera1', path_common[g])):
                copied += count_number_of_files(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera1', path_common[g]))
            if os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera2', path_common[g])):
                copied += count_number_of_files(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera2', path_common[g]))
        bar.update(copied)
        time.sleep(2)
except ValueError:
    pass

# Rename folder to make more sense for the user
while threads0.isAlive() and threads1.isAlive():
    pass
for drive_num in range(2):
    if os.path.isdir(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera0')):
        os.rename(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera0'),
                  os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera Left'))
    if os.path.isdir(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera1')):
        os.rename(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera1'),
                  os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera Centre'))
    if os.path.isdir(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera2')):
        os.rename(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera2'),
                  os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera Right'))

print("\n\nFinished")
