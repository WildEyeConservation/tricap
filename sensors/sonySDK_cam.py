"""Handler for sony SDK based cameras. Uses this library to handle communication."""

import os
import logging
import threading
import shutil
from PIL import Image
from io import BytesIO
import base64
import signal


from time import sleep, time
from datetime import datetime

import sys
sys.path.append("/home/radxa/tricap")

from config import (
    CAMERA_STATES,
    SONY_IMAGE_FORMAT_CAMERA_SETTING,
    SONY_IMAGE_FORMAT_CHOICES,
    SONY_IMAGE_FORMAT_FILE_TYPES,
    SONY_PC_IMAGE_FORMAT_FILE_TYPES,
)
sys.path.append(os.path.abspath("/home/radxa/SonySDKWrapper"))

import subprocess, tempfile
from pathlib import Path

# noinspection PyUnresolvedReferences
class sonySDKcam():
    """Handler for sony SDK based cameras. Uses this library to handle communication."""

    _logger = logging.getLogger(__name__)
    CONNECT_ATTEMPTS = 10
    CONNECT_POLLS_PER_ATTEMPT = 50
    CONNECT_POLL_INTERVAL_SEC = 0.1
    _lock_with_save = None
    _sonyCamera = None

    def imageDownloadCompleteCallback(self, filename):
        self._logger.debug("Sony camera transfer callback called with "+str(filename, encoding="utf-8"))
        with self._lock_with_save:
                self._downLoadedCount += 1
                self._num_images_copied += 1

    def cameraErrorCallback(self, message):
        self._logger.error("Received an error callback from sony camera SDK "+str(message, encoding="utf-8"))
        raise Exception("Received an error callback from sony camera SDK "+str(message, encoding="utf-8"))

    def exitGracefully(self, *args):
        print("exiting gracefully")
        self._sonyCamera.setOnErrorCallBack(None,self._cameraID)
        del self._sonyCamera
        self._sonyCamera = None
        sys.exit(143)

    def __init__(
            self,
            memoryFsPath,
            sonySDKInstance,
            cameraID,
            capture_lock,
            image_format=SONY_IMAGE_FORMAT_CAMERA_SETTING):
        """Constructor"""
        self._camera = None
        self._image_count = 0
        self._to_save_queue = []
        self._serial_num = "Default_serial_num"
        self._preview_images_big_jpg = []
        self._num_images_copied = 0
        self._num_images_failed = 0
        self._memoryFsPath = memoryFsPath
        self._preview_images = []
        self._im_aspect_ratio = 0
        self._triggers = 0
        self._marginTimers = {}
        self._capture_lock = capture_lock

        self._ensure_memory_fs(memoryFsPath)
        
        # Background rediscovery runs outside Python's main thread, where
        # signal.signal() is not permitted.
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, self.exitGracefully)
        self._sonyCamera = sonySDKInstance
        self._cameraID = cameraID

        self._connect_camera()

        self._sonyCamera.loadProperties(self._cameraID)
        sleep(2)
        # This sets the file chunk size for transferring images from the camera to the PI ram fileSystem. The max seems to be 20Mb chunks, as configured here. 
        # This allows the shutter events sent from the SDK to not be blocked for too long while images are transferred, preventing erratic shutter timing.
        self._sonyCamera.setTransferBufferSize(16,self._cameraID)

        # This instructs the camera to save images to the PC only and not on the SD card.
        self._sonyCamera.setCameraSaveLocation(1,self._cameraID)
        # live view is enabled by default on connection and seems to use USB bandwidth, so toggle it to disable
        self._sonyCamera.toggleLiveView(self._cameraID)

        self.set_image_format(image_format)

        print("Setting download callback")
        self._sonyCamera.setOnDownloadCompleteCallback(self.imageDownloadCompleteCallback,self._cameraID)
        self._sonyCamera.setOnErrorCallBack(self.cameraErrorCallback,self._cameraID)

        self._serial_num = self._sonyCamera.getModel(self._cameraID).replace("-","_")

        # Give the camera a moment to settle before starting to capture images. Prevents the first capture from being missed
        sleep(3)

        self.state = CAMERA_STATES.INITIALISED

    def _ensure_memory_fs(self, memory_fs_path):
        """Create and mount the shared transfer tmpfs exactly once."""
        os.makedirs(memory_fs_path, exist_ok=True)
        if os.path.ismount(memory_fs_path):
            self._logger.debug(
                "Sony transfer tmpfs already mounted at %s", memory_fs_path
            )
            return

        try:
            mount_status = subprocess.run(
                ["mount", "-t", "tmpfs", "tmpfs", memory_fs_path],
                check=True,
            )
            self._logger.debug(mount_status)
        except Exception as exc:
            raise RuntimeError(
                "Failed to mount Sony transfer tmpfs at {}".format(
                    memory_fs_path
                )
            ) from exc

        if not os.path.ismount(memory_fs_path):
            raise RuntimeError(
                "Sony transfer tmpfs is not mounted at {}".format(
                    memory_fs_path
                )
            )

    def _connect_camera(self):
        """Connect with bounded retries instead of waiting forever."""
        for attempt in range(1, self.CONNECT_ATTEMPTS + 1):
            self._sonyCamera.connectCamera(self._cameraID)
            for _ in range(self.CONNECT_POLLS_PER_ATTEMPT):
                if self._sonyCamera.isConnected(self._cameraID):
                    return
                sleep(self.CONNECT_POLL_INTERVAL_SEC)

            # Check once more at the polling boundary before reconnecting.
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
                self._cameraID,
                self.CONNECT_ATTEMPTS,
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

        # StillImageStoreDestination is configured as host-PC only above. Sony
        # exposes the host transfer selection separately from the camera's
        # FileType property, so setting only FileType can fire the shutter
        # without delivering a file to setSaveInfo's destination.
        pc_file_type = SONY_PC_IMAGE_FORMAT_FILE_TYPES[image_format]
        if not self._sonyCamera.setPCFileSaveType(
                pc_file_type, self._cameraID):
            # ILX-LR1 exposes this property as read-only and commonly reports
            # "Raw and JPEG", which already transfers either explicit camera
            # format correctly. Do not discard an otherwise healthy camera.
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

    def is_cam_image_fresh(self):
        """Check if the camera image is new."""
        return False

    def _trigger_capture(self):
        """Make the camera capture an image but don't wait for it to return.

        Return True if successful, or False if failed.
        """
        retval = True
        # We need to send a shutter down, wait a bit, and send a shutter up command to capture an image. 
        # To sync the images up in time as close as possible, do all the shutter downs, wait a bit, and do all the shutter up's
        sonyCommandResult = False
        with self._capture_lock:
            sonyCommandResult = self._sonyCamera.isConnected(self._cameraID) and self._sonyCamera.shutterDown(self._cameraID)
        if(sonyCommandResult):
            retval = retval and True
        else:
            self._logger.warning('Trigger Camera(shutter down) '+str(self._cameraID)+' failed')
            retval = retval and False
        sleep(0.035)
        sonyCommandResult = False
        with self._capture_lock:
            sonyCommandResult = self._sonyCamera.isConnected(self._cameraID) and self._sonyCamera.shutterUp(self._cameraID)
        if(sonyCommandResult):
            retval = retval and True
        else:
            self._logger.warning('Trigger Camera(shutter up) '+str(self._cameraID)+' failed')
            retval = retval and False
        return retval

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
            if not self._sonyCamera.isConnected(self._cameraID):
                raise Exception("Camera "+str(self._cameraID)+" is not connected!")

            if not continuous:
                return

    def test_capture(self):
        """Capture a single image and return its raw bytes and filename."""
        download_done = threading.Event()
        downloaded_name = [None]

        def _on_download(filename):
            downloaded_name[0] = str(filename, encoding="utf-8")
            download_done.set()

        self._sonyCamera.setOnDownloadCompleteCallback(_on_download, self._cameraID)
        temp_dir = tempfile.mkdtemp(dir=self._memoryFsPath)
        try:
            if not self._sonyCamera.setSaveInfo(temp_dir, "test_", 1, self._cameraID):
                raise RuntimeError("Failed to set save location for test capture")

            self._trigger_capture()

            if not download_done.wait(timeout=30):
                raise TimeoutError("Test capture timed out waiting for image download")

            name = Path(downloaded_name[0]).name if downloaded_name[0] else None
            fpath = Path(temp_dir) / name if name else None

            if not fpath or not fpath.exists():
                files = [f for f in Path(temp_dir).iterdir() if f.is_file()]
                if not files:
                    raise RuntimeError("No image file found after test capture")
                fpath = files[0]

            return fpath.read_bytes(), fpath.name
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            self._sonyCamera.setOnDownloadCompleteCallback(
                self.imageDownloadCompleteCallback, self._cameraID
            )

    def capture_and_copy(self, mount_point, interval, init_start, session_start_date, serial_number, stop_capture, lock_with_save, index, capture_done, save_done, sync_lock):
        self._lock_with_save = lock_with_save
        # empty event buffer
        self._logger.debug(f'capture_and_copy {init_start}')
        self._session_start_date = session_start_date
        # local variables
        start = init_start
        self._triggers = 0
        missedCount = 0
        self._marginTimers = {}
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

        self._dest_dir = self.get_im_target_dir(self._session_start_date, mount_point, serial_number)
        if not os.path.isdir(self._dest_dir):
            os.makedirs(self._dest_dir)

        self._logger.info("Set save info CAM"+str(self._cameraID)+" to "+self._memoryFsPath)
        if (not self._sonyCamera.setSaveInfo(self._dest_dir, str(self._cameraID)+"_"+session_start_date.strftime("%d_%m_%Y_%H_%M_%S")+"_", 1,self._cameraID)):
            with sync_lock:
                capture_done[index].set()
            raise Exception("Failed to set the save location. Make sure that the following path exists and has appropriate permissions: " + self._memoryFsPath)

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
                    self._triggers += 1
                    with self._lock_with_save:
                        self._logger.info(str(serial_number)+": Waiting for "+str(self._triggers - self._downLoadedCount )+" images from the camera save queue is: " + str(len(self._to_save_queue)) + " images long.")
                else:
                    self._logger.warning('Could not successfully trigger a capture.')
                    self.state = CAMERA_STATES.ERROR_CAPTURE
                    if not self._sonyCamera.isConnected(self._cameraID):
                        with sync_lock:
                            capture_done[index].set()
                        raise Exception("Camera "+str(self._cameraID)+" is not connected!")
                start += interval
                while start - time() < 0.5:
                    self._logger.warning(f"next capture delayed {start - time()}")
                    start += interval
                    missedCount += 1

            # check if thread is done
            if stop_capture.is_set() and stopTriggerInitiated:
                if self._downLoadedCount + self._num_images_failed >= self._triggers or copyWaitTimeout <=0:
                    # All triggered images have downloaded.

                    if copyWaitTimeout <=0:
                        self._num_images_failed = self._triggers-(self._downLoadedCount+self._num_images_failed)
                        self._logger.warning(str(serial_number)+': failed to download '+str(self._num_images_failed)+ ' images from the camera')
                    isCaptureDoneSet = False
                    with sync_lock:
                        isCaptureDoneSet = capture_done[index].is_set()               
                    if not isCaptureDoneSet:
                        with sync_lock:
                            capture_done[index].set()
                        self._logger.debug('Exit capture thread 2')
                        return
                else:
                    copyWaitTimeout -=1
                    sleep(1)
            


    def save_to_ssd(self, mount_point, computer_files, serial_num, lock_with_copy, lock_with_preview, capture_done, save_done, sync_lock):
        self._logger.debug(f"Save to SSD thread started")

        self._dest_dir = self.get_im_target_dir(self._session_start_date, mount_point, serial_num)

        while True:
            
            fileName = ""
            self._lock_with_save.acquire()
            if(len(self._to_save_queue) > 0):
                fileName = self._to_save_queue.pop(0)
                self._lock_with_save.release()
                print(str(datetime.now())+ " popping file " + fileName)
            else:
                self._lock_with_save.release()
            if fileName == '':
                with lock_with_copy:
                    save_done.set()
                allDone = True
                with sync_lock:
                    for t in capture_done:
                        if not t.is_set():
                            allDone = False            
                if allDone:
                    self._logger.debug('save_to_ssd thread is done')
                    self._logger.debug('Exit save thread')
                    return
                # nothing to save
                sleep(100e-3)                    
            else:
                # save required
                with lock_with_copy:
                    save_done.clear()
                currentFolder, currentFilename = os.path.split(fileName)
                dest = os.path.join(self._dest_dir, currentFilename)
                if not os.path.isdir(self._dest_dir):
                    os.makedirs(self._dest_dir)
                if not os.path.isdir(os.path.join(self._dest_dir,"in_progress")):
                    os.makedirs(os.path.join(self._dest_dir,"in_progress"))

                print(str(datetime.now())+ " Iterate over destination files")
                if dest in computer_files:
                    self._logger.debug('File exists {}'.format(dest))
                    while dest in computer_files:
                        dest = "{0}_{2}.{1}".format(*dest.rsplit(".", 1), "copy")
                    self._logger.debug('Save as _copy {}'.format(dest))

                try:
                    if currentFilename.upper().endswith(".JPG"):
                        with lock_with_preview:
                            preview_count = len(self._preview_images_big_jpg)
                        if preview_count < 3 or self._num_images_copied % 500 == 0:
                            with open(fileName, "rb") as source_file:
                                source_image = source_file.read()
                            with lock_with_preview:
                                if len(self._preview_images_big_jpg) >= 3:
                                    self._preview_images_big_jpg.pop(0)
                                self._preview_images_big_jpg.append(source_image)

                    print(str(datetime.now())+ " start copy")
                    try:
                        copy_status = subprocess.run(["mv", fileName, os.path.join(self._dest_dir,"in_progress",currentFilename)], check=True)
                        copy_status = subprocess.run(["mv", os.path.join(self._dest_dir,"in_progress",currentFilename), dest], check=True)
                        self._logger.debug(copy_status)
                        self._num_images_copied += 1
                    except Exception:
                        print("Failed to copy file, retrying")
                        with self._lock_with_save:
                            self._to_save_queue.append(fileName)
                        continue
                    print(str(datetime.now())+ " copied to "+ dest)
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

    def get_im_target_dir(self, timestamp, mount_point, serial_num):
        session_dir = "{}/{}".format(timestamp.strftime('%Y_%m_%d'), self._session_id)
        complete_dir = os.path.join(mount_point, session_dir, str(serial_num))
        return complete_dir

    def get_preview_image(self, idx):
        if idx >= len(self._preview_images) or self._generating_preview:
            return ''
        return self._preview_images[idx]

    def get_aspect_ratio(self):
        return self._im_aspect_ratio

    def get_live_view_frame(self):
        """Return a single live-view JPEG frame from the Sony SDK, or None on failure.

        Ensures the camera is connected and live view is enabled before requesting
        a frame from the underlying SDK wrapper.
        """
        with self._capture_lock:
            if not self._sonyCamera.isConnected(self._cameraID):
                return None
            if not self._sonyCamera.isLiveViewEnabled(self._cameraID):
                self._sonyCamera.toggleLiveView(self._cameraID)
            return self._sonyCamera.getLiveViewFrame(self._cameraID)

    def sync_time(self):
        self._sonyCamera.setDateTime(round(datetime.now().timestamp()),self._cameraID)

    @property
    def serial_num(self):
        return self._serial_num

    @property
    def captureCount(self):
        return self._image_count

    @property
    def sessionStartDate(self):
        return self._session_start_date
    
    def get_cam_image_count(self):
        """Return the number of images captured by the camera, as tracked by this object."""
        return self._image_count

    def get_cam_copy_count(self):
        """Return the number of images copied from the Raspberry pi memory to the SSD, as tracked by this object."""
        return self._num_images_copied
