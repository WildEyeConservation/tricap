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
#from checksumdir import dirhash  # checksumdir 1.1.4
import filecmp
import glob
import hashlib

# Variables accessible throughout the whole program
sd_card_list = []
Sortie = "Sortie0"
day = datetime.date.today()  # Global created for re-use


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
    global day

    lock.acquire()
    try:
        copy_directory(os.path.join(sd_card_list[camera_num], 'DCIM'),
                       os.path.join(drive, day, Sortie, 'images', 'Camera' + str(camera_num)))
    finally:
        lock.release()

# Count the number of files in a folder at a certain moment
def count_number_of_files(path):
    total_number_of_files = len([f for f in os.listdir(path)
                                 if os.path.isfile(os.path.join(path, f))])
    return total_number_of_files


# ******************************************************************************************************************** #


def main():
    # Main variables used
    num_files = 0
    camera_serial_number = 3 * [""]
    temp_serial_number = 3 * [""]
    user_input = " "
    path_list = []
    path_common = ['100CANON', '101CANON', '102CANON', '103CANON', '104CANON']
    global day
    sd_hash = []
    sha1 = hashlib.sha256()
    sha2 = hashlib.sha256()
    sha3 = hashlib.sha256()
    list1 = []
    list2 = []
    list3 = []
    hash_flag = True

    # Start the program and show partitions to the user
    print("Starting")
    log_name = "logs/sd_copy_" + str(datetime.date.today()) + ".log"  # datetime.date. today()
    logging.basicConfig(filename=log_name, level=logging.INFO)
    logging.info("Copying program started at: " + str(datetime.datetime.now()))
    storage_drives = psutil.disk_partitions()
    for index in range(len(storage_drives)):
        if platform.system() == 'Windows':
            print(str(index) + ": " + str(storage_drives[index]))
        else:
            print(str(index) + ": " + str(storage_drives[index].mountpoint) + "\n")

    # Get input from the user for the internal, external and SD cards
    drive_count = int(input("Are you copying to 1 or 2 drives?:"))
    if drive_count == 1:
        internal = int(input("Choose a drive to copy to from list above and enter number: "))
        storage_drives[0], storage_drives[internal] = storage_drives[internal], storage_drives[0]
    elif drive_count == 2:
        internal = int(input("Choose internal drive to copy to from list above and enter number: "))
        external = int(input("Choose external drive to copy to from list above and enter number: "))
        storage_drives[0], storage_drives[internal] = storage_drives[internal], storage_drives[0]
        storage_drives[1], storage_drives[external] = storage_drives[external], storage_drives[1]
    else:
        print("Incorrect option. Please restart program.")
        logging.info("Incorrect option. Program terminated")
        while True:  # Added for safe use when correct option is not chosen
            pass

    while user_input != "":
        user_input = input("Enter one SD card number not already entered from list above or press ENTER to continue: ")
        try:
            sd_card_list.append(storage_drives[int(user_input)].mountpoint)
        except ValueError:
            continue
    for cards in range(len(sd_card_list)):
        if drive_count == 2:
            print("Copying " + sd_card_list[cards] + " to " + str(storage_drives[0].mountpoint) + " and "
                  + str(storage_drives[1].mountpoint))
        elif drive_count == 1:
            print("Copying " + sd_card_list[cards] + " to " + str(storage_drives[0].mountpoint))
    if len(sd_card_list) == 0:
        print("No SD cards specified")
        return -1
    user_input = str(input("Proceed? (y/n): "))
    # Get final confirmation from user
    if user_input == "y" or user_input == "Y":
        for cards in range(len(sd_card_list)):
            if drive_count == 2:
                logging.info("Copying " + sd_card_list[cards] + " to " + str(storage_drives[0].mountpoint) + " and "
                             + str(storage_drives[1].mountpoint))
            elif drive_count == 1:
                logging.info("Copying " + sd_card_list[cards] + " to " + str(storage_drives[0].mountpoint))
    else:
        print("Please restart program.")
        logging.info("Program terminated, because of incorrect drives")
        return -1

    # Change the drive_list based on the exif data serial number
    # Read exif data to determine which camera is used
    print("Preparing data to copy.")
    time_start = datetime.datetime.now()

    for index_outer in range(len(sd_card_list)):
        for index_inner in range(5):
            if os.path.isdir(os.path.join(sd_card_list[index_outer], "DCIM", "10" + str(index_inner) + "CANON")):
                path_list.append(os.path.join(sd_card_list[index_outer], "DCIM", "10" + str(index_inner) + "CANON"))
    # print(path_list)

    for index in range(len(sd_card_list)):
        first_file = os.listdir(os.path.join(sd_card_list[index], 'DCIM', '100CANON'))[0]  # Put in threads area
        with open(os.path.join(sd_card_list[index], 'DCIM', '100CANON', first_file), 'rb') as file:
            tags = exifread.process_file(file, stop_tag="EXIF BodySerialNumber")

            if 'EXIF BodySerialNumber' in tags.keys():
                if len(sd_card_list) == 3:
                    camera_serial_number[index] = tags['EXIF BodySerialNumber']
                else:
                    camera_serial_number[index] = tags['EXIF BodySerialNumber']

            if 'GPS GPSDate' in tags.keys():
                day = str(tags['GPS GPSDate'])
                day = day.replace(':', '-')

    # Check last file date
    dir_index = 0
    while os.path.isdir(os.path.join(sd_card_list[0], 'DCIM', path_common[dir_index])):
        dir_index += 1
    list_file = glob.glob(os.path.join(sd_card_list[0], 'DCIM', '100CANON') + "/*.CR2")
    latest_file = max(list_file, key=os.path.getctime)
    with open(latest_file, 'rb') as file:
        tags = exifread.process_file(file, stop_tag="EXIF BodySerialNumber")
        if 'GPS GPSDate' in tags.keys():
            day2 = str(tags['GPS GPSDate'])
            day2 = day2.replace(':', '-')

    if day != day2:
        print("Please choose a date for folder naming: 1)", day, ' or 2)', day2, 'or 3) own folder name')
        option_input = int(input("Choose option 1, 2 or 3: "))
        if option_input == 2:
            day = day2
        elif option_input == 3:
            day = str(input("Please type in folder name: "))

    if len(sd_card_list) == 3:
        # Change the drive list here
        for index in range(len(sd_card_list)):
            if str(camera_serial_number[index]) == "032024003117":
                camera_serial_number[0], camera_serial_number[index] = camera_serial_number[index], camera_serial_number[0]
                sd_card_list[0], sd_card_list[index] = sd_card_list[index], sd_card_list[0]
            elif str(camera_serial_number[index]) == "023052000180":
                camera_serial_number[1], camera_serial_number[index] = camera_serial_number[index], camera_serial_number[1]
                sd_card_list[1], sd_card_list[index] = sd_card_list[index], sd_card_list[1]
            elif str(camera_serial_number[index]) == "413051000325":
                camera_serial_number[2], camera_serial_number[index] = camera_serial_number[index], camera_serial_number[2]
                sd_card_list[2], sd_card_list[index] = sd_card_list[index], sd_card_list[2]
    # print(camera_serial_number)

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
    if drive_count == 1:
        if os.path.isdir(os.path.join(storage_drives[0].mountpoint, day, 'Sortie0')):
            while os.path.isdir(os.path.join(storage_drives[0].mountpoint, day, Sortie)):
                nums += 1
                Sortie = "Sortie" + str(nums)
    else:
        if os.path.isdir(os.path.join(storage_drives[1].mountpoint, day, 'Sortie0')) or \
                os.path.isdir(os.path.join(storage_drives[0].mountpoint, day, 'Sortie0')):
            while os.path.isdir(os.path.join(storage_drives[1].mountpoint, day, Sortie)) or \
             os.path.isdir(os.path.join(storage_drives[0].mountpoint, day, Sortie)):
                nums += 1
                Sortie = "Sortie" + str(nums)
    print("Sortie: " + Sortie)

