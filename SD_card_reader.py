"""Script used to copy all the data from the SD cards to an internal drive and external drive"""
import psutil
import shutil
import datetime
import progressbar
import threading
import os.path
import time
import exifread
import platform
from math import ceil
import logging

sd_card_list = []
Sortie = "Sortie0"


# Copy directory from source to destination
def copy_directory(source, destination):
    try:
        shutil.copytree(source, destination)
    # Directories are the same
    except shutil.Error as e:
        print('Directory not copied. Error: %s' % e)
    # Any error saying that the directory doesn't exist
    except OSError as e:
        print('Directory not copied. Error: %s' % e)


# Thread used to copy directories at the same time
def copy_thread(drive, camera_num):
    # print(drive)
    copy_directory(os.path.join(sd_card_list[camera_num], 'DCIM'),
                   os.path.join(drive, str(datetime.date.today()), Sortie, 'images', 'Camera' + str(camera_num)))


# Count the number of files in a folder at a certain moment
def count_number_of_files(path):
    total_number_of_files = len([f for f in os.listdir(path)
                                 if os.path.isfile(os.path.join(path, f))])
    return total_number_of_files

# ******************************************************************************************************************** #


def main():

    num_files = 0
    camera_serial_number = 3 * [""]
    temp_serial_number = 3 * [""]
    user_input = " "
    path_list = []
    path_common = ['100CANON', '101CANON', '102CANON', '103CANON', '104CANON']
    # Start the program and show partitions to the user
    print("Starting")
    logging.basicConfig(filename='sd_copy.log', level=logging.INFO)
    logging.info("Copying program started at: " + str(datetime.datetime.now()))
    storage_drives = psutil.disk_partitions()
    for index in range(len(storage_drives)):
        if platform.system() == 'Windows':
            print(str(index) + ": " + str(storage_drives[index]))
        else:
            print(str(index) + ": " + str(storage_drives[index].mountpoint) + "\n")

    # Get input from the user for the internal, external and SD cards
    internal = int(input("Choose internal drive from list above and enter number: "))
    external = int(input("Choose external drive from list above and enter number: "))
    # storage_drives[0], storage_drives[internal] = storage_drives[internal], storage_drives[0]
    # storage_drives[1], storage_drives[external] = storage_drives[external], storage_drives[1]
    storage_drives[1], storage_drives[external], storage_drives[0], storage_drives[internal] = \
        storage_drives[external], storage_drives[1], storage_drives[internal], storage_drives[0]

    while user_input != "":
        user_input = input("Enter one SD card number not already entered from list above or press ENTER to continue: ")
        try:
            sd_card_list.append(storage_drives[int(user_input)].mountpoint)
        except ValueError:
            continue
    for cards in range(len(sd_card_list)):
        print("Copying " + sd_card_list[cards] + " to " + str(storage_drives[0].mountpoint) + " and "
              + str(storage_drives[1].mountpoint))

    user_input = str(input("Proceed (y/n): "))
    # Get final confirmation from user
    if user_input == "y" or user_input == "Y":
        for cards in range(len(sd_card_list)):
            logging.info("Copying " + sd_card_list[cards] + " to " + str(storage_drives[0].mountpoint) + " and "
                         + str(storage_drives[1].mountpoint))
    else:
        return -1

    # Change the drive_list based on the exif data serial number
    # Read exif data to determine which camera is used
    print("Arranging data.")

    for index_outer in range(len(sd_card_list)):
        for index_inner in range(5):
            if os.path.isdir(os.path.join(sd_card_list[index_outer], "DCIM", "10" + str(index_inner) + "CANON")):
                path_list.append(os.path.join(sd_card_list[index_outer], "DCIM", "10" + str(index_inner) + "CANON"))
    # print(path_list)

    for index in range(len(sd_card_list)):
        first_file = os.listdir(os.path.join(sd_card_list[index], 'DCIM', '100CANON'))[0]  # Put in threads area
        # file = open(os.path.join(sd_card_list[index], 'DCIM', '100CANON', first_file), 'rb')
        with open(os.path.join(sd_card_list[index], 'DCIM', '100CANON', first_file), 'rb') as file:
            tags = exifread.process_file(file, stop_tag="EXIF BodySerialNumber" )

            if 'EXIF BodySerialNumber' in tags.keys():
                if len(sd_card_list) == 3:
                    temp_serial_number[index] = tags['EXIF BodySerialNumber']
                else:
                    camera_serial_number[index] = tags['EXIF BodySerialNumber']

    if len(sd_card_list) == 3:
        # Change the drive list here
        for index in range(len(sd_card_list)):
            if str(camera_serial_number[index]) == "032024003117":
                temp_serial_number[0], camera_serial_number[index] = camera_serial_number[index], temp_serial_number[0]
                sd_card_list[0], sd_card_list[index] = sd_card_list[index], sd_card_list[0]
            elif str(camera_serial_number[index]) == "023052000180":
                temp_serial_number[1], camera_serial_number[index] = camera_serial_number[index], temp_serial_number[1]
                sd_card_list[1], sd_card_list[index] = sd_card_list[index], sd_card_list[1]
            elif str(camera_serial_number[index]) == "413051000325":
                temp_serial_number[2], camera_serial_number[index] = camera_serial_number[index], temp_serial_number[2]
                sd_card_list[2], sd_card_list[index] = sd_card_list[index], sd_card_list[2]
    print(camera_serial_number)

    # Count the total amount of files to be transferred
    for path_number in range(len(path_list)):
        path = os.path.join(path_list[path_number])
        temp_num_files = len([f for f in os.listdir(path)
                              if os.path.isfile(os.path.join(path, f))])
        num_files += temp_num_files
    logging.info("Copying " + str(num_files) + " to each drive.")

    # Determine the Sortie of the day
    global Sortie
    nums = 0
    if os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), 'Sortie0')) or \
            os.path.isdir(os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), 'Sortie0')):
        while os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie)) or \
         os.path.isdir(os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie)):
            nums += 1
            Sortie = "Sortie" + str(nums)
    print("sortie: " + Sortie)

    # Start the multi-threads to copy the data
    #for j in range(sd_card_list.__len__()):  # starts two threads per drive_list
    # print("Copying " + sd_card_list[j] + " to:")
    # threads0 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, j,))
    # threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, j,))
    threads0 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 0,))  # Internal drive
    threads0.start()
    #print("SD: " + str(len(sd_card_list)))
    if len(sd_card_list) == 2:
        threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 1,))  # External drive
        threads2 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 1,))
        threads3 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 0,))
        threads1.start()
    if len(sd_card_list) == 3:
        threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 1,))  # External drive
        threads2 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 2,))
        threads3 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 0,))
        threads4 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 1,))
        threads5 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 2,))
        threads1.start()

    print("File copy started.")
    # print(threading.active_count())
    time.sleep(2)
    token = 4*[False]

    # Show the progress of the copy. Progressbar time is calculated on external drive copy time
    bar = progressbar.ProgressBar(maxval=num_files)
    try:
        for copied in bar(range(num_files)):
            copied = 0
            for index in range(ceil(len(path_list)/len(sd_card_list))):
                if os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera0', path_common[index])):
                    copied += count_number_of_files(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera0', path_common[index]))
                if os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera1', path_common[index])):
                    copied += count_number_of_files(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera1', path_common[index]))
                if os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera2', path_common[index])):
                    copied += count_number_of_files(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera2', path_common[index]))

    # Start new threads when old threads has stopped
            if len(sd_card_list) > 1:
                if not threads0.isAlive() and not threads2.isAlive() and not token[0]:
                    threads2.start()
                    token[0] = True
                if not threads1.isAlive() and not threads3.isAlive() and not token[1]:
                    threads3.start()
                    token[1] = True
            if len(sd_card_list) > 2:
                if not threads0.isAlive() and not threads2.isAlive() and not threads4.isAlive() and not token[2]:
                    threads4.start()
                    token[2] = True
                if not threads1.isAlive() and not threads3.isAlive() and not threads5.isAlive() and not token[3]:
                    threads5.start()
                    token[3] = True
            elif len(sd_card_list) == 1:
                if not token[0]:
                    threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 0,))  # Internal drive
                    threads1.start()
                    token[0] = True

            bar.update(copied)
            logging.info("Copied: " + str(copied) + " images at " + str(datetime.datetime.now().strftime("%H:%M:%S")))
            time.sleep(2)
    except ValueError:
        pass

    # Rename folder to make more sense for the user
    while threads0.isAlive() or threads1.isAlive():
        pass
    if len(sd_card_list) > 1:
        while threads2.isAlive() or threads3.isAlive():
            pass
    if len(sd_card_list) > 2:
        while threads4.isAlive() or threads5.isAlive():
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

    logging.info("Copying program ended at: " + str(datetime.datetime.now()))
    print("\n\nFinished Copying")

# Start main program
if __name__ == '__main__':
    main()
