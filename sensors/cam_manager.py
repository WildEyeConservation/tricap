"""D Joubert 16 November 2016 - Camera managers for Tricap app."""
# coding=utf-8

# TODO Settings page should show warning for all incorrectly formatted settings

import logging
import threading
import os, json, csv
import subprocess, time
from datetime import datetime
import RPi.GPIO as GPIO
from scipy import interpolate
import numpy as np

from config import (
    CAM_MANAGER_STATES,
    SERVER_LOG_DIR,
    SESSION_ROOT_DIR,
    MOUNT_POINT,
    SONY_TEMPFS_MOUNT_POINT,
    MOUNT_POINT_SSD,
    SONY_IMAGE_FORMAT_CAMERA_SETTING,
    SONY_IMAGE_FORMAT_CHOICES,
    SONY_IMAGE_FORMAT_CONFIG_KEY,
)

# TODO : Create a camera factory that will import cameras according to its config and make them available via its own
# autodetect function
try:
    from .canon_6D import Canon6DCam
    from .gphoto_cam import GPhotoCam as Camera
    from .canon_R import CanonRCam
    from .gpio_cam import GpioCam as CameraGpio
    from .sonySDK_cam import sonySDKcam as CameraSony
    # SonySDKWrapper import must be done after path is added to sys.path
    import sys
    sys.path.append("/home/radxa/tricap")
    sys.path.append(os.path.abspath("/home/radxa/SonySDKWrapper"))
    from sonySDKWrapper import *
except ImportError as e:
    logging.getLogger(__name__).warning(f"Could not import gphoto based libs: {e}")

from .dummy_cam import DummyCam
from .dummy_cam import DummyShell, external_dummy_calibrate_func
from .base_setting import BaseSetting, SettingSpec
from .sony_discovery import discover_sony_cameras

from support.basic import RepeatingBarrierPasser
from support.usb_storage_mode import UsbStorageMode
from statistics import mean


RED_PIN = 17
GREEN_PIN = 27

