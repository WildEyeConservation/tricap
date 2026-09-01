"""D Joubert 16 November 2016 - Camera managers for Tricap app."""
# coding=utf-8

# TODO Settings page should show warning for all incorrectly formatted settings

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

from config import (
    CAM_MANAGER_STATES,
    MOUNT_POINT,
    SONY_TEMPFS_MOUNT_POINT,
    MOUNT_POINT_SSD,
    SONY_IMAGE_FORMAT_CAMERA_SETTING,
    SONY_IMAGE_FORMAT_CHOICES,
    SONY_IMAGE_FORMAT_CONFIG_KEY,
)

from support.ssd_volume import find_volume

from .base_setting import BaseSetting, SettingSpec
from .sony_discovery import discover_sony_cameras
from .sonySDK_cam import sonySDKcam as SonyCamera


def _disk_usage_gb(path):
    total, used, free = shutil.disk_usage(path)
    gb = 1073741824
    return {"capacityGB": round(total / gb, 2), "usedGB": round(used / gb, 2), "freeGB": round(free / gb, 2)}


def create_sony_sdk():
    wrapper_path = os.path.abspath("/home/radxa/SonySDKWrapper")
    if wrapper_path not in sys.path:
        sys.path.append(wrapper_path)
    from sonySDKWrapper import sonyCamera
    return sonyCamera()


class CameraSettings:
    def __init__(self, manager):
        object.__setattr__(self, "_manager", manager)

    def __setattr__(self, key, value):
        if key == SONY_IMAGE_FORMAT_CONFIG_KEY:
            self._manager.set_sony_image_format(value)
        else:
            self._manager._cam_settings[key] = value

    def __getattr__(self, key):
        if key == SONY_IMAGE_FORMAT_CONFIG_KEY:
            return BaseSetting(SettingSpec(
                choices=SONY_IMAGE_FORMAT_CHOICES,
                get_value=self._manager.get_sony_image_format,
                set_value=self._manager.set_sony_image_format,
            ))
        return self._manager._cam_settings.get(key)

    __setitem__ = __setattr__
    __getitem__ = __getattr__


