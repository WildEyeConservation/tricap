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
    MOUNT_POINT_SSD,
    SONY_IMAGE_FORMAT_CAMERA_SETTING,
    SONY_IMAGE_FORMAT_CHOICES,
    SONY_IMAGE_FORMAT_CONFIG_KEY,
)

from support.ssd_volume import find_volume

from .sony_discovery import discover_sony_cameras
from .sonySDK_cam import sonySDKcam as SonyCamera


CAPTURE_ACTIVE_MARKER = '/run/skyseeker-capture-active'


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


class TriCapCamsManager:
    """TriCapCamsManager manages TriCap camera objects"""

    _logger = logging.getLogger(__name__)

    def __init__(self, man_settings: dict, cam_settings: dict, storage_lock=None):
        """Construct."""
        self.state = CAM_MANAGER_STATES.STOPPED

        self._copy_start_time = None
        self._capture_threads = list()
        # Keep this list object for the lifetime of the manager. Other startup
        # components retain a reference to it.
        self._cameras = []
        self.camera_startup_error = ''
        self._stop_capture = None
        self._capture_threads_done = list() # sync finish time between capture threads
        self._cam_settings = cam_settings
        self._man_settings = man_settings
        self._camera_count_locks = list()
        self._storage_lock = storage_lock or threading.Lock()
        # Free space on the external SSD only changes during a copy, so measure it
        # once per volume and serve the cached figures while unmounted.
        self._ssd_usage_lock = threading.Lock()
        self._ssd_usage = {"id": None, "info": {}, "at": 0.0}
        # Names of backup/verify jobs currently using the external SSD. While
        # any is present the SSD must not be unmounted or mount-cycled.
        self._external_jobs_lock = threading.Lock()
        self._external_storage_jobs = set()
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

    def get_cameras_as_list(self):  # Sort this list
        return self._cameras

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

        if not self._cameras:
            self.state = CAM_MANAGER_STATES.ERROR_NO_CAMS
            self._logger.debug(
                'Tried to start capture threads with no Sony cameras connected.'
            )
            return

        if self.state != CAM_MANAGER_STATES.STOPPED:
            return

        try:
            if getattr(self, 'altimeter', None) is not None:
                self.altimeter.start_measuring()
        except Exception as exc:
            self._logger.warning('Cam manager - altimeter start failed: %s', exc)

        for camera in self._cameras:
            camera.reset_session_counters()

        self._logger.debug('Cam manager - start capturing threads')
        self._stop_capture = threading.Event()

        if not self._camera_count_locks:
            self._logger.debug('Cam manager - create thread interlocks')
            self._thread_sync_lock = threading.Lock()
            for _camera in self._cameras:
                self._camera_count_locks.append(threading.Lock())
                self._capture_threads_done.append(threading.Event())

        if not self.mount_disk():
            self._logger.warning(
                'Internal storage is not mounted; Sony capture will continue'
            )

        global_start_time = time.monotonic() + 0.5
        self._copy_start_time = datetime.now()
        self._capture_threads.clear()

        for index, camera in enumerate(self._cameras):
            self._capture_threads_done[index].clear()
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
                    self._camera_count_locks[index],
                    index,
                    self._capture_threads_done,
                    self._thread_sync_lock,
                ),
            ))

        self.state = CAM_MANAGER_STATES.STARTED
        self._mark_capture_active()
        for thread in self._capture_threads:
            thread.start()

        self._logger.debug('Cam manager - capture threads started.')

        threading.Thread(
            target=self._finalise_when_capture_threads_exit,
            daemon=True,
            args=(list(self._capture_threads),),
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

    def shutdown(self):
        """Stop capture and release every camera within a bounded interval."""
        self.stop_capturing()
        deadline = time.monotonic() + 25
        while self.is_capture_thread_alive() and time.monotonic() < deadline:
            time.sleep(0.1)
        if self.is_capture_thread_alive():
            self._logger.warning('Capture threads did not stop before shutdown timeout')
        else:
            self._clear_capture_marker()
        for camera in self._cameras:
            camera.release()

    def _mark_capture_active(self):
        '''Create the advisory marker used to defer AP recovery.'''
        try:
            with open(CAPTURE_ACTIVE_MARKER, 'w', encoding='utf-8') as marker:
                marker.write(self._copy_start_time.isoformat())
        except OSError as exc:
            self._logger.warning('Could not create capture-active marker: %s', exc)

    def _clear_capture_marker(self):
        '''Remove the advisory capture marker when capture has stopped.'''
        try:
            os.remove(CAPTURE_ACTIVE_MARKER)
        except FileNotFoundError:
            pass
        except OSError as exc:
            self._logger.warning('Could not remove capture-active marker: %s', exc)

    def is_capture_thread_alive(self):
        """ Return true if any cam thread is alive """
        for t in self._capture_threads:
            if t.is_alive():
                return True
        return False

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

    def claim_external_storage(self, job):
        with self._external_jobs_lock:
            self._external_storage_jobs.add(job)

    def release_external_storage(self, job):
        with self._external_jobs_lock:
            self._external_storage_jobs.discard(job)

    def external_ssd_device(self):
        """Path of the external SSD's data partition, or None."""
        vol = find_volume()
        return vol.path if vol else None

    SSD_FAILED_MOUNT_RETRY_SEC = 60

    def ssd_usage(self):
        """Capacity/used/free of the external SSD in GB; {} when none is connected."""
        with self._external_jobs_lock:
            in_use = bool(self._external_storage_jobs)
        if in_use:
            with self._ssd_usage_lock:
                return dict(self._ssd_usage["info"])
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
        with self._external_jobs_lock:
            if self._external_storage_jobs:
                self._logger.warning(
                    "Refusing to unmount external storage while in use by %s",
                    sorted(self._external_storage_jobs),
                )
                return False
            if os.path.ismount(MOUNT_POINT_SSD):
                try:
                    mount_status = subprocess.run(["umount", MOUNT_POINT_SSD], check=True)
                    self._logger.debug(mount_status)
                except (OSError, subprocess.SubprocessError) as exc:
                    self._logger.warning("Failed to umount: %s", exc)
                    return False
            else:
                self._logger.info('Disk not mounted')
        return True

    def _finalise_when_capture_threads_exit(self, capture_threads):
        """Return to STOPPED once every capture thread has exited."""
        for thread in capture_threads:
            thread.join()
        self._reset_after_capture()

    def _reset_after_capture(self):
        """Reset manager and successful cameras after capture completes."""
        if (not self.is_capture_thread_alive()
                and self.state == CAM_MANAGER_STATES.STARTED):
            self._logger.debug("Capture completed")
            self.state = CAM_MANAGER_STATES.STOPPED
            self._clear_capture_marker()

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

    def sync_time(self, time_str):
        subprocess.run(["timedatectl", "set-time", time_str], check=True)

        for cam in self._cameras:
            cam.sync_time()
