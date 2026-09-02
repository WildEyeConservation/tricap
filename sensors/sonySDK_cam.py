"""Handler for Sony SDK based cameras."""

import logging
import os
import threading
import time
from datetime import datetime
from time import sleep

from config import (
    CAMERA_STATES,
    SONY_IMAGE_FORMAT_CAMERA_SETTING,
    SONY_IMAGE_FORMAT_CHOICES,
    SONY_IMAGE_FORMAT_FILE_TYPES,
    SONY_PC_IMAGE_FORMAT_FILE_TYPES,
)


class sonySDKcam:
    """Handle communication with one Sony SDK camera."""

    _logger = logging.getLogger(__name__)
    CONNECT_ATTEMPTS = 10
    CONNECT_POLLS_PER_ATTEMPT = 50
    CONNECT_POLL_INTERVAL_SEC = 0.1

    def imageDownloadCompleteCallback(self, filename):
        name = (
            filename.decode("utf-8", errors="replace")
            if isinstance(filename, bytes)
            else str(filename)
        )
        self._logger.debug("Sony camera transfer callback called with %s", name)
        with self._count_lock:
            self._downLoadedCount += 1
            self._num_images_copied += 1

    def cameraErrorCallback(self, message):
        message = (
            message.decode("utf-8", errors="replace")
            if isinstance(message, bytes)
            else str(message)
        )
        self.last_error = message
        self.state = CAMERA_STATES.ERROR_CAPTURE
        self._logger.error(
            "Received an error callback from Sony camera SDK: %s", message
        )

    def __init__(
            self,
            sonySDKInstance,
            cameraID,
            capture_lock,
            image_format=SONY_IMAGE_FORMAT_CAMERA_SETTING):
        self._image_count = 0
        self._serial_num = "Default_serial_num"
        self._num_images_copied = 0
        self._num_images_failed = 0
        self._downLoadedCount = 0
        self._triggers = 0
        self._capture_lock = capture_lock
        self._count_lock = threading.Lock()
        self.last_error = None

        self._sonyCamera = sonySDKInstance
        self._cameraID = cameraID

        self._connect_camera()
        self._sonyCamera.loadProperties(self._cameraID)
        sleep(2)
        # Smaller chunks keep SDK transfers from blocking shutter commands.
        self._sonyCamera.setTransferBufferSize(16, self._cameraID)
        self._sonyCamera.setCameraSaveLocation(1, self._cameraID)
        # Live view consumes USB bandwidth and is not used during capture.
        self._sonyCamera.toggleLiveView(self._cameraID)
        self.set_image_format(image_format)

        self._logger.debug("Setting Sony download callback")
        self._sonyCamera.setOnDownloadCompleteCallback(
            self.imageDownloadCompleteCallback, self._cameraID
        )
        self._sonyCamera.setOnErrorCallBack(
            self.cameraErrorCallback, self._cameraID
        )
        self._serial_num = self._sonyCamera.getModel(self._cameraID).replace(
            "-", "_"
        )

        # Prevent the first capture from being missed while the camera settles.
        sleep(3)
        self.state = CAMERA_STATES.INITIALISED

    def release(self):
        """Detach SDK callbacks without allowing cleanup errors to escape."""
        for callback_name in (
                "setOnErrorCallBack", "setOnDownloadCompleteCallback"):
            try:
                callback = getattr(self._sonyCamera, callback_name)
                callback(None, self._cameraID)
            except Exception as exc:
                self._logger.debug(
                    "Failed to release Sony camera %s callback: %s",
                    self._cameraID,
                    exc,
                )

    def _connect_camera(self):
        """Connect with bounded retries instead of waiting forever."""
        for attempt in range(1, self.CONNECT_ATTEMPTS + 1):
            self._sonyCamera.connectCamera(self._cameraID)
            for _ in range(self.CONNECT_POLLS_PER_ATTEMPT):
                if self._sonyCamera.isConnected(self._cameraID):
                    return
                sleep(self.CONNECT_POLL_INTERVAL_SEC)

            if self._sonyCamera.isConnected(self._cameraID):
                return
            self._logger.warning(
                "Camera %s connection attempt %s/%s timed out",
                self._cameraID,
                attempt,
                self.CONNECT_ATTEMPTS,
            )
            self._sonyCamera.disconnect(self._cameraID)

        raise RuntimeError(
            "Sony camera {} connection timed out after {} attempts".format(
                self._cameraID, self.CONNECT_ATTEMPTS
            )
        )

    def set_image_format(self, image_format):
        """Set the camera format and its corresponding PC transfer format."""
        if image_format not in SONY_IMAGE_FORMAT_CHOICES:
            raise ValueError(
                "Unsupported Sony image format {!r}; expected one of {}".format(
                    image_format, SONY_IMAGE_FORMAT_CHOICES
                )
            )

        if image_format != SONY_IMAGE_FORMAT_CAMERA_SETTING:
            file_type = SONY_IMAGE_FORMAT_FILE_TYPES[image_format]
            if not self._sonyCamera.setCameraFileSaveType(
                    file_type, self._cameraID):
                raise RuntimeError(
                    "Failed to set camera {} image format to {}".format(
                        self._cameraID, image_format
                    )
                )
            self._logger.info(
                "Camera %s image format set to %s",
                self._cameraID,
                image_format,
            )
        else:
            self._logger.info(
                "Camera %s image format left unchanged", self._cameraID
            )

        # Sony exposes host transfer selection separately from FileType.
        pc_file_type = SONY_PC_IMAGE_FORMAT_FILE_TYPES[image_format]
        if not self._sonyCamera.setPCFileSaveType(
                pc_file_type, self._cameraID):
            # ILX-LR1 commonly exposes this property as read-only while still
            # transferring the explicitly selected format correctly.
            self._logger.warning(
                "Camera %s PC transfer format is not writable; retaining "
                "the camera's existing transfer selection",
                self._cameraID,
            )
        else:
            self._logger.info(
                "Camera %s PC transfer format set to %s",
                self._cameraID,
                image_format,
            )

    def _trigger_capture(self):
        """Trigger the shutter without waiting for the image transfer."""
        with self._capture_lock:
            shutter_down = (
                self._sonyCamera.isConnected(self._cameraID)
                and self._sonyCamera.shutterDown(self._cameraID)
            )
        if not shutter_down:
            self._logger.warning(
                "Trigger Camera(shutter down) %s failed", self._cameraID
            )

        sleep(0.035)
        with self._capture_lock:
            shutter_up = (
                self._sonyCamera.isConnected(self._cameraID)
                and self._sonyCamera.shutterUp(self._cameraID)
            )
        if not shutter_up:
            self._logger.warning(
                "Trigger Camera(shutter up) %s failed", self._cameraID
            )
        return bool(shutter_down and shutter_up)

    def capture_and_copy(
            self,
            mount_point,
            interval,
            init_start,
            session_start_date,
            serial_number,
            stop_capture,
            count_lock,
            index,
            capture_done,
            sync_lock):
        self._count_lock = count_lock
        self._logger.debug("capture_and_copy %s", init_start)
        self._session_start_date = session_start_date
        start = init_start
        self._triggers = 0
        with self._count_lock:
            self._downLoadedCount = 0
            self._num_images_copied = 0
        self._session_id = session_start_date.strftime("%H_%M_%S")
        self._logger.debug("_session_id %s", self._session_id)
        self._num_images_failed = 0
        self._image_count = 0

        self._dest_dir = self.get_im_target_dir(
            self._session_start_date, mount_point, serial_number
        )
        os.makedirs(self._dest_dir, exist_ok=True)

        self._logger.info(
            "Set save info CAM%s to %s", self._cameraID, self._dest_dir
        )
        if not self._sonyCamera.setSaveInfo(
                self._dest_dir,
                "{}_{}_".format(
                    self._cameraID,
                    session_start_date.strftime("%d_%m_%Y_%H_%M_%S"),
                ),
                1,
                self._cameraID):
            with sync_lock:
                capture_done[index].set()
            raise RuntimeError(
                "Failed to set the save location. Make sure that the following "
                "path exists and has appropriate permissions: {}".format(
                    self._dest_dir
                )
            )

        sleep(1)
        download_wait_attempts = 20

        try:
            self._capture_loop(
                interval, start, serial_number, stop_capture, index,
                capture_done, sync_lock, download_wait_attempts)
        except Exception as exc:
            # An SDK call that raises must not leave the camera looking healthy
            # or the session waiting on a thread that is already gone.
            self.last_error = str(exc)
            self.state = CAMERA_STATES.ERROR_CAPTURE
            with sync_lock:
                capture_done[index].set()
            raise

    def _capture_loop(self, interval, start, serial_number, stop_capture,
                      index, capture_done, sync_lock, download_wait_attempts):
        stop_trigger_initiated = False
        while True:
            if stop_capture.is_set() and not stop_trigger_initiated:
                stop_trigger_initiated = True
                with sync_lock:
                    capture_done[index].clear()

            if time.monotonic() > start and not stop_capture.is_set():
                if self._trigger_capture():
                    self._image_count += 1
                    self.state = CAMERA_STATES.CAPTURING
                    self._triggers += 1
                    with self._count_lock:
                        waiting = self._triggers - self._downLoadedCount
                    self._logger.info(
                        "%s: waiting for %s images from the camera",
                        serial_number,
                        waiting,
                    )
                else:
                    self._logger.warning(
                        "Could not successfully trigger a capture."
                    )
                    self.state = CAMERA_STATES.ERROR_CAPTURE
                    if not self._sonyCamera.isConnected(self._cameraID):
                        with sync_lock:
                            capture_done[index].set()
                        raise RuntimeError(
                            "Camera {} is not connected!".format(
                                self._cameraID
                            )
                        )

                start += interval
                skipped_slots = 0
                while start - time.monotonic() < 0.5:
                    start += interval
                    skipped_slots += 1
                if skipped_slots:
                    self._logger.warning(
                        "%s: skipped %s delayed capture slot(s)",
                        serial_number,
                        skipped_slots,
                    )

            if stop_capture.is_set() and stop_trigger_initiated:
                with self._count_lock:
                    downloads_complete = (
                        self._downLoadedCount + self._num_images_failed
                        >= self._triggers
                    )
                if downloads_complete or download_wait_attempts <= 0:
                    if download_wait_attempts <= 0:
                        with self._count_lock:
                            self._num_images_failed = max(
                                0, self._triggers - self._downLoadedCount
                            )
                        self._logger.warning(
                            "%s: failed to download %s images from the camera",
                            serial_number,
                            self._num_images_failed,
                        )
                    with sync_lock:
                        if not capture_done[index].is_set():
                            capture_done[index].set()
                    self._logger.debug("Exit capture thread")
                    return

                download_wait_attempts -= 1
                sleep(1)
            else:
                # Poll the schedule without pinning a core between triggers.
                sleep(0.005)

    def get_state_as_string(self):
        """Return the state of the camera as a string."""
        return self.state.name

    def get_im_target_dir(self, timestamp, mount_point, serial_num):
        session_dir = "{}/{}".format(
            timestamp.strftime("%Y_%m_%d"), self._session_id
        )
        return os.path.join(mount_point, session_dir, str(serial_num))

    def sync_time(self):
        self._sonyCamera.setDateTime(
            round(datetime.now().timestamp()), self._cameraID
        )

    @property
    def serial_num(self):
        return self._serial_num

    def reset_session_counters(self):
        self._image_count = 0
        self._num_images_failed = 0
        self._triggers = 0
        with self._count_lock:
            self._downLoadedCount = 0
            self._num_images_copied = 0

    def get_cam_image_count(self):
        """Return the number of images captured in this session."""
        return self._image_count

    def get_cam_copy_count(self):
        """Return the number of images downloaded in this session."""
        with self._count_lock:
            return self._num_images_copied
