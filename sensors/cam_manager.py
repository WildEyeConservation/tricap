"""D Joubert 16 November 2016 - Camera managers for Tricap app."""
# coding=utf-8

# TODO Settings page should show warning for all incorrectly formatted settings

import logging
import threading
import os, json, csv
import subprocess, time, shutil
from datetime import datetime
import RPi.GPIO as GPIO
from scipy import interpolate
import numpy as np

from config import CAM_MANAGER_STATES, SERVER_LOG_DIR, SESSION_ROOT_DIR, MOUNT_POINT

# TODO : Create a camera factory that will import cameras according to its config and make them available via its own
# autodetect function
try:
    from .canon_6D import Canon6DCam
    from .gphoto_cam import GPhotoCam as Camera
    from .canon_R import CanonRCam
except ImportError:
    logging.getLogger(__name__).warning('Could not import gphoto based libs.')

from .dummy_cam import DummyCam
from .dummy_cam import DummyShell, external_dummy_calibrate_func

from support.basic import RepeatingBarrierPasser
from statistics import mean


RED_PIN = 17
GREEN_PIN = 27

class MultiConfig:
    dictkeys = ["_cameras", "_context"]

    def __init__(self, cameras):
        self._cameras = cameras

    def __setattr__(self, key, value):
        if key in self.dictkeys:
            self.__dict__[key] = value
        else:
            for camera in self._cameras:
                camera.config[key] = value

    def __getattr__(self, key):
        if key in self.dictkeys:
            return self.__dict__[key]
        else:
            return self._cameras[0].config[key]

    __setitem__ = __setattr__
    __getitem__ = __getattr__

    def get_tree(self):
        return self._cameras[0].config.get_tree()