class MultiConfig:
    dictkeys = ["_cameras", "_context", "_manager"]

    def __init__(self, cameras, manager=None):
        self._cameras = cameras
        self._manager = manager

    def __setattr__(self, key, value):
        if key in self.dictkeys:
            self.__dict__[key] = value
        elif key == SONY_IMAGE_FORMAT_CONFIG_KEY and self._manager is not None:
            self._manager.set_sony_image_format(value)
        elif self._manager is not None and self._manager.use_sony_cam:
            # The Sony wrapper does not expose the generic gPhoto config tree.
            # Retain unrelated Camera-section values without trying to apply
            # Canon-specific settings to a Sony camera.
            self._manager._cam_settings[key] = value
        else:
            for camera in self._cameras:
                camera.config[key] = value

    def __getattr__(self, key):
        if key in self.dictkeys:
            return self.__dict__[key]
        elif key == SONY_IMAGE_FORMAT_CONFIG_KEY and self._manager is not None:
            return BaseSetting(SettingSpec(
                choices=SONY_IMAGE_FORMAT_CHOICES,
                get_value=self._manager.get_sony_image_format,
                set_value=self._manager.set_sony_image_format,
            ))
        elif self._manager is not None and self._manager.use_sony_cam:
            return self._manager._cam_settings.get(key)
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

    def __init__(self, man_settings: dict, cam_settings: dict, use_dummy_cams=False, imu_lock=None, use_gpio_cams=False, use_sony_cam=False):
        """Construct."""
        self.state = CAM_MANAGER_STATES.STOPPED

        self._copy_start_time = None
        self._save_threads = list()
        self._capture_threads = list()
        self._preview_threads = list()
        # Keep this list object for the lifetime of the manager. Other startup
        # components retain a reference to it.
        self._cameras = []
        self.camera_startup_error = ''
        self._usb_storage_mode = None
        self._usb_storage_restart_timer = None
        self._rate_timer = None
        self._stop_capture = None
        self._save_done = list() # sync finish time between capture and save threads
        self._capture_threads_done = list() # sync finish time between capture threads
        self._cam_settings = cam_settings
        self._man_settings = man_settings
        self.use_dummy_cams = use_dummy_cams
        self.use_gpio_cams = use_gpio_cams
        self.use_sony_cam = use_sony_cam
        self.camera_list = ""
        self._shutdownStartTime = None
        self._shutdownEnabled = False
        self._startupTime = datetime.now()
        self._capture_and_copy_lock = list()
        self._save_and_preview_lock = list()
        self._imu_lock = imu_lock
        self._thread_sync_lock = None
        # stop time sync -> fix pi time to camera time
        if not use_gpio_cams:
            subprocess.run(["timedatectl", "set-ntp", "false"], check=True)
        self._initialise()
        self.mount_disk()

    def _initialise(self):
        try:
            self._find_cameras(discovery_attempts=5)
        except Exception as exc:
            self.camera_startup_error = str(exc)
            self._logger.error(
                'Camera startup failed; dashboard will remain available and '
                'storage operations can continue. Restart Tricap after '
                'reconnecting cameras: %s',
                exc,
                exc_info=True,
            )

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

    def _find_cameras(self, discovery_attempts=15):
        # Let callers decide whether a failed pass should affect startup or be
        # reported by the background retry loop.

        if self.use_gpio_cams:
            tricap_cam = CameraGpio()
            self._cameras.append(tricap_cam)
        elif self.use_dummy_cams:
            for name, address in DummyCam.autodetect():
                if name in TriCapCamsManager.supportedCameras:
                    self._logger.info('Adding camera %s at address %s ' % (name, address))
                    tricap_cam = DummyShell(DummyCam(address, self._cam_settings))
                    tricap_cam._camera.calibrate_func = external_dummy_calibrate_func
                    tricap_cam._camera.calibrate_step = int(self._man_settings['calibrate_step'])
                    self._cameras.append(tricap_cam)
        elif self.use_sony_cam:
            self._sonySDKInstance, numCameras = discover_sony_cameras(
                sonyCamera,
                attempts=discovery_attempts,
                logger=self._logger,
            )
            self._sonySDKCamCaptureLock = threading.Lock()
            discovered_cameras = []
            for i in range(1, numCameras + 1):
                try:
                    tricap_cam = CameraSony(
                        SONY_TEMPFS_MOUNT_POINT, self._sonySDKInstance, i,
                        self._sonySDKCamCaptureLock,
                        self.get_sony_image_format())
                    discovered_cameras.append(tricap_cam)
                except Exception as exc:
                    self._logger.warning(
                        'Camera %s could not be initialised: %s',
                        i, exc, exc_info=True)

            if not discovered_cameras:
                raise RuntimeError(
                    'Sony cameras were detected, but none could be initialised'
                )
            self._cameras.extend(discovered_cameras)
            self.camera_startup_error = ''
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

        if not self.use_gpio_cams:
            if self.state == CAM_MANAGER_STATES.STARTED and (not self.is_capture_thread_alive() or not self.is_save_thread_alive()):
                # started, but capture threads are not alive -> sleep 
                self._logger.debug('Cam manager - waiting for threads to end')
                while self.is_capture_thread_alive() or self.is_save_thread_alive():
                    time.sleep(50e-3)
                self._logger.debug('Cam manager - threads ended')
                self.copy_disk_monitor()
            if len(self._cameras) == 0:
                self.state = CAM_MANAGER_STATES.ERROR_NO_CAMS
                self._logger.debug('Tried to start capture threads with no cameras connected.')
            elif self.state == CAM_MANAGER_STATES.STOPPED:
                try:
                    if getattr(self, 'altimeter', None) is not None:
                        self.altimeter.start_measuring()
                except Exception as e:
                    self._logger.warning(f"Cam manager - altimeter start failed: {e}")
                if self.use_sony_cam:
                    for cam in self._cameras:
                        cam._image_count = 0
                else:
                    for cam in self._cameras:
                        cam._camera._image_count = 0
                
                self._logger.debug('Cam manager - start capturing thread')
                self._stop_capture = threading.Event()
                self._stop_capture.clear()

                if len(self._capture_and_copy_lock) == 0 and \
                    len(self._save_and_preview_lock) == 0 and \
                    len(self._capture_threads_done) == 0 and \
                    len(self._save_done) == 0:
                    # first time
                    self._logger.debug('Cam manager - create thread interlocks')
                    self._thread_sync_lock = threading.Lock()
                    for cam in self._cameras:
                        self._capture_and_copy_lock.append(threading.Lock())
                        self._save_and_preview_lock.append(threading.Lock()) 
                        self._capture_threads_done.append(threading.Event())
                        self._save_done.append(threading.Event())

                if not self.mount_disk():
                    # no disk -> do not copy

                    # Double cam setup captures to CAM SD cards, so ignore the SSD not mounting and continue anyway
                    # self.state = CAM_MANAGER_STATES.STOPPED
                    self._logger.warning('Cam manager - no ssd -> do no start capturing')
                    # return

                global_start_time = time.time() + 0.5
                self._copy_start_time = datetime.now()
                self._capture_threads.clear()
                for index, cam in enumerate(self._cameras):  # self.thread was thread
                    self._capture_threads_done[index].clear()
                    self._save_done[index].clear()
                    if(not self.use_sony_cam):
                        x = threading.Thread(target=cam.capture_and_copy, daemon=True, args=(self._image_capture_interval, global_start_time, self._copy_start_time, str(cam.serial_num), self._stop_capture, self._capture_and_copy_lock[index], index, self._capture_threads_done, self._save_done[index], self._thread_sync_lock, ))
                    else:
                        x = threading.Thread(target=cam.capture_and_copy, daemon=True, args=(MOUNT_POINT, self._image_capture_interval, global_start_time, self._copy_start_time, str(cam.serial_num), self._stop_capture, self._capture_and_copy_lock[index], index, self._capture_threads_done, self._save_done[index], self._thread_sync_lock, ))
                    self._capture_threads.append(x)

                existing_files = self.list_exisiting_files(MOUNT_POINT)
                self._save_threads.clear()
                for index, cam in enumerate(self._cameras):  # self.thread was thread
                    if(not self.use_sony_cam):
                        x = threading.Thread(target=cam.save_to_ssd, daemon=True, args=(MOUNT_POINT, existing_files, str(cam.serial_num), self._capture_and_copy_lock[index], self._save_and_preview_lock[index], self._capture_threads_done, self._save_done[index], self._thread_sync_lock, ))
                    else:
                        x = threading.Thread(target=cam.save_to_ssd, daemon=True, args=(MOUNT_POINT, existing_files, str(cam.serial_num), self._capture_and_copy_lock[index], self._save_and_preview_lock[index], self._capture_threads_done, self._save_done[index], self._thread_sync_lock, self._imu_lock, ))
                    self._save_threads.append(x)

                for t in self._capture_threads:
                    t.start()

                for t in self._save_threads:
                    t.start()

                self.state = CAM_MANAGER_STATES.STARTED
                self._logger.debug('Cam manager - capture threads started.')
            elif self.state == CAM_MANAGER_STATES.STARTED:
                self._stop_capture.clear()
                self._logger.debug('Cam manager - continue capturing thread')
        else: 
            # use gpio cams
            if self.state == CAM_MANAGER_STATES.STARTED:
                # already started
                self._logger.debug('Cam manager - continue capturing thread')
            elif self.state == CAM_MANAGER_STATES.STOPPED:
                self._logger.debug('Cam manager - start capturing thread')
                self._stop_capture = threading.Event()
                self._stop_capture.clear()
                barrier = threading.Barrier(2)  # one for the timer and one for the gpio camera
            
                self._capture_threads.clear()
                for index, cam in enumerate(self._cameras):  # self.thread was thread
                    self._capture_threads.append(threading.Thread(target=cam.capture, daemon=True, args=(barrier, )))
                
                self._rate_timer = RepeatingBarrierPasser(self._image_capture_interval, self._stop_capture, barrier, daemon=True)
                self._rate_timer.start()
                for t in self._capture_threads:
                    t.start()

                self.state = CAM_MANAGER_STATES.STARTED
                self._logger.debug('Cam manager - capture threads started.')

    def stop_capturing(self):
        try:
            if getattr(self, 'altimeter', None) is not None:
                self.altimeter.stop_measuring()
        except Exception as e:
            self._logger.warning(f"Cam manager - altimeter stop failed: {e}")
        if self.state == CAM_MANAGER_STATES.STARTED:
            self._stop_capture.set()

            self._logger.debug('Cam manager - capture threads stop requested.')

            if self.use_gpio_cams:
                self.state = CAM_MANAGER_STATES.STOPPED
                self._logger.debug('Cam manager - capture threads stopped.')

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
                    mount_status = subprocess.run(["mount", "/dev/nvme0n1p1", MOUNT_POINT], check=True)
                    self._logger.debug(mount_status)
            except:
                self._logger.warning('Failed to mount')
                return False
        else:
            self._logger.info('Disk already mounted')
        return True

    def mount_ssd(self):
        if not os.path.ismount(MOUNT_POINT_SSD):
            device = self.external_ssd_device()
            if device is None:
                self._logger.warning('SSD not connected')
                return False
            try:
                os.makedirs(MOUNT_POINT_SSD, exist_ok=True)
                mount_status = subprocess.run(
                    ["mount", device, MOUNT_POINT_SSD], check=True)
                self._logger.debug(mount_status)
            except (OSError, subprocess.SubprocessError) as exc:
                self._logger.warning('Failed to mount %s: %s', device, exc)
                return False
        else:
            self._logger.info('Disk already mounted')

        try:
            if os.statvfs(MOUNT_POINT_SSD).f_flag & os.ST_RDONLY:
                self._logger.warning('External SSD is mounted read-only')
                return False
        except OSError as exc:
            self._logger.warning('Failed to inspect external SSD mount: %s', exc)
            return False
        return True

    def external_ssd_device(self):
        """Return the first filesystem-bearing partition on a USB disk."""
        try:
            output = subprocess.check_output([
                "lsblk", "--json", "--paths", "--output",
                "NAME,PATH,TYPE,FSTYPE,TRAN",
            ], text=True)
            block_devices = json.loads(output).get("blockdevices", [])
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            self._logger.warning('Failed to discover external SSD: %s', exc)
            return None

        for disk in block_devices:
            if disk.get("tran") != "usb":
                continue
            candidates = disk.get("children") or [disk]
            for candidate in candidates:
                if (candidate.get("type") in ("disk", "part") and
                        candidate.get("fstype") and candidate.get("path")):
                    return candidate["path"]
        return None

    def unmount_disk(self):
        if os.path.ismount(MOUNT_POINT_SSD):
            try:
                mount_status = subprocess.run(["umount", MOUNT_POINT_SSD], check=True)
                self._logger.debug(mount_status)
            except:
                self._logger.warning('Failed to umount')
                return False
        else:
            self._logger.info('Disk not mounted')
        return True

    def begin_usb_storage_mode(self):
        """Disconnect USB sensors while preserving Wi-Fi and external storage."""
        if self._usb_storage_mode is not None:
            return True

        mode = UsbStorageMode(logger=self._logger)
        external_device = self.external_ssd_device()
        targets = mode.plan(external_device)
        if not targets:
            self._logger.info(
                'USB storage mode found no non-essential devices to disconnect'
            )
            return True

        try:
            if getattr(self, 'altimeter', None) is not None:
                self.altimeter.stop_measuring()
                self.altimeter.disconnect()

            if (self.use_sony_cam and self._cameras
                    and hasattr(self, '_sonySDKCamCaptureLock')):
                with self._sonySDKCamCaptureLock:
                    for camera in self._cameras:
                        camera.disconnect_for_storage()

            changed = mode.quiesce(external_device)
            self._usb_storage_mode = mode
            self._logger.info(
                'USB storage mode active; disconnected: %s',
                ', '.join(changed),
            )
            return True
        except Exception:
            self._logger.exception('Could not enter USB storage mode')
            mode.restore()
            self._schedule_usb_storage_restart()
            return False

    def end_usb_storage_mode(self):
        """Restore USB sensors and restart Tricap so drivers rediscover them."""
        mode = self._usb_storage_mode
        self._usb_storage_mode = None
        if mode is None:
            return
        mode.restore()
        self._logger.info('USB storage mode ended; devices were restored')
        self._schedule_usb_storage_restart()

    def _schedule_usb_storage_restart(self, delay=5.0):
        if (self._usb_storage_restart_timer is not None
                and self._usb_storage_restart_timer.is_alive()):
            return

        def restart_service():
            self._logger.info(
                'Restarting Tricap after USB storage mode device restoration'
            )
            try:
                subprocess.Popen(
                    ['systemctl', 'restart', 'tricap.service'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except Exception:
                self._logger.exception(
                    'Could not restart Tricap after USB storage mode'
                )

        self._usb_storage_restart_timer = threading.Timer(
            delay, restart_service
        )
        self._usb_storage_restart_timer.daemon = True
        self._usb_storage_restart_timer.start()

    def copy_disk_monitor(self):
        """
        If all threads are done -> unmount the external disk
        """

        if not self.is_save_thread_alive() and self.state == CAM_MANAGER_STATES.STARTED:
            self._logger.debug("Save completed - unmount disk")

            self.merge_gps_meta_data()

            self._shutdownEnabled = True
            self._shutdownStartTime = datetime.now()
            self.state = CAM_MANAGER_STATES.STOPPED

            # A successful trigger leaves each camera in CAPTURING. Once all
            # capture/save threads have finished, return successful cameras to
            # their ready state without masking a genuine error state.
            for cam in self._cameras:
                if cam.state.name == 'CAPTURING':
                    cam.state = type(cam.state).INITIALISED

        # if self.state == CAM_MANAGER_STATES.STOPPED and self._shutdownEnabled:
        #     if (datetime.now() - self._shutdownStartTime).total_seconds() > 9000:
        #         GPIO.output(RED_PIN, GPIO.LOW)
        #         GPIO.output(GREEN_PIN, GPIO.LOW)
        #         subprocess.call('poweroff', shell=True)

    def merge_gps_meta_data(self):
        # this is outdated -> accelData.csv changed to accelData.bin with raw values only
        return 
        if(self.use_sony_cam):
            return
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
        self._image_capture_interval = value

    def get_calibrate_step(self):
        return self._man_settings['calibrate_step']

    def set_calibrate_step(self, value):
        self._man_settings['calibrate_step'] = value

    def get_num_cams(self):
        return len(self._cameras)

    def get_cam_ids(self):
        if self.use_gpio_cams:
            return []

        cam_ids = []
        for cam in self._cameras:
            if cam.serial_num is not None:
                cam_ids.append(cam.serial_num)
            else:
                cam_ids.append('Unknown')
        return cam_ids

    @property
    def config(self):
        return MultiConfig(self._cameras, self)

    def get_sony_image_format(self):
        """Return the configured Sony image-format behavior."""
        return self._cam_settings.get(
            SONY_IMAGE_FORMAT_CONFIG_KEY,
            SONY_IMAGE_FORMAT_CAMERA_SETTING,
        )

    def set_sony_image_format(self, image_format):
        """Store the value and apply explicit overrides to Sony cameras."""
        if image_format not in SONY_IMAGE_FORMAT_CHOICES:
            raise ValueError(
                "Unsupported Sony image format {!r}; expected one of {}".format(
                    image_format, SONY_IMAGE_FORMAT_CHOICES
                )
            )

        if self.use_sony_cam:
            for camera in self._cameras:
                camera.set_image_format(image_format)
        self._cam_settings[SONY_IMAGE_FORMAT_CONFIG_KEY] = image_format

    def copy_eta(self):
        if self._copy_start_time == None or self.use_gpio_cams or self.use_sony_cam:
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
        if self.use_gpio_cams:
            return

        subprocess.run(["timedatectl", "set-time", time_str], check=True)

        for cam in self._cameras:
            cam.sync_time()

    def start_preview(self):
        if self.use_gpio_cams:
            return

        if len(self._save_and_preview_lock) == 0:
            return False

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