class TriCapCamsManager:
    """TriCapCamsManager manages TriCap camera objects"""

    _logger = logging.getLogger(__name__)

    def __init__(self, man_settings: dict, cam_settings: dict, storage_lock=None):
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
        self._stop_capture = None
        self._save_done = list() # sync finish time between capture and save threads
        self._capture_threads_done = list() # sync finish time between capture threads
        self._cam_settings = cam_settings
        self._man_settings = man_settings
        self._capture_and_copy_lock = list()
        self._save_and_preview_lock = list()
        self._storage_lock = storage_lock or threading.Lock()
        # Free space on the external SSD only changes during a copy, so measure it
        # once per volume and serve the cached figures while unmounted.
        self._ssd_usage_lock = threading.Lock()
        self._ssd_usage = {"id": None, "info": {}, "at": 0.0}
        self._thread_sync_lock = None
        subprocess.run(["timedatectl", "set-ntp", "false"], check=True)
        self._initialise()
        self.mount_disk()

    def _initialise(self):
        try:
            self._find_cameras()
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

    def get_cameras_as_list(self):  # Sort this list
        return self._cameras

    def get_state(self):
        return self.state

    def _find_cameras(self, discovery_attempts=15):
        self._sonySDKInstance, camera_count = discover_sony_cameras(
            create_sony_sdk,
            attempts=discovery_attempts,
            logger=self._logger,
        )
        self._sonySDKCamCaptureLock = threading.Lock()
        discovered_cameras = []

        for camera_id in range(1, camera_count + 1):
            try:
                camera = SonyCamera(
                    SONY_TEMPFS_MOUNT_POINT,
                    self._sonySDKInstance,
                    camera_id,
                    self._sonySDKCamCaptureLock,
                    self.get_sony_image_format(),
                )
                discovered_cameras.append(camera)
            except Exception as exc:
                self._logger.warning(
                    'Sony camera %s could not be initialised: %s',
                    camera_id,
                    exc,
                    exc_info=True,
                )

        if not discovered_cameras:
            raise RuntimeError(
                'Sony cameras were detected, but none could be initialised'
            )

        self._cameras.extend(discovered_cameras)
        self.camera_startup_error = ''

    def start_capturing(self):
        """Start the capturing threads of all connected cams."""
        self._logger.debug(f"Cam manager - current state {self.state}")

        if self.state == CAM_MANAGER_STATES.STARTED and (
                not self.is_capture_thread_alive()
                or not self.is_save_thread_alive()):
            self._logger.debug('Cam manager - waiting for threads to end')
            while self.is_capture_thread_alive() or self.is_save_thread_alive():
                time.sleep(50e-3)
            self.copy_disk_monitor()

        if not self._cameras:
            self.state = CAM_MANAGER_STATES.ERROR_NO_CAMS
            self._logger.debug(
                'Tried to start capture threads with no Sony cameras connected.'
            )
            return

        if self.state == CAM_MANAGER_STATES.STARTED:
            self._stop_capture.clear()
            self._logger.debug('Cam manager - continue capturing thread')
            return

        if self.state != CAM_MANAGER_STATES.STOPPED:
            return

        try:
            if getattr(self, 'altimeter', None) is not None:
                self.altimeter.start_measuring()
        except Exception as exc:
            self._logger.warning('Cam manager - altimeter start failed: %s', exc)

        for camera in self._cameras:
            camera._image_count = 0

        self._logger.debug('Cam manager - start capturing threads')
        self._stop_capture = threading.Event()

        if not self._capture_and_copy_lock:
            self._logger.debug('Cam manager - create thread interlocks')
            self._thread_sync_lock = threading.Lock()
            for _camera in self._cameras:
                self._capture_and_copy_lock.append(threading.Lock())
                self._save_and_preview_lock.append(threading.Lock())
                self._capture_threads_done.append(threading.Event())
                self._save_done.append(threading.Event())

        if not self.mount_disk():
            self._logger.warning(
                'Internal storage is not mounted; Sony capture will continue'
            )

        global_start_time = time.time() + 0.5
        self._copy_start_time = datetime.now()
        existing_files = self.list_exisiting_files(MOUNT_POINT)
        self._capture_threads.clear()
        self._save_threads.clear()

        for index, camera in enumerate(self._cameras):
            self._capture_threads_done[index].clear()
            self._save_done[index].clear()
            self._capture_threads.append(threading.Thread(
                target=camera.capture_and_copy,
                daemon=True,
                args=(
                    MOUNT_POINT,
                    self._image_capture_interval,
                    global_start_time,
                    self._copy_start_time,
                    str(camera.serial_num),
                    self._stop_capture,
                    self._capture_and_copy_lock[index],
                    index,
                    self._capture_threads_done,
                    self._save_done[index],
                    self._thread_sync_lock,
                ),
            ))
            self._save_threads.append(threading.Thread(
                target=camera.save_to_ssd,
                daemon=True,
                args=(
                    MOUNT_POINT,
                    existing_files,
                    str(camera.serial_num),
                    self._capture_and_copy_lock[index],
                    self._save_and_preview_lock[index],
                    self._capture_threads_done,
                    self._save_done[index],
                    self._thread_sync_lock,
                ),
            ))

        for thread in self._capture_threads + self._save_threads:
            thread.start()

        self.state = CAM_MANAGER_STATES.STARTED
        self._logger.debug('Cam manager - capture threads started.')

        threading.Thread(
            target=self._finalise_when_saved,
            daemon=True,
            args=(list(self._save_threads),),
        ).start()

    def stop_capturing(self):
        try:
            if getattr(self, 'altimeter', None) is not None:
                self.altimeter.stop_measuring()
        except Exception as e:
            self._logger.warning(f"Cam manager - altimeter stop failed: {e}")
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
                with self._storage_lock:
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
        """Path of the external SSD's data partition, or None."""
        vol = find_volume()
        return vol.path if vol else None

    SSD_FAILED_MOUNT_RETRY_SEC = 60

    def ssd_usage(self):
        """Capacity/used/free of the external SSD in GB; {} when none is connected."""
        if os.path.ismount(MOUNT_POINT_SSD):
            return self.refresh_ssd_usage()
        vol = find_volume()
        if vol is None:
            with self._ssd_usage_lock:
                self._ssd_usage = {"id": None, "info": {}, "at": 0.0}
            return {}
        with self._ssd_usage_lock:
            cached = self._ssd_usage
            fresh_failure = time.time() - cached["at"] < self.SSD_FAILED_MOUNT_RETRY_SEC
            if cached["id"] == vol.id and (cached["info"] or fresh_failure):
                return dict(cached["info"])
            # New volume: mount once, measure, unmount. A failed mount is remembered
            # briefly so a bad drive is not mount-cycled on every poll.
            info = {}
            if not os.path.ismount(MOUNT_POINT_SSD) and self.mount_ssd():
                try:
                    info = _disk_usage_gb(MOUNT_POINT_SSD)
                finally:
                    self.unmount_disk()
            self._ssd_usage = {"id": vol.id, "info": info, "at": time.time()}
            return dict(info)

    def refresh_ssd_usage(self):
        """Measure the mounted SSD and cache it. Called before unmounting after a copy."""
        try:
            info = _disk_usage_gb(MOUNT_POINT_SSD)
        except OSError:
            return {}
        vol = find_volume()
        with self._ssd_usage_lock:
            self._ssd_usage = {"id": vol.id if vol else None, "info": info, "at": time.time()}
        return dict(info)

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

    def _finalise_when_saved(self, save_threads):
        """Return to STOPPED once every save thread of this capture has exited.

        Nothing else transitions the manager out of STARTED: stop_capturing
        only requests the threads to stop, and the save threads may keep
        copying for a while after that.
        """
        for thread in save_threads:
            thread.join()
        self.copy_disk_monitor()

    def copy_disk_monitor(self):
        """Reset manager and camera state once the save threads have finished."""

        if not self.is_save_thread_alive() and self.state == CAM_MANAGER_STATES.STARTED:
            self._logger.debug("Save completed - unmount disk")
            self.state = CAM_MANAGER_STATES.STOPPED

            # A successful trigger leaves each camera in CAPTURING. Once all
            # capture/save threads have finished, return successful cameras to
            # their ready state without masking a genuine error state.
            for cam in self._cameras:
                if cam.state.name == 'CAPTURING':
                    cam.state = type(cam.state).INITIALISED

    def get_image_capture_interval(self):
        return self._man_settings['image_capture_interval']

    def set_image_capture_interval(self, value):
        self._man_settings['image_capture_interval'] = value
        self._image_capture_interval = value

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
        return CameraSettings(self)

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

        for camera in self._cameras:
            camera.set_image_format(image_format)
        self._cam_settings[SONY_IMAGE_FORMAT_CONFIG_KEY] = image_format

    def copy_eta(self):
        return ""

    def sync_time(self, time_str):
        subprocess.run(["timedatectl", "set-time", time_str], check=True)

        for cam in self._cameras:
            cam.sync_time()

    def start_preview(self):
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
