"""Camera driver for a generic camera that can be accessed using the libgphoto2
library."""

import os
import logging
import threading
from io import BytesIO
import exifread

from time import sleep
from datetime import datetime

import gphoto2 as gp
from anytree import Node, PreOrderIter, RenderTree

from config import CAMERA_STATES
from .abstract_cam import AbstractCamera, CamConfigType
from .base_setting import BaseSetting

# Max attempts that can be made to trigger a photo during the capture process
MAX_TRIGGER_ATTEMPTS = 5
IMAGE_COUNT_DELTA_FOR_WAIT_FOR_PATH = 10
IMAGE_COUNT_DELTA_FOR_FETCH = 5


class GPhotoSetting(BaseSetting):
    """Setting handler for gphoto cameras."""

    def __init__(self, widget):
        """Constructor."""
        widget.name = widget.get_name()
        super().__init__(widget)

    @property
    def choices(self):
        """Access the choices for a widget as a list."""
        try:
            return [self._widget.get_choice(i) for i in range(self._widget.count_choices())]
        except gp.GPhoto2Error:
            return None


class GPhotoConfig:
    """Configuration handler for gphoto cameras."""

    dictkeys = ["_camera", "_context"]

    def __init__(self, camera, context):
        """Constructor."""
        self._camera = camera
        self._context = context

    def __repr__(self):
        """Represent the configuration settings as a tree."""
        return str(RenderTree(self.get_tree()))

    def __dir__(self):
        """dir."""
        return [node.name for node in PreOrderIter(self.get_tree()) if node.is_leaf]

    def __setattr__(self, key, value):
        """Set a configuration setting to a new value."""
        if key in GPhotoConfig.dictkeys:
            self.__dict__[key] = value
        else:
            config = self._camera.get_config(self._context)
            GPhotoSetting(config.get_child_by_name(key)).set(value)
            self._camera.set_config(config, self._context)

    def __getattr__(self, key):
        """Get a configuration setting from the camera."""
        return GPhotoSetting(self._camera.get_config(self._context).get_child_by_name(key))

    __setitem__ = __setattr__
    __getitem__ = __getattr__

    @staticmethod
    def _get_config(node, parent=None):
        children = [node.get_child(i) for i in range(node.count_children())]
        if len(children):
            thisnode = Node(node.get_name(), parent=parent, label=node.get_label(),
                            type=CamConfigType(node.get_type()))
            for child in children:
                GPhotoConfig._get_config(child, thisnode)
            return thisnode
        else:
            if node.get_type() == CamConfigType.Radio:
                choices = [node.get_choice(i) for i in range(node.count_choices())]
            else:
                choices = None
            return Node(node.get_name(), parent=parent, label=node.get_label(), type=CamConfigType(node.get_type()),
                        value=node.get_value(), choices=choices)

    def get_tree(self):
        """Return the configuration tree."""
        config = self._camera.get_config(self._context)
        return GPhotoConfig._get_config(config)