# Locks are added to ensure only the necessary processes are running to increase the efficiency as much as possible.
# Only two copy threads at most are running at a time between the drives and the SD cards
    lock0 = threading.Lock()
    lock1 = threading.Lock()

    threads0 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 0, lock0,))  # Internal drive
    threads0.start()
    if len(sd_card_list) == 1:
        if drive_count == 2:
            threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 0, lock1,))  # External drive
            threads1.start()
    if len(sd_card_list) == 2:
        threads2 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 1, lock0,))
        threads2.start()
        if drive_count == 2:
            threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 1, lock1,))  # External drive
            threads3 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 0, lock1,))
            threads1.start()
            threads3.start()
    if len(sd_card_list) == 3:
        threads2 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 2, lock0,))
        threads4 = threading.Thread(target=copy_thread, args=(storage_drives[0].mountpoint, 1, lock0,))
        threads2.start()
        threads4.start()
        if drive_count == 2:
            threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 1, lock1,))  # External drive
            threads3 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 0, lock1,))
            threads5 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 2, lock1,))
            threads1.start()
            threads3.start()
            threads5.start()

    print("File copy started.\n")
    # print("Active: " + str(threading.active_count()))
    time.sleep(2)

    # Show the progress of the copy. Progressbar time is calculated on external drive copy time
    bar = progressbar.ProgressBar(maxval=drive_count*num_files)
    try:
        for copied in bar(range(drive_count*num_files)):
            copied = 0

            for index in range(ceil(len(path_list)/len(sd_card_list))):
                if os.path.isdir(
                        os.path.join(storage_drives[0].mountpoint, day, Sortie, 'images',
                                     'Camera0', path_common[index])):
                    copied += count_number_of_files(
                        os.path.join(storage_drives[0].mountpoint, day, Sortie, 'images',
                                     'Camera0', path_common[index]))
                if os.path.isdir(
                        os.path.join(storage_drives[0].mountpoint, day, Sortie, 'images',
                                     'Camera1', path_common[index])):
                    copied += count_number_of_files(
                        os.path.join(storage_drives[0].mountpoint, day, Sortie, 'images',
                                     'Camera1', path_common[index]))
                if os.path.isdir(
                        os.path.join(storage_drives[0].mountpoint, day, Sortie, 'images',
                                     'Camera2', path_common[index])):
                    copied += count_number_of_files(
                        os.path.join(storage_drives[0].mountpoint, day, Sortie, 'images',
                                     'Camera2', path_common[index]))

            if drive_count == 2:
                for index in range(ceil(len(path_list) / len(sd_card_list))):
                    if os.path.isdir(
                            os.path.join(storage_drives[1].mountpoint, day, Sortie, 'images',
                                         'Camera0', path_common[index])):
                        copied += count_number_of_files(
                            os.path.join(storage_drives[1].mountpoint, day, Sortie, 'images',
                                         'Camera0', path_common[index]))
                    if os.path.isdir(
                            os.path.join(storage_drives[1].mountpoint, day, Sortie, 'images',
                                         'Camera1', path_common[index])):
                        copied += count_number_of_files(
                            os.path.join(storage_drives[1].mountpoint, day, Sortie, 'images',
                                         'Camera1', path_common[index]))
                    if os.path.isdir(
                            os.path.join(storage_drives[1].mountpoint, day, Sortie, 'images',
                                         'Camera2', path_common[index])):
                        copied += count_number_of_files(
                            os.path.join(storage_drives[1].mountpoint, day, Sortie, 'images',
                                         'Camera2', path_common[index]))

            bar.update(copied)
            logging.info("Copied: " + str(copied) + " images at " + str(datetime.datetime.now().strftime("%H:%M:%S")))
            time.sleep(1)
    except ValueError:
        pass

    logging.info("Copying program ended at: " + str(datetime.datetime.now()))
    logging.info("Total copy time: " + str(datetime.datetime.now()-time_start))

    # Do a hash function of copied folders to verify if all the content is copied.
    print("\n\nComparing folders for final validation.")

    for index in range(len(sd_card_list)):
        sd_hash.extend(glob.glob(str(sd_card_list[index]) + '/DCIM/*CANON/*'))
    for index in range(len(sd_hash)):  
        if platform.system() == 'Windows':
            temp = sd_hash[index].split('\\')
        else:
            temp = sd_hash[index].split('/')
        list1.append(temp[len(temp)-1])
        sha1.update(list1[index].encode())
    print("hash SD cards: " + str(sha1.hexdigest()))

    if drive_count > 0:
        hd_hash1 = glob.glob(storage_drives[0].mountpoint + "/" + day + "/" +
                             str(Sortie) + "/images/Camera*/*CANON/*")
        for index in range(len(hd_hash1)):
            if platform.system() == 'Windows':
                temp = hd_hash1[index].split('\\')
            else:
                temp = hd_hash1[index].split('/')
            list2.append(temp[len(temp) - 1])
            sha2.update(list2[index].encode())
        print("hash HD internal drive: " + str(sha2.hexdigest()))
        if sha1.hexdigest() != sha2.hexdigest():
            hash_flag = False
    if drive_count > 1:
        hd_hash2 = glob.glob(storage_drives[1].mountpoint + "/" + day + "/" +
                             str(Sortie) + "/images/Camera*/*CANON/*")
        for index in range(len(hd_hash2)):
            if platform.system() == 'Windows':
                temp = hd_hash2[index].split('\\')
            else:
                temp = hd_hash2[index].split('/')
            list3.append(temp[len(temp) - 1])
            sha3.update(list3[index].encode())
        print("hash HD external drive: " + str(sha3.hexdigest()))
        if sha1.hexdigest() != sha3.hexdigest():
            hash_flag = False

    if hash_flag is True:
        print("\nCopying verified and all the images are backed up.")
        logging.info("Copying verified.")
    else:
        print("\nCopying verification failed!")
        logging.info("Copying verification failed.")
    # print(list1)
    # print(list2)
    # print(list3)

