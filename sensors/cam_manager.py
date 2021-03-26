"""D Joubert 16 November 2016 - Camera managers for Tricap app."""
# coding=utf-8

# TODO Settings page should show warning for all incorrectly formatted settings

import logging
import threading
import os
import exifread
import copy
import subprocess, time, shutil
from datetime import datetime

from config import CAM_MANAGER_STATES, SERVER_LOG_DIR, SESSION_ROOT_DIR

# TODO : Create a camera factory that will import cameras according to its config and make them available via its own
# autodetect function
try:
    from .canon_6D import Canon6DCam
    from .gphoto_cam import GPhotoCam as Camera
except ImportError:
    logging.getLogger(__name__).warning('Could not import gphoto based libs.')

from .dummy_cam import DummyCam
from .dummy_cam import DummyShell, external_dummy_calibrate_func

from support.basic import RepeatingBarrierPasser

MOUNT_POINT = "/mnt/ext_cam_storage"

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

    supportedCameras = {"Canon EOS 6D", "Dummy Cam"}
    _logger = logging.getLogger(__name__)

    def __init__(self, man_settings: dict, cam_settings: dict, use_dummy_cams=False):
        """Construct."""
        self.state = CAM_MANAGER_STATES.STOPPED

        self._kill_cpy_pill = None
        self._pause_cpy_pill = None
        self._copy_flush_time = None
        self._cpy_threads = list()
        self._capture_threads = list()
        self._kill_preview_pill = None
        self._preview_threads = list()
        self._cameras = None
        self._rate_timer = None
        self._kill_pill = None
        self._cam_settings = cam_settings
        self._man_settings = man_settings
        self.use_dummy_cams = use_dummy_cams
        self.camera_list = ""
        self._initialise()

    def _initialise(self):
        self._find_cameras()

        self._image_capture_interval = float(self._man_settings['image_capture_interval'])

        self.load_preview()

    def is_cam_image_fresh(self, cam_num):
        return self._cameras[cam_num].is_cam_image_fresh()

    def get_data(self, cam_num):
        return self._cameras[cam_num].data

    def get_cam_image_fp(self, cam_num):
        return self._cameras[cam_num].get_cam_image_fp()

    def order_cameras_list(self):
        self.camera_list = self._cameras
        if len(self.camera_list) == 3:
            for camera_nb in range(3):
                if self.camera_list[camera_nb].config.eosserialnumber == "032024003117":
                    self._cameras[0], self.camera_list[camera_nb] = self.camera_list[camera_nb], self._cameras[0]
                elif self.camera_list[camera_nb].config.eosserialnumber == "023052000180":
                    self._cameras[1], self.camera_list[camera_nb] = self.camera_list[camera_nb], self._cameras[1]
                elif self.camera_list[camera_nb].config.eosserialnumber == "413051000325":
                    self._cameras[2], self.camera_list[camera_nb] = self.camera_list[camera_nb], self._cameras[2]

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
                if name in TriCapCamsManager.supportedCameras:
                    self._logger.info('Adding camera %s at address %s ' % (name, address))
                    tricap_cam = Canon6DCam(Camera(address, self._cam_settings))
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
            fp = cam.capture_and_download(target_folder=SESSION_ROOT_DIR, target_name=str(index)+'.CR2')
            with open(fp, 'rb') as im_f:
                tags = exifread.process_file(im_f, stop_tag="GPS GPSLongitude")  # Reduce time of execution by adding a stop tag
                if 'GPS GPSLongitude' in tags.keys():
                    gps_status_of_cams.append(True)
                else:
                    gps_status_of_cams.append(False)

            # get the camera to capture an image and download it to a provided folder
            # get the exif data from the image
            # check if the exif data has the appropriate fields in it.
            # add that to the list

        return gps_status_of_cams

    def start_capturing(self):
        """Start the capturing threads of all connected cams."""
        if len(self._cameras) == 0:
            self.state = CAM_MANAGER_STATES.ERROR_NO_CAMS
            self._logger.debug('Tried to start capture threads with no cameras connected.')
        elif self.state == CAM_MANAGER_STATES.STOPPED or self.state == CAM_MANAGER_STATES.COPYING:
            if self.state == CAM_MANAGER_STATES.COPYING:
                self.stop_copying()
            if self.state == CAM_MANAGER_STATES.LOADING_PREVIEW:
                self.stop_load_preview()

            self._kill_pill = threading.Event()

            for cam in self._cameras:
                cam._camera._image_count = 0

            if self._image_capture_interval != 0:
                barrier = threading.Barrier(len(self._cameras)+1)  # add one for the timer
                self._rate_timer = RepeatingBarrierPasser(self._image_capture_interval,
                                                          self._kill_pill, barrier, daemon=True)
                self._rate_timer.start()
            else:
                barrier = threading.Barrier(len(self._cameras))

            self._capture_threads = list()
            while self.is_copy_thread_alive() or self.is_preview_thread_alive():
                time.sleep(200e-3)
            for cam in self._cameras:  # self.thread was thread
                # TODO This seems to be a mistake, should probaby make a list of the threads
                x = threading.Thread(target=cam.capture, daemon=True, args=(True,barrier,self._kill_pill, ))
                self._capture_threads.append(x)
                x.start()
            self.state = CAM_MANAGER_STATES.STARTED
            self._logger.debug('Cam manager - capture threads started.')

    def stop_capturing(self):
        if self.state == CAM_MANAGER_STATES.STARTED:
            self._kill_pill.set()
            self.state = CAM_MANAGER_STATES.STOPPED
            self.load_preview()
            self._logger.debug('Cam manager - capture threads stopped.')

    def is_copy_thread_alive(self):
        """ Return true if any cam thread is alive """
        for t in self._cpy_threads:
            if t.is_alive():
                return True
        return False

    def is_preview_thread_alive(self):
        """ Return true if any cam thread is alive """
        for t in self._preview_threads:
            if t.is_alive():
                return True
        return False

    def load_preview(self):
        self._logger.debug('Cam manager - preview threads started.')
        self._kill_preview_pill = threading.Event()
        self._preview_threads = list()
        for camera in self._cameras:
            x = threading.Thread(target=camera.load_preview, args=(self._kill_cpy_pill, ), daemon=True)
            self._preview_threads.append(x)
            x.start()
        
        self.state = CAM_MANAGER_STATES.LOADING_PREVIEW

    def stop_load_preview(self):
        self._logger.debug('Cam manager - preview threads stopped.')
        if self._kill_preview_pill:
            self._kill_preview_pill.set()
        self.state = CAM_MANAGER_STATES.STOPPED

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
                mount_status = subprocess.run(["umount", MOUNT_POINT], check=True)
                self._logger.debug(mount_status)
            except:
                self._logger.warning('Failed to umount')
                return False
        else:
            self._logger.info('Disk not mounted')
        return True

    def flush_disk(self):
        if os.path.ismount(MOUNT_POINT):
            try:
                flush_status = subprocess.run(["hdparm", "-F", "/dev/sda1"], check=True)
                self._logger.debug(flush_status)
                return True
            except:
                self._logger.warning("Flush failed")
        else:
            self._logger.info('Disk not mounted')
        return False

    def start_copying(self):
        self._logger.debug('Cam manager - copy threads started.')
        if not self.mount_disk():
            # no disk -> do not copy
            self.state = CAM_MANAGER_STATES.STOPPED
            return

        existing_files = self.list_exisiting_files(MOUNT_POINT)

        self._kill_cpy_pill = threading.Event()
        self._pause_cpy_pill = threading.Event()
        self._copy_flush_time = datetime.now()
        self._cpy_threads = list()
        for index, camera in enumerate(self._cameras):
            x = threading.Thread(target=camera.cpy_images, args=(existing_files, index, MOUNT_POINT, self._kill_cpy_pill, self._pause_cpy_pill, ), daemon=True)
            self._cpy_threads.append(x)
            x.start()

        self.state = CAM_MANAGER_STATES.COPYING

    def stop_copying(self):
        self._logger.debug('Cam manager - copy threads stopped.')
        if self._kill_cpy_pill:
            self._kill_cpy_pill.set()
        self.unmount_disk()
        self.state = CAM_MANAGER_STATES.STOPPED

    def copy_disk_monitor(self):
        """
        If all threads are done -> unmount the external disk
        Flush the external drive cache every 15 minutes during the copy process
        """
        if self.state == CAM_MANAGER_STATES.LOADING_PREVIEW:
            if not self.is_preview_thread_alive():
                self.start_copying()
                return

        if self.state != CAM_MANAGER_STATES.COPYING:
            return
            
        if not os.path.ismount(MOUNT_POINT) or not self._pause_cpy_pill:
            return

        # check if all copy threads are finished
        finished = True
        if os.path.ismount(MOUNT_POINT):
            if self.is_copy_thread_alive():
                finished = False
    
        if not finished:
            # flush external and delete from SD cards every x seconds
            if (datetime.now() - self._copy_flush_time).total_seconds() > 600:
                self._copy_flush_time = datetime.now()
                # pause copy process
                self._pause_cpy_pill.set()
                # wait for current image copy to finish
                time.sleep(3)
                # flush external disk cache -> do this here and not multiple times in gphoto_cam.py
                if self.flush_disk():
                    # flush successful -> unpause, delete and continue copying
                    self._pause_cpy_pill.clear()
                else:
                    # flush failed -> do not delete and stop copying
                    self._pause_cpy_pill.clear()
                    self.stop_copying()
                    return

        if finished and self.state == CAM_MANAGER_STATES.COPYING:
            # flush external disk cache
            if not self.flush_disk():
                # flush failed -> do not delete from SD card
                self.state = CAM_MANAGER_STATES.STOPPED
                return # do not delete images from SD card if there is something wrong with the external
                
            # delete remaining SD card images
            del_threads = list()
            for index, camera in enumerate(self._cameras):
                x = threading.Thread(target=camera.delete_images, daemon=True)
                del_threads.append(x)
                x.start()

            for t in del_threads:
                t.join()

            # unmount external disk
            self.unmount_disk()
            self.state == CAM_MANAGER_STATES.STOPPED

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

            info['totalGB'] = total // 1073741824,
            info['usedGB'] = used // 1073741824,
            info['freeGB'] = free // 1073741824
        
        return info
