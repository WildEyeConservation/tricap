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
from checksumdir import dirhash  # checksumdir 1.1.4
import filecmp
import glob
import hashlib

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


def print_diff_files(dcmp):
    for name in dcmp.diff_files:
        print("diff_file %s found in %s and %s" % (name, dcmp.left,
                                                   dcmp.right))
    for sub_dcmp in dcmp.subdirs.values():
        print_diff_files(sub_dcmp)


def are_dir_trees_equal(dir1, dir2):
    """
    Compare two directories recursively. Files in each directory are
    assumed to be equal if their names and contents are equal.

    @param dir1: First directory path
    @param dir2: Second directory path

    @return: True if the directory trees are the same and 
        there were no errors while accessing the directories or files, 
        False otherwise.
   """

    dirs_cmp = filecmp.dircmp(dir1, dir2)
    if len(dirs_cmp.left_only) > 0 or len(dirs_cmp.right_only) > 0 or \
                    len(dirs_cmp.funny_files) > 0:
        return False
    (_, mismatch, errors) = filecmp.cmpfiles(
        dir1, dir2, dirs_cmp.common_files, shallow=False)
    if len(mismatch) > 0 or len(errors) > 0:
        return False
    for common_dir in dirs_cmp.common_dirs:
        new_dir1 = os.path.join(dir1, common_dir)
        new_dir2 = os.path.join(dir2, common_dir)
        if not are_dir_trees_equal(new_dir1, new_dir2):
            return False
    return True

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
    drive_count = int(input("Are you copying to 1 or 2 drives?:"))
    if drive_count == 1:
        internal = int(input("Choose drive from list above and enter number: "))
        storage_drives[0], storage_drives[internal] = storage_drives[internal], storage_drives[0]
    elif drive_count == 2:
        internal = int(input("Choose internal drive from list above and enter number: "))
        external = int(input("Choose external drive from list above and enter number: "))
        storage_drives[0], storage_drives[internal] = storage_drives[internal], storage_drives[0]
        storage_drives[1], storage_drives[external] = storage_drives[external], storage_drives[1]
    else:
        print("Incorrect option. Please restart program.")
    # storage_drives[1], storage_drives[external], storage_drives[0], storage_drives[internal] = \
    #     storage_drives[external], storage_drives[1], storage_drives[internal], storage_drives[0]

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

    user_input = str(input("Proceed (y/n): "))
    # Get final confirmation from user
    if user_input == "y" or user_input == "Y":
        for cards in range(len(sd_card_list)):
            if drive_count == 2:
                logging.info("Copying " + sd_card_list[cards] + " to " + str(storage_drives[0].mountpoint) + " and "
                             + str(storage_drives[1].mountpoint))
            elif drive_count == 1:
                logging.info("Copying " + sd_card_list[cards] + " to " + str(storage_drives[0].mountpoint))
    else:
        return -1

    # Change the drive_list based on the exif data serial number
    # Read exif data to determine which camera is used
    print("Arranging data.")
    time_start = datetime.datetime.now()

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
                    camera_serial_number[index] = tags['EXIF BodySerialNumber']
                else:
                    camera_serial_number[index] = tags['EXIF BodySerialNumber']

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
    if drive_count == 1:
        if os.path.isdir(os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), 'Sortie0')):
            while os.path.isdir(os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie)):
                nums += 1
                Sortie = "Sortie" + str(nums)
    else:
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
        if drive_count == 2:
            threads1 = threading.Thread(target=copy_thread, args=(storage_drives[1].mountpoint, 0, lock1,))  # External drive
            threads1.start()
    #print("SD: " + str(len(sd_card_list)))
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

    print("File copy started.")
    print("Active: " + str(threading.active_count()))
    time.sleep(2)

    # Show the progress of the copy. Progressbar time is calculated on external drive copy time
    bar = progressbar.ProgressBar(maxval=drive_count*num_files)
    try:
        for copied in bar(range(drive_count*num_files)):
            copied = 0

            for index in range(ceil(len(path_list)/len(sd_card_list))):
                if os.path.isdir(
                        os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                     'Camera0', path_common[index])):
                    copied += count_number_of_files(
                        os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                     'Camera0', path_common[index]))
                if os.path.isdir(
                        os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                     'Camera1', path_common[index])):
                    copied += count_number_of_files(
                        os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                     'Camera1', path_common[index]))
                if os.path.isdir(
                        os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                     'Camera2', path_common[index])):
                    copied += count_number_of_files(
                        os.path.join(storage_drives[0].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                     'Camera2', path_common[index]))

            if drive_count == 2:
                for index in range(ceil(len(path_list) / len(sd_card_list))):
                    if os.path.isdir(
                            os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                         'Camera0', path_common[index])):
                        copied += count_number_of_files(
                            os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                         'Camera0', path_common[index]))
                    if os.path.isdir(
                            os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                         'Camera1', path_common[index])):
                        copied += count_number_of_files(
                            os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                         'Camera1', path_common[index]))
                    if os.path.isdir(
                            os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                         'Camera2', path_common[index])):
                        copied += count_number_of_files(
                            os.path.join(storage_drives[1].mountpoint, str(datetime.date.today()), Sortie, 'images',
                                         'Camera2', path_common[index]))

            bar.update(copied)
            logging.info("Copied: " + str(copied) + " images at " + str(datetime.datetime.now().strftime("%H:%M:%S")))
            time.sleep(2)
    except ValueError:
        pass

    logging.info("Copying program ended at: " + str(datetime.datetime.now()))
    logging.info("Total copy time: " + str(datetime.datetime.now()-time_start))

    # Do a hash function of copied folders to verify if all the content is copied.
    print("\n")
    SD_hash = []
    sha1 = hashlib.sha256()
    sha2 = hashlib.sha256()
    sha3 = hashlib.sha256()
    list1 = []
    list2 = []
    list3 = []
    hash = True

    for index in range(len(sd_card_list)):
        SD_hash.extend(glob.glob(str(sd_card_list[index]) + '/DCIM/*CANON/*'))
    for index in range(len(SD_hash)):
        temp = SD_hash[index].split('\\')
        list1.append(temp[len(temp)-1])
        sha1.update(list1[index].encode())
    print("hash SD cards: " + str(sha1.hexdigest()))

    if drive_count > 0:
        HD_hash1 = glob.glob(storage_drives[0].mountpoint + "/" + str(datetime.date.today()) + "/" +
                             str(Sortie) + "/images/Camera*/*CANON/*")
        for index in range(len(HD_hash1)):
            temp = HD_hash1[index].split('\\')
            list2.append(temp[len(temp) - 1])
            sha2.update(list2[index].encode())
        print("hash HD internal drive: " + str(sha2.hexdigest()))
        if sha1.hexdigest() != sha2.hexdigest():
            hash = False
    if drive_count > 1:
        HD_hash2 = glob.glob(storage_drives[1].mountpoint + "/" + str(datetime.date.today()) + "/" +
                             str(Sortie) + "/images/Camera*/*CANON/*")
        for index in range(len(HD_hash2)):
            temp = HD_hash2[index].split('\\')
            list3.append(temp[len(temp) - 1])
            sha3.update(list3[index].encode())
        print("hash HD external drive: " + str(sha3.hexdigest()))
        if sha1.hexdigest() != sha3.hexdigest():
            hash = False

    if hash is True:
        print("\nCopying verified and all content are backed up.")
    else:
        print("\nCopying failed!")
    # print(list1)
    # print(list2)
    # print(list3)

    # print("\nComparing folders for final validation.")
    # for camera_num in range(len(sd_card_list)):
    #     time1 = datetime.datetime.now()
    #     directory1 = os.path.join(sd_card_list[camera_num], 'DCIM')
    #     hash1 = dirhash(directory1, 'md5')
    #     print("hash SD " + str(sd_card_list[camera_num]) + ": " + str(hash1))
    #     for drv in range(drive_count):
    #         directory2 = os.path.join(storage_drives[drv].mountpoint, str(datetime.date.today()), Sortie, 'images', 'Camera' + str(camera_num)) # Sortie
    #         hash2 = dirhash(directory2, 'md5')
    #         print("hash drive " + str(storage_drives[drv].mountpoint) + ": " + str(hash2))
    #     print(str(datetime.datetime.now()-time1))

    # sha256hash1 = dirhash("C:/Users/Pieter.at.Innoventix/Desktop/Innoventix/Tricap docs", 'sha256', excluded_extensions=['pyc'])
    # print(sha256hash1)
    # sha256hash2 = dirhash("C:/Users/Pieter.at.Innoventix/Desktop/Innoventix/Tricap docs1", 'sha256',
    #                      excluded_extensions=['pyc'])
    # print(sha256hash2)

            # Rename folder to make more sense for the user

    if len(sd_card_list) == 3:
        for drive_num in range(drive_count):
            if os.path.isdir(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie,
                                          'images', 'Camera0')):
                os.rename(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie,
                                       'images', 'Camera0'),
                          os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie,
                                       'images', 'Camera Left'))
            if os.path.isdir(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie,
                                          'images', 'Camera1')):
                os.rename(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie,
                                       'images', 'Camera1'),
                          os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie,
                                       'images', 'Camera Centre'))
            if os.path.isdir(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie,
                                          'images', 'Camera2')):
                os.rename(os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie,
                                       'images', 'Camera2'),
                          os.path.join(storage_drives[drive_num].mountpoint, str(datetime.date.today()), Sortie,
                                       'images', 'Camera Right'))

    print("Finished Copying")

# Start main program
if __name__ == '__main__':
    main()
