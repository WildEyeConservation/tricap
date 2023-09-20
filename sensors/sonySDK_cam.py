"""Handler for sony SDK based cameras. Uses this library to handle communication."""

import os
import logging
import threading
from exiftool import ExifToolHelper
import shutil
import rawpy
from PIL import Image
from io import BytesIO
import base64
import signal
import time
from scipy import interpolate
import numpy as np
import csv


from time import sleep, time, strftime
from datetime import datetime

import sys
sys.path.append("/home/pi/tricap")

from config import CAMERA_STATES
sys.path.append(os.path.abspath("/home/pi/SonySDKWrapper"))
from sonySDKWrapper import *

import subprocess, hashlib, json

# noinspection PyUnresolvedReferences
class sonySDKcam():
    """Handler for sony SDK based cameras. Uses this library to handle communication."""

    _logger = logging.getLogger(__name__)
    _lock_with_save = None
    KEYS_TO_SAVE = ('Composite:SubSecDateTimeOriginal','EXIF:ExifImageHeight','EXIF:ExifImageWidth','EXIF:LensSerialNumber','Composite:GPSAltitude','EXIF:GPSDateStamp','Composite:GPSLatitude','Composite:GPSLongitude','EXIF:GPSTimeStamp','EXIF:ISO', 'EXIF:ShutterSpeedValue','MakerNotes:FocusMode','MakerNotes:Quality')
    _sonyCamera = None

    def imageDownloadCompleteCallback(self, filename):
        # print("Received sony camera download callback with filename "+str(filename, encoding="utf-8"))
        self._logger.debug("Sony camera transfer callback called with "+str(filename, encoding="utf-8"))
        with self._lock_with_save:
                self._to_save_queue.append(str(filename, encoding="utf-8"))
                self._downLoadedCount += 1

    def cameraErrorCallback(self, message):
        # print("Received an error callback from sony camera SDK "+str(message, encoding="utf-8"))
        self._logger.error("Received an error callback from sony camera SDK "+str(message, encoding="utf-8"))
        raise Exception("Received an error callback from sony camera SDK "+str(message, encoding="utf-8"))

    def exitGracefully(self, sig, frame):
        self._sonyCamera = None
        sys.exit(sig)

    def __init__(self, memoryFsPath):
        """Constructor"""
        self._exif_info = {}
        self._camera = None
        self._image_count = 0
        self._to_save_queue = []
        self._serial_num = "Default_serial_num"
        self._preview_images_big_jpg = []
        self._num_images_copied = 0
        self._num_images_failed = 0
        self._disableHashAndPreview = True
        self._memoryFsPath = memoryFsPath
        self._preview_images = []
        self._im_aspect_ratio = 0

        try:
            mount_status = subprocess.run(["mount", "tmpfs", "-t",  "tmpfs", memoryFsPath], check=True)
            self._logger.debug(mount_status)
        except:
            raise Exception('Failed to mount ram fs for sony SDK copy, path: ' + memoryFsPath)
            return
        
        # catch SIGINT and SIGTERM to destroy the sony camera object to not break the SDK when you do a systemctl stop
        signal.signal(signal.SIGINT, self.exitGracefully)
        signal.signal(signal.SIGTERM, self.exitGracefully)

        self._sonyCamera = sonyCamera()
        numCameras = self._sonyCamera.getNumCameras()
        if (numCameras > 0):
            self._sonyCamera.connectCamera(1)
            
            # counter = 100
            while (not self._sonyCamera.isConnected()):
                sleep(0.1)
                # counter -= 1
                # if(counter <= 0):
                #     self._sonyCamera = None
                #     raise Exception("Sony Camera connection timeout!")

            self._sonyCamera.loadProperties()
            sleep(2)
            # This sets the file chunk size for transferring images from the camera to the PI ram fileSystem. The max seems to be 20Mb chunks, as configured here. 
            # This allows the shutter events sent from the SDK to not be blocked for too long while images are transferred, preventing erratic shutter timing.
            self._sonyCamera.setTransferBufferSize(20)

            # This instructs the camera to save images to the PC only and not on the SD card.
            self._sonyCamera.setCameraSaveLocation(1)

            # live view is enabled by default on connection and seems to use USB bandwidth, so toggle it to disable
            self._sonyCamera.toggleLiveView()

            print("Setting download callback")
            self._sonyCamera.setOnDownloadCompleteCallback(self.imageDownloadCompleteCallback)
            self._sonyCamera.setOnErrorCallBack(self.cameraErrorCallback)

            if (not self._sonyCamera.setSaveInfo(memoryFsPath, "IMG3_", 1)):
                raise Exception("Failed to set the save location. Make sure that the following path exists and has appropriate permissions: " + memoryFsPath)
            
            self._serial_num = self._sonyCamera.getModel().replace("-","_")

            # Give the camera a moment to settle before starting to capture images. Prevents the first capture from being missed
            sleep(3)
        else:
            self.state = CAMERA_STATES.ERROR_CONFIG
            raise Exception("No Sony SDK cameras were detected")
        self.state = CAMERA_STATES.INITIALISED

    def is_cam_image_fresh(self):
        """Check if the camera image is new."""
        return False

    # @staticmethod
    # def autodetect():
    #     """Run gphoto2 camera autodetection."""
    #     return GPhotoCam._context.camera_autodetect()

    # @property
    # def config(self):
    #     """Return a GPhotoConfig object for the camera."""
    #     return GPhotoConfig(self._gp_camera, self._context)

    # def _fetch_preview_camera_file(self, file_path: str):
    #     camera_file = None
    #     try:
    #         camera_file = self._gp_camera.file_get(file_path.folder,
    #                                                file_path.name,
    #                                                gp.GP_FILE_TYPE_PREVIEW,
    #                                                GPhotoCam._context)
    #     except gp.GPhoto2Error:
    #         self._logger.error('Error retrieving preview, is the capturetarget correctly set?')
    #         raise

    #     return camera_file

    # def get_current_folder(self):
    #     """Get the latest folder from the camera."""
    #     folder = '/'
    #     done_flag = False
    #     while done_flag is False:
    #         cam_folders = self._gp_camera.folder_list_folders(folder, self._context)
    #         if len(cam_folders) == 0:
    #             done_flag = True
    #         else:
    #             target_folder = cam_folders[-1][0]
    #             if cam_folders[-1][0] == 'MISC':
    #                 target_folder = cam_folders[-2][0]
    #             folder += target_folder + '/'
    #             for name, value in cam_folders:
    #                 print(name)

    #     return folder

    # def calibrate_func(self):
    #     print('running the calibration function.')
    #     # get the latest folder and file
    #     # folder = self.get_current_folder()
    #     # print(folder)
    #     # cam_files = self._gp_camera.folder_list_files('/', self._context)
    #     # cam_files = self._gp_camera.folder_list_files(folder, self._context)
    #     # print(cam_files)
    #     # print(len(cam_files))
    #     # fname = cam_files[-1][0]
    #     # print(fname)

    #     # capturing image
    #     MAX_FOCUS_ATTEMPTS = 3
    #     focus_flag = False
    #     focus_attempts = 0
    #     while focus_flag is False and focus_attempts < MAX_FOCUS_ATTEMPTS: 
    #         trigger_attempts = 0
    #         cam_fp = None
    #         done_flag = False
    #         while trigger_attempts < MAX_TRIGGER_ATTEMPTS and done_flag is False:
    #             try:
    #                 cam_fp = self._gp_camera.capture(gp.GP_CAPTURE_IMAGE, GPhotoCam._context)
    #                 done_flag = True
    #             except gp.GPhoto2Error as ex:
    #                 self._logger.warning('Exception when trying to trigger a capture: %s', ex)
    #                 trigger_attempts += 1
    #                 sleep(1)

    #         if done_flag is False:
    #             print("could not successfully capture.")                
    #             self._logger.error('Calibration: could not autofocus.')
    #             return -1

    #         print("successfully captured.")

    #         # get the exif data from that file
    #         buf = bytearray(128*1024)
    #         self._gp_camera.file_read(cam_fp.folder, cam_fp.name, 
    #                                   gp.GP_FILE_TYPE_NORMAL, 0, 
    #                                   buf, GPhotoCam._context)
    #         tfile = tempfile.NamedTemporaryFile('wb', delete=True)
    #         tfile.write(buf)
    #         exif_data = pyexifinfo.get_json(tfile.name)[0]

    #         print(exif_data['MakerNotes:FocusDistanceLower'])
    #         fdl = float(exif_data['MakerNotes:FocusDistanceLower'][:-2])
    #         if fdl != 11.9:
    #             print('not in focus')
    #             focus_attempts += 1
    #         else:
    #             print('focussed')
    #             focus_flag = True

    #     if focus_flag is False:
    #         print("impossible to focus")
            
    #         self._logger.error('Calibration: could not autofocus.')
    #     else:
    #         self._logger.info('Calibration: focus a success.')
    #     # react to it, i.e. use autofocus to correct?


    # def _update_image(self, camera_file):
    #     file_data = camera_file.get_data_and_size()
    #     # Make a copy, so that we can release the file_data object
    #     self.data = memoryview(file_data).tobytes()
    #     self._fresh_capture = True

    # def _run_calibrate_if_needed(self):
    #     if self.calibrate_func is not None:
    #         if self.calibrate_step > 0:
    #             print(self._image_count)
    #             if self._image_count == 1 or self._image_count % self.calibrate_step == 0:
    #                 self.calibrate_func()

    # def _wait_for_image_path(self, before_capture_ts=None):
    #     image_path = None

    #     event = self._gp_camera.wait_for_event(100, GPhotoCam._context)
    #     count = 0

    #     if before_capture_ts is None:
    #         while event[0] != gp.GP_EVENT_FILE_ADDED and count < 1000:
    #             sleep(0.01)
    #             event = self._gp_camera.wait_for_event(100, GPhotoCam._context)
    #             count += 1
    #     else:
    #         while event[0] != gp.GP_EVENT_FILE_ADDED and (datetime.now() - before_capture_ts).total_seconds() < 1.2:
    #             sleep(0.01)
    #             event = self._gp_camera.wait_for_event(100, GPhotoCam._context)

    #     if event[0] == gp.GP_EVENT_FILE_ADDED:
    #         image_path = event[1]

    #     return image_path

    # def capture_and_read_exif(self):
    #     """Capture an image and download it."""
    #     file_path = self._gp_camera.capture(gp.GP_CAPTURE_IMAGE, GPhotoCam._context)

    #     sleep(100e-3)

    #     camera_files = self.list_camera_files()
    #     exif_data = None
    #     if len(camera_files) > 0:
    #         # read last image exif data
    #         folder, name = os.path.split(camera_files[-1])
    #         camera_file = self._gp_camera.file_get(folder,
    #                                             name,
    #                                             gp.GP_FILE_TYPE_NORMAL,
    #                                             GPhotoCam._context)
    #         file_data = camera_file.get_data_and_size()
    #         data_bytes = memoryview(file_data).tobytes()
    #         tfile = tempfile.NamedTemporaryFile('wb', delete=True)            
    #         tfile.write(data_bytes)
    #         exif_data = pyexifinfo.get_json(tfile.name)[0]

    #     return exif_data

    # def cam_trigger(self):
    #     """Trigger using either normal function or the eos remote release."""
    #     if self.calibrate_step > 0:
    #         # full press (bypass focus)
    #         config = self._gp_camera.get_config(GPhotoCam._context)
    #         GPhotoSetting(config.get_child_by_name('eosremoterelease')).set('Press Full')
    #         self._gp_camera.set_config(config, GPhotoCam._context)

    #         # release full press
    #         config = self._gp_camera.get_config(GPhotoCam._context)
    #         GPhotoSetting(config.get_child_by_name('eosremoterelease')).set('Release Full')
    #         self._gp_camera.set_config(config, GPhotoCam._context)
    #     else:
    #         self._gp_camera.trigger_capture(GPhotoCam._context)

    def _trigger_capture(self):
        """Make the camera capture an image but don't wait for it to return.

        Return True if successful, or False if failed.
        """
        if(self._sonyCamera.isConnected() and self._sonyCamera.captureImage()):
            return True
        else:
            self._logger.warning('Trigger failed')
            return False

    def capture(self, continuous=False, barrier: threading.Barrier = None, stop_event=None):
        """Start capturing photos, typically called by a thread."""
        self.state = CAMERA_STATES.INITIALISED
        while True:
            if stop_event and stop_event.is_set():
                self.update_message = 'capture stop event is set'
                self.notify()
                return

            space_available = True

            self.update_message = 'before barrier wait'
            self.notify()

            if barrier:
                barrier.wait()

            self.update_message = 'before capture'
            self.notify()
            before_capture_ts = datetime.now()

            if space_available and self._trigger_capture():  # Checks to see if something went wrong with the cameras
                self._image_count += 1
                self.state = CAMERA_STATES.CAPTURING
            else:
                self._logger.error('Could not successfully trigger a capture.')
                self.state = CAMERA_STATES.ERROR_CAPTURE
                if not self._sonyCamera.isConnected():
                    raise Exception("Camera is not connected!")

            if not continuous:
                return

    # def reset(self, settings: dict):
    #     """Reset the camera."""
    #     self.state = CAMERA_STATES.UNINITIALISED
    #     self._setup_camera(settings)

    def capture_and_copy(self, interval, init_start, session_start_date, serial_number, stop_capture, lock_with_save, index, capture_done, save_done, sync_lock):
        self._lock_with_save = lock_with_save
        # empty event buffer
        self._logger.debug(f'capture_and_copy {init_start}')
        self._session_start_date = session_start_date
        # code=0
        # while code != 1:
        #     code,filepath=self._gp_camera.wait_for_event(1)

        # local variables
        start = init_start
        triggers = 0
        missedCount = 0
        with self._lock_with_save:
            self._downLoadedCount = 0
        self._session_id = session_start_date.strftime("%H_%M_%S")
        self._logger.debug(f"_session_id {self._session_id}")
        stopTriggerInitiated = False
        self._num_images_failed = 0
        self._num_images_copied = 0
        self._image_count = 0
        self._preview_images_big_jpg = []
        self._preview_images = []

        if (not self._sonyCamera.setSaveInfo(self._memoryFsPath, session_start_date.strftime("%d_%m_%Y_%H_%M_%S")+"_", 1)):
            with sync_lock:
                capture_done[index].set()
            raise Exception("Failed to set the save location. Make sure that the following path exists and has appropriate permissions: " + memoryFsPath)

        sleep(1)
        # How long to wait for copies from the camera until it is assumed that the photos did not make it.
        copyWaitTimeout = 20

        # main loop
        while True:
            if stop_capture.is_set() and not stopTriggerInitiated:
                # stop trigger
                stopTriggerInitiated = True
                with sync_lock:
                    capture_done[index].clear()

            # check if trigger is required
            if (time() - start > 0) and (stop_capture and not stop_capture.is_set()):
                # trigger required
                if self._trigger_capture(): 
                    self._image_count += 1
                    self.state = CAMERA_STATES.CAPTURING                    
                    triggers += 1
                    with self._lock_with_save:
                        self._logger.info("Waiting for "+str(triggers*2 - self._downLoadedCount )+" images from the camera save queue is: " + str(len(self._to_save_queue)) + " images long.")
                else:
                    self._logger.warning('Could not successfully trigger a capture.')
                    self.state = CAMERA_STATES.ERROR_CAPTURE
                    if not self._sonyCamera.isConnected():
                        with sync_lock:
                            capture_done[index].set()
                        raise Exception("Camera is not connected!")
                start += interval
                while start - time() < 1.0:
                    self._logger.warning(f"next capture delayed {start - time()}")
                    start += interval
                    missedCount += 1

            # check if thread is done
            if stop_capture.is_set() and stopTriggerInitiated:
                if self._downLoadedCount + self._num_images_failed >= triggers*2 or copyWaitTimeout <=0:
                    # All the triggered images were downloaded by the sony SDK, it downloads a RAW and JPG image for every image taken

                    if copyWaitTimeout <=0:
                        self._num_images_failed = triggers*2-(self._downLoadedCount+self._num_images_failed)
                        self._logger.warning('failed to download '+str(self._num_images_failed)+ ' images from the camera')
                    isCaptureDoneSet = False
                    with sync_lock:
                        isCaptureDoneSet = capture_done[index].is_set()               
                    if not isCaptureDoneSet:
                        # self.save_exif_info(serial_number)
                        # self._exif_info = {}
                        with sync_lock:
                            capture_done[index].set()
                        self._logger.debug('Exit capture thread 2')
                        return
                else:
                    copyWaitTimeout -=1
                    sleep(1)
            


    def save_to_ssd(self, mount_point, computer_files, serial_num, lock_with_copy, lock_with_preview, capture_done, save_done, sync_lock, imu_lock):
        self._logger.debug(f"Save to SSD thread started")

        # tagsToGet = ['Composite:SubSecDateTimeOriginal','EXIF:ExifImageHeight','EXIF:ExifImageWidth','Composite:GPSAltitude','EXIF:GPSDateStamp','Composite:GPSLatitude','Composite:GPSLongitude','EXIF:GPSTimeStamp','EXIF:ISO', 'EXIF:ShutterSpeedValue','MakerNotes:FocusMode','MakerNotes:Quality']
        # et = ExifToolHelper()
        self._dest_dir = self.get_im_target_dir(self._session_start_date, mount_point, serial_num)
        self._mount_point = mount_point
        self._imu_lock = imu_lock

        while True:
            
            fileName = ""
            # print("About to wait on lock")
            self._lock_with_save.acquire()
            # print("Lock aquired")
            if(len(self._to_save_queue) > 0):
                fileName = self._to_save_queue.pop(0)
                self._lock_with_save.release()
                print(str(datetime.now())+ " popping file " + fileName)
            else:
                self._lock_with_save.release()
            # if(fileName != ""):
                # nameParts = fileName.split("/")
                # exifDataJson[nameParts[-1]] = et.get_tags([fileName], tagsToGet)
                # print("Copying "+ fileName + " to "+ destinationDirectory+"/"+nameParts[-1])
                # shutil.move(fileName,destinationDirectory+"/"+nameParts[-1])


            if fileName == '':
                with lock_with_copy:
                    save_done.set()
                allDone = True
                with sync_lock:
                    for t in capture_done:
                        if not t.is_set():
                            allDone = False            
                if allDone:
                    self._logger.debug('save_to_ssd thread is done, generating exif info...')
                    self.save_exif_info(serial_num)
                    self._logger.debug('Exit save thread')
                    return
                # nothing to save
                sleep(100e-3)                    
            else:
                # save required
                with lock_with_copy:
                    save_done.clear()
                # print(str(datetime.now())+ " Getting file name and exif")
                currentFolder, currentFilename = os.path.split(fileName)
                # currentFilename = str(currentFilename,encoding="utf-8")
                # exif_data = et.get_tags([fileName], self.KEYS_TO_SAVE)[0]
                # print("read exif data: "+str(exif_data))
                # timestamp = datetime.strptime(exif_data["Composite:SubSecDateTimeOriginal"], "%Y:%m:%d %H:%M:%S%z")
                # print("Copying to " + dest_dir + "/"+currentFilename)
                dest = os.path.join(self._dest_dir, currentFilename)
                if not os.path.isdir(self._dest_dir):
                    os.makedirs(self._dest_dir)
                if not os.path.isdir(os.path.join(self._dest_dir,"in_progress")):
                    os.makedirs(os.path.join(self._dest_dir,"in_progress"))
                
                # if (not self._disableHashAndPreview):
                #     print(str(datetime.now())+ " read file for md5")
                #     sourceFile = open(fileName,"rb")
                #     sourceImageContent = sourceFile.read()
                #     print(str(datetime.now())+ " done reading, calculating hash")
                #     imageHash =  hashlib.md5(sourceImageContent).hexdigest() # 170ms for MD5 calc
                #     sourceFile.close()
                imageAlreadySaved = False
                print(str(datetime.now())+ " Iterate over destination files")
                if dest in computer_files:
                    # file exists
                    self._logger.debug('File exists {}'.format(dest))
                    if(not self._disableHashAndPreview):
                        try:
                            f = open(dest, "rb")
                            h = hashlib.md5(f.read()).hexdigest()
                            # exif_data = pyexifinfo.get_json(f.name)[0]
                            f.close()
                            if h == imageHash:
                                imageAlreadySaved = True
                                self._logger.debug('File already copied {}'.format(dest))
                                # self.append_exif_info(currentFilename, self._dest_dir, exif_data, imageHash)
                        except:
                            while dest in computer_files:
                                dest = "{0}_{2}.{1}".format(*dest.rsplit(".", 1), "copy")
                            self._logger.debug('Save as _copy {}'.format(dest))
                    else:
                        while dest in computer_files:
                            dest = "{0}_{2}.{1}".format(*dest.rsplit(".", 1), "copy")
                        self._logger.debug('Save as _copy {}'.format(dest))
                
                # self._logger.debug('Save {} {}'.format(dest, imageAlreadySaved))
                try:
                    if not imageAlreadySaved:

                        if(".JPG" in currentFilename):
                            previewCount = 0
                            with lock_with_preview:
                                previewCount = len(self._preview_images_big_jpg)
                            if previewCount < 3:
                                sourceFile = open(fileName,"rb")
                                sourceImageContent = sourceFile.read()
                                sourceFile.close()
                                with lock_with_preview:
                                    self._preview_images_big_jpg.append(sourceImageContent)
                            elif self._num_images_copied % 500 == 0:
                                with lock_with_preview:
                                    self._preview_images_big_jpg.pop(0)
                                    self._preview_images_big_jpg.append(sourceImageContent)

                        print(str(datetime.now())+ " start copy")
                        try:
                            # First copy to the SSD, then move from the in_progress folder to the main folder. This is done
                            # to try to make the copy "atomic" to avoid corrupted files on the SSD due to loss of power or similar.
                            copy_status = subprocess.run(["mv", fileName, os.path.join(self._dest_dir,"in_progress",currentFilename)], check=True)
                            copy_status = subprocess.run(["mv", os.path.join(self._dest_dir,"in_progress",currentFilename), os.path.join(self._dest_dir,currentFilename)], check=True)
                            self._logger.debug(copy_status)
                            self._num_images_copied += 1
                        except:
                            # raise Exception('Failed to copy file')
                            print("Failed to copy file, retrying")
                            self._lock_with_save.acquire()
                            self._to_save_queue.append(fileName)
                            self._lock_with_save.release()
                            continue
                        # shutil.move(fileName,self._dest_dir+"/"+currentFilename)
                        print(str(datetime.now())+ " copied to "+ self._dest_dir+"/"+currentFilename )
                        # if not self._disableHashAndPreview:
                        #     self.append_exif_info(currentFilename, self._dest_dir, exif_data, imageHash)
                        # else:
                        #     self.append_exif_info(currentFilename, self._dest_dir, exif_data, "")
                        # self.save_exif_info(serial_num)
                        # self._exif_info = {}
                        # if not self._disableHashAndPreview:
                        #     print(str(datetime.now())+ " generate preview")
                        
                    print(str(datetime.now())+ " done with copy thread")
                except Exception as e:
                    self._logger.warning("Save exception %s %s -> %s, error: %s" % (currentFolder, currentFilename, dest, str(e)))
                    self._num_images_failed += 1


    def load_preview_images(self, lock_with_save):
        self._logger.debug('Load preview thread started')
        self._generating_preview = True
        previewStart = time()
        previewLen = 0
        self._logger.debug('Wait on lock')
        with lock_with_save:
            previewLen = len(self._preview_images_big_jpg)
        if (previewLen < 1):
            self._generating_preview = False
            return
        self._logger.debug('Got length')
        self._preview_images.clear()
        for i in range(previewLen):
            try:
                self._logger.debug('Loading image')
                with lock_with_save:
                    im = Image.open(BytesIO(bytes(self._preview_images_big_jpg.pop(0))))
                bytes_io = BytesIO()
                self._logger.debug('Saving image')
                im.save(bytes_io, format='JPEG', quality=20)
                self._im_aspect_ratio = im.width/im.height
                if len(bytes_io.getvalue()) < 10000000:
                    # avoid memory crash on app
                    self._preview_images.append(base64.b64encode(bytes_io.getvalue()).decode("utf-8"))
                self._logger.debug(len(bytes_io.getvalue()))
            except Exception as e:
                self._logger.warning(f"Failed to generate preview image{e}")
        self._generating_preview = False
        self._logger.debug(f"Preview time {time() - previewStart}")

    def get_state_as_string(self):
        """Return the state of the camera as a string."""
        return self.state.name

    # def get_disk_info(self):
    #     # start_get_storageinfo = datetime.now()
    #     # sifs = self._gp_camera.get_storageinfo(GPhotoCam._context)
    #     # print('get_storageinfo delay={:.2f}ms'.format((datetime.now()-start_get_storageinfo).total_seconds()*1000))
    #     # approximately 2.7ms to get storage info
    #     info = {}
    #     try:
    #         sifs = self._gp_camera.get_storageinfo(GPhotoCam._context)[0]
    #         info['freeMB'] = round(sifs.freekbytes / 1024, 2)
    #         info['freeGB'] = round(sifs.freekbytes / 1048576, 2)
    #         info['capacityGB'] = round(sifs.capacitykbytes / 1048576, 2)
    #         info['usedGB'] = round(info['capacityGB'] - info['freeGB'], 2)
    #     except IndexError as ex:
    #         self._logger.warning('Exception: no storage info: %s', ex)
    #         pass
    #     except AttributeError as ex:
    #         self._logger.warning('Exception: invalid storage info: %s', ex)
    #         pass
    #     except Exception as ex:
    #         self._logger.warning('Exception: invalid general storage info: %s', ex)
    #         pass

    #     return info

    def get_im_target_dir(self, timestamp, mount_point, serial_num):
        session_dir = "{}/{}".format(timestamp.strftime('%Y_%m_%d'), self._session_id)
        complete_dir = os.path.join(mount_point, session_dir, str(serial_num))
        return complete_dir

    # def list_camera_files(self, path='/'):
    #     result = []
    #     # get files
    #     gp_list = self._gp_camera.folder_list_files(path, GPhotoCam._context)
    #     for name, value in gp_list:
    #         result.append(os.path.join(path, name))
    #     # read folders
    #     folders = []
    #     gp_list = self._gp_camera.folder_list_folders(path, GPhotoCam._context)
    #     for name, value in gp_list:
    #         folders.append(name)
    #     # recurse over subfolders
    #     for name in folders:
    #         result.extend(self.list_camera_files(os.path.join(path, name)))
    #     return result

    # def get_camera_file_info(self, path):
    #     folder, name = os.path.split(path)
    #     return self._gp_camera.file_get_info(folder, name, GPhotoCam._context)

    # def refresh_camera(self):
    #     try:
    #         self._gp_camera.exit()
    #         # sleep(500e-3)
    #         # self._gp_camera.init(GPhotoCam._context)
    #     except:
    #         pass

    def append_exif_info(self, name, dest_dir, exif_data, md5, current_exif_info):
        # self._logger.debug(f'append_exif_info {len(data_bytes)} name {name} dest_dir {dest_dir}')
        filtered_exif = {}
        # if str(self.config.eosserialnumber) == '113053000777':
        #     for key in exif_data:
        #         self._logger.debug('{} {}'.format(key, exif_data[key]))
        for key in self.KEYS_TO_SAVE:
            if key in exif_data:
                formatted_key = key[key.index(':')+1:]
                filtered_exif[formatted_key] = exif_data[key]

        # do not save temporary filename
        filtered_exif['FileName'] = name
        filtered_exif['FileDir'] = dest_dir
        if not self._disableHashAndPreview:
            filtered_exif['md5'] = md5 
        if 'EXIF:LensSerialNumber' in exif_data:
            self._lens_serial_number = exif_data['EXIF:LensSerialNumber']
        else:
            self._lens_serial_number = ''

        already_saved = False
        if dest_dir not in current_exif_info:
            current_exif_info[dest_dir] = {}
        else:
            # check if image is already saved
            if not self._disableHashAndPreview:
                if filtered_exif['md5'] in current_exif_info[dest_dir]:
                # if any(filtered_exif['md5'] == s['md5'] for s in current_exif_info[dest_dir]):
                    already_saved = True
                    self._logger.debug("File already added to exif info")
            else:
                if filtered_exif['FileName'] in current_exif_info[dest_dir]:
                # if any(filtered_exif['md5'] == s['md5'] for s in current_exif_info[dest_dir]):
                    already_saved = True
                    self._logger.debug("File already added to exif info")
        if not already_saved:
            if not self._disableHashAndPreview:
                current_exif_info[dest_dir][filtered_exif['md5']] = filtered_exif
            else:
                current_exif_info[dest_dir][filtered_exif['FileName']] = filtered_exif
            # current_exif_info[dest_dir].append(filtered_exif)

    def merge_gps_meta_data(self, gps_session_start_time, cam_serial_num, imu_lock ):
        try:
            # read gps data
            imu_dir = os.path.join(self._mount_point, gps_session_start_time.strftime('%Y_%m_%d'))
            complete_gps_dir = os.path.join(imu_dir, 'gpsData.csv')

            gps_times = []
            pi_times = []
            lats = []
            longs = []
            alts = []
            qualities = []
            gpsLatDir = ''
            gpsLongDir = ''

            with imu_lock:
                with open(complete_gps_dir) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    for row in csv_reader:
                        if len(row) > 8:
                            if float(row[1]) != 0 and float(row[2]) != 0 and float(row[3]) != 0 and float(row[5]) != 0 and float(row[7]) != 0:
                                qualities.append(float(row[0]))
                                gps_times.append(float(row[1]))
                                pi_times.append(float(row[2]))
                                lats.append(float(row[3]))
                                gpsLatDir = row[4]
                                longs.append(float(row[5]))
                                gpsLongDir = row[6]
                                alts.append(float(row[7]))
            
            qualities = np.asarray(qualities)
            gps_times = np.asarray(gps_times)
            lats = np.asarray(lats)
            longs = np.asarray(longs)
            alts = np.asarray(alts)

            f_qual = interpolate.interp1d(gps_times, qualities)
            f_lats = interpolate.interp1d(gps_times, lats)
            f_longs = interpolate.interp1d(gps_times, longs)
            f_alts = interpolate.interp1d(gps_times, alts)

            # read accelerometer data
            complete_accel_dir = os.path.join(imu_dir, 'accelData.csv')

            heading = []
            headingComp = []
            kalmanX = []
            kalmanY = []
            pi_times = []
            with imu_lock:
                with open(complete_accel_dir) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    for row in csv_reader:
                        if len(row) > 16:
                            pi_times.append(float(row[0]))
                            heading.append(float(row[13]))
                            headingComp.append(float(row[14]))
                            kalmanX.append(float(row[15]))
                            kalmanY.append(float(row[16]))

            heading = np.asarray(heading)
            headingComp = np.asarray(headingComp)
            kalmanX = np.asarray(kalmanX)
            kalmanY = np.asarray(kalmanY)
            pi_times = np.asarray(pi_times)

            f_heading = interpolate.interp1d(pi_times, heading)
            f_headingComp = interpolate.interp1d(pi_times, headingComp)
            f_kalmanX = interpolate.interp1d(pi_times, kalmanX)
            f_kalmanY = interpolate.interp1d(pi_times, kalmanY)

            cam_session_dir = os.path.join(self._mount_point, gps_session_start_time.strftime('%Y_%m_%d'), gps_session_start_time.strftime('%H_%M_%S'))

            cam_dir = os.path.join(cam_session_dir, cam_serial_num)
            complete_cam_dir = os.path.join(cam_dir, 'exif_cam.json')
            cam_info = {}
            with open(complete_cam_dir, 'r') as f:
                cam_info = json.load(f)
            images = cam_info['exifInfo']
            for key, im in images.items():
                im_time = float(datetime.strptime(im['SubSecDateTimeOriginal'], '%Y:%m:%d %H:%M:%S%z').timestamp())
                try:
                    im['GPSDateStamp'] = im_time
                    im['GPSLatitude'] = np.array(f_lats([im_time]))[0]
                    im['GPSLongitude'] = np.array(f_longs([im_time]))[0]
                    im['GPSAltitude'] = np.array(f_alts([im_time]))[0]
                    im['GPSQuality'] = np.array(f_qual([im_time]))[0]
                    im['Heading'] = np.array(f_heading([im_time]))[0]    
                    im['HeadingComp'] = np.array(f_headingComp([im_time]))[0]     
                    im['KalmanX'] = np.array(f_kalmanX([im_time]))[0]     
                    im['KalmanY'] = np.array(f_kalmanY([im_time]))[0]                        
                    im['GPSLatitudeDir'] = gpsLatDir
                    im['GPSLongitudeDir'] = gpsLongDir
                except Exception as ex:
                    self._logger.warning(f"sonyCAM GPS append failed {ex}")
            cam_info['exifInfo'] = images
            with open(complete_cam_dir, 'w') as f:
                json.dump(cam_info, f, sort_keys=True)   
        except Exception as e:
            self._logger.warning(f"sonyCAM Merge GPS data read failed {e}")

    def save_exif_info(self, serial_number):
        # Iterate through all the folders on the SSD and check that all the exif info is up to date

        et = ExifToolHelper()
        for dirPath, dirs, files in os.walk(os.path.expanduser(self._mount_point)):
            if "in_progress" in dirPath:
                continue
            if not "exif_cam.json" in files:
                imageNames = [name for name in files if (".JPG" in name or ".ARW" in name)]
                if len(imageNames) >0:
                    self._logger.debug('Generating exif info for directory: ' + dirPath)
                    for i in range(len(imageNames)):
                        imageNames[i] = os.path.join(dirPath,imageNames[i])
                    # print("getting exif info for: " + str(absImageNames))
                    exifData = []
                    try:
                        exifData = et.get_tags(imageNames, self.KEYS_TO_SAVE)
                    except Exception as e:
                        self._logger.warning(f"Failed to read exif data for {dirPath}, error: {e}")
                        # Add an empty json entry for this directory to create an empty exif file, preventing this directory from being processed again
                        self._exif_info[dirPath] = {}
                    for i in range(len(exifData)):
                        self.append_exif_info(os.path.split(imageNames[i])[-1],dirPath, exifData[i],"",self._exif_info)

        # Save exif info
        for exif_dir in self._exif_info:
            filename = os.path.join(exif_dir, 'exif_cam.json')
            if not os.path.exists(filename):
                # no existing file
                self._logger.debug('no existing file')
                new_data = {}
                new_data['serialNumber'] = serial_number
                new_data['exifInfo'] = self._exif_info[exif_dir]
                new_data['lensSerialNumber'] = self._lens_serial_number
                # self._logger.debug('serialNumber {} lens {}'.format(new_data['serialNumber'], new_data['lensSerialNumber']))

                # find session index from dest_dir
                dir_split = exif_dir.split('/')
                new_data['sessionId'] = dir_split[-3] + "#" + dir_split[-2] # date (YYYY_MM_DD) + session idx
                
                with open(filename, 'w') as f:
                    json.dump(new_data, f, sort_keys=True)
            else:
                # existing file
                self._logger.debug(f'existing file {exif_dir} {filename}')
                exisiting_data = {}
                try:
                    with open(filename, 'r') as f:
                        exisiting_data = json.load(f)
                    # print("current exif info: " + str(self._exif_info[exif_dir].items()))
                    for key,value in self._exif_info[exif_dir].items():
                        if key in exisiting_data['exifInfo']:
                            # item already added
                            self._logger.debug(f"item already added {value['FileName']}")
                        else:
                            # new item -> add
                            self._logger.debug(f"new item - append {value['FileName']}")
                            exisiting_data['exifInfo'][key] = value
                    with open(filename, 'w') as f:
                        json.dump(exisiting_data, f, sort_keys=True)
                except Exception as e:
                    self._logger.warning(f"Append to existing file failed {e}")
            dir_split = exif_dir.split('/')
            try:
                self.merge_gps_meta_data(datetime.strptime(dir_split[-3] +"_"+ dir_split[-2],"%Y_%m_%d_%H_%M_%S"), dir_split[-1], self._imu_lock)
            except:
                self._logger.warning("failed to append gps data to exif info in directory "+exif_dir)
        self._exif_info = {}


    # def get_camera_image_hash(self, folder, name):
    #     h = "cam"
    #     for i in range(3):
    #         try:
    #             camera_file = self._gp_camera.file_get(folder, name, gp.GP_FILE_TYPE_NORMAL, GPhotoCam._context)
    #             h = hashlib.sha256(memoryview(camera_file.get_data_and_size())).hexdigest()
    #             return h
    #         except:
    #             self._logger.warning("Failed to get %s %s hash" % (folder, name))
    #             sleep(1)
    #     return h

    # def get_external_image_hash(self, path):
    #     h = "ext"
    #     for i in range(3):
    #         try:
    #             f = open(path, "rb")
    #             h = hashlib.sha256(f.read()).hexdigest()
    #             f.close()
    #             return h
    #         except:
    #             self._logger.warning("Failed to get %s hash" % (path))
    #             sleep(1)
    #     return h

    def get_preview_image(self, idx):
        if idx >= len(self._preview_images) or self._generating_preview:
            return ''
        return self._preview_images[idx]

    def get_aspect_ratio(self):
        return self._im_aspect_ratio

    # def get_copy_percentage(self):
    #     if self._num_images_to_copy == 0:
    #         # invalid
    #         return 0

    #     return round(self._num_images_copied / self._num_images_to_copy, 2)

    # def get_copy_exception_count(self):
    #     return self._num_images_failed

    # def get_images_to_copy(self):
    #     return self._num_images_to_copy

    # def get_images_copied(self):
    #     return self._num_images_copied
        
    def sync_time(self):
        # print("Syncing time to "+str(round(datetime.now().timestamp())))
        self._sonyCamera.setDateTime(round(datetime.now().timestamp()))

    @property
    def serial_num(self):
        return self._serial_num

    @property
    def captureCount(self):
        return self._image_count
    
    def get_cam_image_count(self):
        """Return the number of images captured by the camera, as tracked by this object."""
        return self._image_count

    def get_cam_copy_count(self):
        """Return the number of images copied from the Raspberry pi memory to the SSD, as tracked by this object."""
        return self._num_images_copied/2 # div 2 - copy raw and jpeg