class TriCapCamsManager:
    """TriCapCamsManager manages TriCap camera objects"""

    supportedCameras = {"Canon EOS 6D", "Dummy Cam", "Canon EOS R"}
    _logger = logging.getLogger(__name__)

    def __init__(self, man_settings: dict, cam_settings: dict, use_dummy_cams=False, imu_lock=None):
        """Construct."""
        self.state = CAM_MANAGER_STATES.STOPPED

        self._copy_start_time = None
        self._save_threads = list()
        self._capture_threads = list()
        self._preview_threads = list()
        self._cameras = None
        self._rate_timer = None
        self._stop_capture = None
        self._stop_save_to_ssd = None
        self._cam_settings = cam_settings
        self._man_settings = man_settings
        self.use_dummy_cams = use_dummy_cams
        self.camera_list = ""
        self._shutdownStartTime = None
        self._shutdownEnabled = False
        self._startupTime = datetime.now()
        self._capture_and_copy_lock = list()
        self._save_and_preview_lock = list()
        self._imu_lock = imu_lock
        # stop time sync -> fix pi time to camera time
        subprocess.run(["timedatectl", "set-ntp", "false"], check=True)
        self._initialise()

    def _initialise(self):
        self._find_cameras()

        self._image_capture_interval = float(self._man_settings['image_capture_interval'])

    def is_cam_image_fresh(self, cam_num):
        return self._cameras[cam_num].is_cam_image_fresh()

    def get_data(self, cam_num):
        return self._cameras[cam_num].data

    def get_cam_image_fp(self, cam_num):
        return self._cameras[cam_num].get_cam_image_fp()

    def order_cameras_list(self):
        self.camera_list = self._cameras
        # if len(self.camera_list) == 3:
        #     for camera_nb in range(3):
        #         if self.camera_list[camera_nb].config.eosserialnumber == "032024003117":
        #             self._cameras[0], self.camera_list[camera_nb] = self.camera_list[camera_nb], self._cameras[0]
        #         elif self.camera_list[camera_nb].config.eosserialnumber == "023052000180":
        #             self._cameras[1], self.camera_list[camera_nb] = self.camera_list[camera_nb], self._cameras[1]
        #         elif self.camera_list[camera_nb].config.eosserialnumber == "413051000325":
        #             self._cameras[2], self.camera_list[camera_nb] = self.camera_list[camera_nb], self._cameras[2]

    def show_cameras_list(self):
        for camera_nb in range(3):
            print(self._cameras[camera_nb].config.eosserialnumber)

    def get_cameras_as_list(self):  # Sort this list
        return self._cameras

    def get_state(self):
        return self.state

    def _find_cameras(self):
        self._cameras = []
        # Do not catch exceptions here. If any detected camera fails to instantiate, it is a critical error and we want
        # to halt and catch fire.

        if self.use_dummy_cams:
            for name, address in DummyCam.autodetect():
                if name in TriCapCamsManager.supportedCameras:
                    self._logger.info('Adding camera %s at address %s ' % (name, address))
                    tricap_cam = DummyShell(DummyCam(address, self._cam_settings))
                    tricap_cam._camera.calibrate_func = external_dummy_calibrate_func
                    tricap_cam._camera.calibrate_step = int(self._man_settings['calibrate_step'])
                    self._cameras.append(tricap_cam)
        else:
            for name, address in Camera.autodetect():
                self._logger.info('Detected camera %s at address %s ' % (name, address))
                if name in TriCapCamsManager.supportedCameras:
                    self._logger.info('Adding camera %s at address %s ' % (name, address))
                    if name == "Canon EOS 6D":                    
                        tricap_cam = Canon6DCam(Camera(address, self._cam_settings))
                    elif name == "Canon EOS R":
                        tricap_cam = CanonRCam(Camera(address, self._cam_settings))
                    else:
                        # this should not happen
                        continue
                        
                    tricap_cam._camera.rate_fp = os.path.join(SERVER_LOG_DIR,
                                                    'canon6dcam_%s_rates.txt' % tricap_cam.serial_num)
                    # tricap_cam._camera.calibrate_func = tricap_cam.focus_infinity
                    tricap_cam._camera.calibrate_step = int(self._man_settings['calibrate_step'])
                    self._cameras.append(tricap_cam)
            self.order_cameras_list()
            # self.show_cameras_list()

    # def reset(self, man_settings: dict, cam_settings: dict):
    #     self._man_settings = man_settings
    #     self._cam_settings = cam_settings
    #
    #     if self.state == CAM_MANAGER_STATES.STARTED:
    #         self.stop_capturing()
    #
    #     self._initialise()

    def check_camera_gps_status(self):
        """Check gps status of all connected cameras and return boolean for each camera.

        For each camera, take a picture, download it, and check the gps info in the exif data.
        """
        gps_status_of_cams = []
        for index, cam in enumerate(self._cameras):
            try:
                exif = cam.capture_and_read_exif()
                if 'Composite:GPSLatitude' in exif.keys():
                    gps_status_of_cams.append(True)
                else:
                    gps_status_of_cams.append(False)
            except:
                self._logger.debug('Failed to read GPSLongitude from exifdata')
                gps_status_of_cams.append(False)

            # get the camera to capture an image and download it to a provided folder
            # get the exif data from the image
            # check if the exif data has the appropriate fields in it.
            # add that to the list

        return gps_status_of_cams

    def start_capturing(self):
        """Start the capturing threads of all connected cams."""
        self._shutdownEnabled = False
        self._logger.debug(f"Cam manager - current state {self.state}")
        if len(self._cameras) == 0:
            self.state = CAM_MANAGER_STATES.ERROR_NO_CAMS
            self._logger.debug('Tried to start capture threads with no cameras connected.')
        elif self.state == CAM_MANAGER_STATES.STOPPED:
            for cam in self._cameras:
                cam._camera._image_count = 0
            
            self._logger.debug('Cam manager - start capturing thread')
            self._stop_capture = threading.Event()
            self._stop_capture.clear()
            self._stop_save_to_ssd = threading.Event()
            self._stop_save_to_ssd.clear()

            if len(self._capture_and_copy_lock) == 0:
                for cam in self._cameras:
                    self._capture_and_copy_lock.append(threading.Lock())

            if len(self._save_and_preview_lock) == 0:
                for cam in self._cameras:
                    self._save_and_preview_lock.append(threading.Lock())  

            if not self.mount_disk():
                # no disk -> do not copy
                self.state = CAM_MANAGER_STATES.STOPPED
                self._logger.warning('Cam manager - no ssd -> do no start capturing')
                return

            global_start_time = time.time() + 0.5
            self._copy_start_time = datetime.now()
            self._capture_threads.clear()
            for index, cam in enumerate(self._cameras):  # self.thread was thread
                x = threading.Thread(target=cam.capture_and_copy, daemon=True, args=(self._image_capture_interval, global_start_time, self._copy_start_time, str(cam.serial_num), self._stop_capture, self._capture_and_copy_lock[index], ))
                self._capture_threads.append(x)
            
            existing_files = self.list_exisiting_files(MOUNT_POINT)
            self._save_threads.clear()
            for index, cam in enumerate(self._cameras):  # self.thread was thread
                x = threading.Thread(target=cam.save_to_ssd, daemon=True, args=(MOUNT_POINT, existing_files, str(cam.serial_num), self._stop_save_to_ssd, self._capture_and_copy_lock[index], self._save_and_preview_lock[index], ))
                self._save_threads.append(x)

            for t in self._capture_threads:
                t.start()

            for t in self._save_threads:
                t.start()

            self.state = CAM_MANAGER_STATES.STARTED
            self._logger.debug('Cam manager - capture threads started.')
        elif self.state == CAM_MANAGER_STATES.STARTED:
            self._logger.debug('Cam manager - continue capturing thread')
            self._stop_capture.clear()

    def stop_capturing(self):
        if self.state == CAM_MANAGER_STATES.STARTED:
            self._stop_capture.set()

            self._logger.debug('Cam manager - capture threads stop requested.')

    def is_capture_thread_alive(self):
        """ Return true if any cam thread is alive """
        for t in self._capture_threads:
            if t.is_alive():
                return True
        return False

    def is_save_thread_alive(self):
        """ Return true if any cam thread is alive """
        for t in self._save_threads:
            if t.is_alive():
                return True
        return False

    def is_preview_thread_alive(self):
        """ Return true if any cam thread is alive """
        for t in self._preview_threads:
            if t.is_alive():
                return True
        return False

    def list_exisiting_files(self, dir):
        result = []
        for root, dirs, files in os.walk(os.path.expanduser(dir)):
            for name in files:
                if '.thumbs' in dirs:
                    dirs.remove('.thumbs')
                if name in ('.directory',):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext in ('.db',):
                    continue
                result.append(os.path.join(root, name))
        return result

    def mount_disk(self):
        if not os.path.ismount(MOUNT_POINT):
            try:
                with self._imu_lock:
                    mount_status = subprocess.run(["mount", "/dev/sda1", MOUNT_POINT], check=True)
                    self._logger.debug(mount_status)
            except:
                self._logger.warning('Failed to mount')
                return False
        else:
            self._logger.info('Disk already mounted')
        return True

    def unmount_disk(self):
        if os.path.ismount(MOUNT_POINT):
            try:
                with self._imu_lock:
                    mount_status = subprocess.run(["umount", MOUNT_POINT], check=True)
                    self._logger.debug(mount_status)
            except:
                self._logger.warning('Failed to umount')
                return False
        else:
            self._logger.info('Disk not mounted')
        return True

    def copy_disk_monitor(self):
        """
        If all threads are done -> unmount the external disk
        """

        if not self.is_capture_thread_alive() and self.state == CAM_MANAGER_STATES.STARTED:
            self._logger.debug("Capture and copy completed - wait for save to complete")
            self._stop_save_to_ssd.set()
            self.state = CAM_MANAGER_STATES.COPYING

        if not self.is_save_thread_alive() and self.state == CAM_MANAGER_STATES.COPYING:
            self._logger.debug("Save completed - unmount disk")
            self.state = CAM_MANAGER_STATES.STOPPED

            self.merge_gps_meta_data()

            self.unmount_disk()
            self._shutdownEnabled = True
            self._shutdownStartTime = datetime.now()

        # if self.state == CAM_MANAGER_STATES.STOPPED and self._shutdownEnabled:
        #     if (datetime.now() - self._shutdownStartTime).total_seconds() > 9000:
        #         GPIO.output(RED_PIN, GPIO.LOW)
        #         GPIO.output(GREEN_PIN, GPIO.LOW)
        #         subprocess.call('poweroff', shell=True)

    def merge_gps_meta_data(self):
        try:
            # read gps data
            imu_dir = os.path.join(MOUNT_POINT, self._copy_start_time.strftime('%Y_%m_%d'))
            complete_gps_dir = os.path.join(imu_dir, 'gpsData.csv')

            gps_times = []
            pi_times = []
            lats = []
            longs = []
            alts = []
            qualities = []
            gpsLatDir = ''
            gpsLongDir = ''
            with self._imu_lock:
                with open(complete_gps_dir) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    for row in csv_reader:
                        if len(row) > 8:
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
            pi_times = np.asarray(pi_times)
            lats = np.asarray(lats)
            longs = np.asarray(longs)
            alts = np.asarray(alts)

            f_qual = interpolate.interp1d(pi_times, qualities)
            f_gps_times = interpolate.interp1d(pi_times, gps_times)
            f_lats = interpolate.interp1d(pi_times, lats)
            f_longs = interpolate.interp1d(pi_times, longs)
            f_alts = interpolate.interp1d(pi_times, alts)

            # read accelerometer data
            complete_accel_dir = os.path.join(imu_dir, 'accelData.csv')

            heading = []
            headingComp = []
            kalmanX = []
            kalmanY = []
            pi_times = []
            with self._imu_lock:
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

            cam_session_dir = os.path.join(MOUNT_POINT, self._copy_start_time.strftime('%Y_%m_%d'), self._copy_start_time.strftime('%H_%M_%S'))
            for cam in self._cameras:
                cam_dir = os.path.join(cam_session_dir, str(cam.serial_num))
                complete_cam_dir = os.path.join(cam_dir, 'exif_cam.json')
                cam_info = {}
                with open(complete_cam_dir, 'r') as f:
                    cam_info = json.load(f)
                images = cam_info['exifInfo']
                for im in images:
                    im_time = float(datetime.strptime(im['SubSecDateTimeOriginal'], '%Y:%m:%d %H:%M:%S.%f').timestamp())
                    try:
                        im['GPSDateStamp'] = np.array(f_gps_times([im_time]))[0]
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
                        self._logger.warning(f"GPS append failed {ex}")
                cam_info['exifInfo'] = images
                with open(complete_cam_dir, 'w') as f:
                    json.dump(cam_info, f, sort_keys=True)   
        except Exception as e:
            self._logger.warning(f"Merge GPS data read failed {e}")

    def get_image_capture_interval(self):
        return self._man_settings['image_capture_interval']

    def set_image_capture_interval(self, value):
        self._man_settings['image_capture_interval'] = value

    def get_calibrate_step(self):
        return self._man_settings['calibrate_step']

    def set_calibrate_step(self, value):
        self._man_settings['calibrate_step'] = value

    def get_num_cams(self):
        return len(self._cameras)

    def get_cam_ids(self):
        cam_ids = []
        for cam in self._cameras:
            if cam.serial_num is not None:
                cam_ids.append(cam.serial_num)
            else:
                cam_ids.append('Unknown')
        return cam_ids

    @property
    def config(self):
        return MultiConfig(self._cameras)

    def external_disk_info(self):
        self._logger.debug('external_disk_info')
        info = {}
        is_mounted = os.path.ismount(MOUNT_POINT)
        if self.mount_disk():
            total, used, free = shutil.disk_usage(MOUNT_POINT)
            if not is_mounted:
                # only unmount if unmounted at the start of this function
                self.unmount_disk()

            info['capacityGB'] = round(total / 1073741824, 2)
            info['usedGB'] = round(used / 1073741824, 2)
            info['freeGB'] = round(free / 1073741824, 2)
        
        return info

    def copy_eta(self):
        if self._copy_start_time == None:
            return ""
        ret = {}
        all_cam_copy_percentage = []
        all_cam_copy_exceptions = []
        all_cam_copied = []
        all_cam_captured = []
        for cam in self._cameras:
            all_cam_copy_percentage.append(cam.get_copy_percentage())
            all_cam_copy_exceptions.append(cam.get_copy_exception_count())
            all_cam_copied.append(cam.get_images_copied())
            all_cam_captured.append(cam.get_images_to_copy())
        
        ret['exceptions'] = all_cam_copy_exceptions
        ret['copied'] = all_cam_copied
        ret['captured'] = all_cam_captured
        average_percentage = mean(all_cam_copy_percentage)
        if average_percentage == 0:
            ret['percentage'] = 0
            ret['timeRemaining'] = "Calculating..."
            return ret
        elapsed_sec = (datetime.now() - self._copy_start_time).total_seconds()
        remaining_sec = elapsed_sec / average_percentage - elapsed_sec
        minutes = remaining_sec // 60
        hours = minutes // 60

        ret['percentage'] = round(average_percentage, 2)
        ret['timeRemaining'] = "%02dh:%02dm:%02ds" % (hours, minutes % 60, remaining_sec % 60)
        return ret

    def sync_time(self, time_str):
        subprocess.run(["timedatectl", "set-time", time_str], check=True)

        for cam in self._cameras:
            cam.sync_time()

    def start_preview(self):
        if not self.is_preview_thread_alive():
            self._logger.debug('Cam manager - start preview thread')
            self._preview_threads.clear()
            for index, cam in enumerate(self._cameras):
                x = threading.Thread(target=cam.load_preview_images, daemon=True, args=(self._save_and_preview_lock[index], ))
                self._preview_threads.append(x)

            for t in self._preview_threads:
                t.start()
            
            return True
        
        return False

        
    @property
    def mount_point(self):
        return MOUNT_POINT