# Rename folder to make more sense for the user

    if len(sd_card_list) == 3:
        for drive_num in range(drive_count):
            if os.path.isdir(os.path.join(storage_drives[drive_num].mountpoint, day, Sortie,
                                          'images', 'Camera0')):
                os.rename(os.path.join(storage_drives[drive_num].mountpoint, day, Sortie,
                                       'images', 'Camera0'),
                          os.path.join(storage_drives[drive_num].mountpoint, day, Sortie,
                                       'images', 'Camera Left'))
            if os.path.isdir(os.path.join(storage_drives[drive_num].mountpoint, day, Sortie,
                                          'images', 'Camera1')):
                os.rename(os.path.join(storage_drives[drive_num].mountpoint, day, Sortie,
                                       'images', 'Camera1'),
                          os.path.join(storage_drives[drive_num].mountpoint, day, Sortie,
                                       'images', 'Camera Centre'))
            if os.path.isdir(os.path.join(storage_drives[drive_num].mountpoint, day, Sortie,
                                          'images', 'Camera2')):
                os.rename(os.path.join(storage_drives[drive_num].mountpoint, day, Sortie,
                                       'images', 'Camera2'),
                          os.path.join(storage_drives[drive_num].mountpoint, day, Sortie,
                                       'images', 'Camera Right'))

    print("Finished Copying.")

# ******************************************************************************************************************** #
# Start main program
if __name__ == '__main__':
    main()