# noinspection PyUnresolvedReferences
class GPhotoCam(AbstractCamera):
    """Handler for a generic gphoto2 based cameras. Uses this library to handle communication."""

    _port_info_list = gp.PortInfoList()
    _port_info_list.load()
    _context = gp.Context()
    _logger = logging.getLogger(__name__)

    def __init__(self, address, settings: dict):
        """Constructor, requires address and camera settings dict."""
        super().__init__(address, settings)

        self._gp_camera = None
        self.data = None
        self._fresh_capture = False
        self.state = CAMERA_STATES.INITIALISED
        self._address = address

        self._image_count = 0

        self._image_path = None
        self._old_image_count = 0

        self._setup_camera(settings)

    def is_cam_image_fresh(self):
        """Check if the camera image is new."""
        return self._fresh_capture

    @staticmethod
    def autodetect():
        """Run gphoto2 camera autodetection."""
        return GPhotoCam._context.camera_autodetect()

    def _setup_camera(self, settings):
        # In case this is a re-setup. Make sure our previous gp_camera handle gets destroyed.
        if self._gp_camera:
            del self._gp_camera
        self._gp_camera = gp.Camera()
        port_info = GPhotoCam._port_info_list[GPhotoCam._port_info_list.lookup_path(self._address)]
        self._gp_camera.set_port_info(port_info)
        self._gp_camera.init(GPhotoCam._context)
        # Do not catch exceptions here. Camera init is mission critical. If camera initialisation fails, we want top
        # level code to know about it.
        for key, value in settings.items():
            self.config[key] = value
        self.state = CAMERA_STATES.INITIALISED

    @property
    def config(self):
        """Return a GPhotoConfig object for the camera."""
        return GPhotoConfig(self._gp_camera, self._context)

    def _fetch_preview_camera_file(self, file_path: str):
        camera_file = None
        try:
            camera_file = self._gp_camera.file_get(file_path.folder,
                                                   file_path.name,
                                                   gp.GP_FILE_TYPE_PREVIEW,
                                                   GPhotoCam._context)
        except gp.GPhoto2Error:
            self._logger.error('Error retrieving preview, is the capturetarget correctly set?')
            raise

        return camera_file

    def get_current_folder(self):
        """Get the latest folder from the camera."""
        folder = '/'
        done_flag = False
        while done_flag is False:
            cam_folders = self._gp_camera.folder_list_folders(folder, self._context)
            if len(cam_folders) == 0:
                done_flag = True
            else:
                folder += cam_folders[-1][0] + '/'

        return folder

    def calibrate_func(self):
        print('running the calibration function.')
        # get the latest folder and file
        folder = self.get_current_folder()
        print(folder)
        cam_files = self._gp_camera.folder_list_files(folder, self._context)
        fname = cam_files[-1][0]
        print(fname)
        
        # get the exif data from that file
        buf = bytearray(32*1024)
        self._gp_camera.file_read(folder, fname, gp.GP_FILE_TYPE_NORMAL, 0, 
                                  buf)
        bio = BytesIO()
        bio.write(buf)
        bio.seek(0)
        exif_data = exifread.process_file(bio)

        # print the exif data
        print(exif_data)

        # react to it, i.e. use autofocus to correct?

        pass

    def _update_image(self, camera_file):
        file_data = camera_file.get_data_and_size()
        # Make a copy, so that we can release the file_data object
        self.data = memoryview(file_data).tobytes()
        self._fresh_capture = True

    def _run_calibrate_if_needed(self):
        if self.calibrate_func is not None:
            if self.calibrate_step > 0:
                if self._image_count % self.calibrate_step == 0:
                    self.calibrate_func()

    def _wait_for_image_path(self, before_capture_ts=None):
        image_path = None

        event = self._gp_camera.wait_for_event(100, GPhotoCam._context)
        count = 0

        if before_capture_ts is None:
            while event[0] != gp.GP_EVENT_FILE_ADDED and count < 1000:
                sleep(0.01)
                event = self._gp_camera.wait_for_event(100, GPhotoCam._context)
                count += 1
        else:
            while event[0] != gp.GP_EVENT_FILE_ADDED and (datetime.now() - before_capture_ts).total_seconds() < 1.2:
                sleep(0.01)
                event = self._gp_camera.wait_for_event(100, GPhotoCam._context)

        if event[0] == gp.GP_EVENT_FILE_ADDED:
            image_path = event[1]

        return image_path

    def capture_and_download(self, target_folder: str, target_name: str = None):
        """Capture an image and download it."""
        file_path = self._gp_camera.capture(gp.GP_CAPTURE_IMAGE, GPhotoCam._context)
        camera_file = self._gp_camera.file_get(file_path.folder,
                                               file_path.name,
                                               gp.GP_FILE_TYPE_NORMAL,
                                               GPhotoCam._context)
        if target_name is None:
            target_name = file_path.name

        target_fp = os.path.join(target_folder, target_name)

        gp.gp_file_save(camera_file, target_fp)

        return target_fp

    def _trigger_capture(self):
        """Make the camera capture an image but don't wait for it to return.

        If a gphoto2 exception is triggered, try up to MAX_TRIGGER_ATTEMPTS again.

        Return True if successful, or False if too many exceptions were caused.
        """
        trigger_attempts = 0
        while trigger_attempts < MAX_TRIGGER_ATTEMPTS:
            try:
                # file_path = self._gp_camera.capture(gp.GP_CAPTURE_IMAGE, GPhotoCam._context)
                self._gp_camera.trigger_capture(GPhotoCam._context)
                return True
            except gp.GPhoto2Error as ex:
                self._logger.warning('Exception when trying to trigger a capture: %s', ex)
                trigger_attempts += 1

        return False

    def capture(self, continuous=False, barrier: threading.Barrier = None, stop_event=None):
        """Start capturing photos, typically called by a thread."""
        self.state = CAMERA_STATES.INITIALISED
        while True:
            if stop_event and stop_event.is_set():
                    return
            if barrier:
                barrier.wait()

            self.update_message = 'before capture'
            self.notify()
            before_capture_ts = datetime.now()

            if self._trigger_capture():  # Checks to see if something went wrong with the cameras
                self._image_count += 1
                self.state = CAMERA_STATES.CAPTURING
            else:
                self._logger.error('Could not successfully trigger a capture.')
                self.state = CAMERA_STATES.ERROR_CAPTURE

            if self.fetch_state:
                # check if we need to get a new image path
                if self._image_path is None or self._image_count - self._old_image_count >= IMAGE_COUNT_DELTA_FOR_WAIT_FOR_PATH:
                    self._image_path = self._wait_for_image_path(before_capture_ts)
                    if self._image_path:
                        self._old_image_count = self._image_count

                self.update_message = 'before preview fetch'
                self.notify()

                # check if we need to fetch the image from the camera
                camera_file = None
                if self._image_path and self._image_count - self._old_image_count == IMAGE_COUNT_DELTA_FOR_FETCH:
                    camera_file = self._fetch_preview_camera_file(self._image_path)

                self.update_message = 'after preview fetch'
                self.notify()

                if camera_file:
                    self._update_image(camera_file)
                    del camera_file
            else:
                # update the timing info
                self.update_message = 'before preview fetch'
                self.notify()
                self.update_message = 'after preview fetch'
                self.notify()

            self._run_calibrate_if_needed()

            if not continuous:
                return self.data

    # def reset(self, settings: dict):
    #     """Reset the camera."""
    #     self.state = CAMERA_STATES.UNINITIALISED
    #     self._setup_camera(settings)

    def get_state_as_string(self):
        """Return the state of the camera as a string."""
        return self.state.name

    def get_cam_image_count(self):
        """Return the number of images captured by the camera, as tracked by this object."""
        return self._image_count

    def get_cam_context(self):
        return GPhotoCam._context

    def get_cam(self):
        return self._gp_camera
