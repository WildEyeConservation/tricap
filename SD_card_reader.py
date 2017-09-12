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

# Variables accessible throughout the whole program
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
def copy_thread(drive, camera_num, lock):
    # print(drive)

    lock.acquire()
    try:
        copy_directory(os.path.join(sd_card_list[camera_num], 'DCIM'),
                       os.path.join(drive, str(datetime.date.today()), Sortie, 'images', 'Camera' + str(camera_num)))
    finally:
        lock.release()


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

# Locks are added to ensure only the necessary processes are running to increase the efficiency as much as possible
# Only two copy threads are running at a time between the drives and the SD cards
    lock0 = threading.Lock()
    lock1 = threading.Lock()

    threads0 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 0, lock0,))  # Internal drive
    threads0.start()
    if len(sd_card_list) == 1:
        threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 0, lock1,))  # External drive
        threads1.start()
    #print("SD: " + str(len(sd_card_list)))
    if len(sd_card_list) == 2:
        threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 1, lock1,))  # External drive
        threads2 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 1, lock0,))
        threads3 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 0, lock1,))
        threads1.start()
        threads2.start()
        threads3.start()
    if len(sd_card_list) == 3:
        threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 1, lock1,))  # External drive
        threads2 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 2, lock0,))
        threads3 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 0, lock1,))
        threads4 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 1, lock0,))
        threads5 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 2, lock1,))
        threads1.start()
        threads2.start()
        threads3.start()
        threads4.start()
        threads5.start()

    print("File copy started.")
    print("Active: " + str(threading.active_count()))
    time.sleep(2)

    # Show the progress of the copy. Progressbar time is calculated on external drive copy time
    bar = progressbar.ProgressBar(maxval=2*num_files)
    try:
        for copied in bar(range(2*num_files)):
            copied = 0
            for index in range(ceil(len(path_list)/len(sd_card_list))):
                if os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera0', path_common[index])):
                    copied += count_number_of_files(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera0', path_common[index]))
                if os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera1', path_common[index])):
                    copied += count_number_of_files(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera1', path_common[index]))
                if os.path.isdir(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera2', path_common[index])):
                    copied += count_number_of_files(os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera2', path_common[index]))

            for index in range(ceil(len(path_list)/len(sd_card_list))):
                if os.path.isdir(os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera0', path_common[index])):
                    copied += count_number_of_files(os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera0', path_common[index]))
                if os.path.isdir(os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera1', path_common[index])):
                    copied += count_number_of_files(os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera1', path_common[index]))
                if os.path.isdir(os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera2', path_common[index])):
                    copied += count_number_of_files(os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera2', path_common[index]))

            bar.update(copied)
            logging.info("Copied: " + str(copied) + " images at " + str(datetime.datetime.now().strftime("%H:%M:%S")))
            time.sleep(2)
    except ValueError:
        pass

    # Rename folder to make more sense for the user
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
    print("\nFinished Copying")

# Start main program
if __name__ == '__main__':
    main()
