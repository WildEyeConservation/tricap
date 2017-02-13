# coding=utf-8
import logging
import threading
import os

from time import sleep

import gphoto2 as gp
from anytree import Node, PreOrderIter, RenderTree
from datetime import datetime

from config import CAMERA_STATES, SERVER_LOG_DIR
from .abstract_cam import AbstractCamera, CamConfigType
from .base_setting import BaseSetting


class GPhotoSetting(BaseSetting):
    def __init__(self, widget):
        widget.name = widget.get_name()
        super().__init__(widget)

    @property
    def choices(self):
        try:
            return [self._widget.get_choice(i) for i in range(self._widget.count_choices())]
        except gp.GPhoto2Error:
            return None


class GPhotoConfig:
    dictkeys = ["_camera", "_context"]

    def __init__(self, camera, context):
        self._camera = camera
        self._context = context

    def __repr__(self):
        return str(RenderTree(self.get_tree()))

    def __dir__(self):
        return [node.name for node in PreOrderIter(self.get_tree()) if node.is_leaf]

    def __setattr__(self, key, value):
        if key in GPhotoConfig.dictkeys:
            self.__dict__[key] = value
        else:
            config = self._camera.get_config(self._context)
            GPhotoSetting(config.get_child_by_name(key)).set(value)
            self._camera.set_config(config, self._context)

    def __getattr__(self, key):
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

        self._setup_camera(settings)

    def is_cam_image_fresh(self):
        return self._fresh_capture

    @staticmethod
    def autodetect():
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
        return GPhotoConfig(self._gp_camera, self._context)

    def capture(self, continuous=False, barrier: threading.Barrier = None, stop_event=None):
        """Start capturing photos, typically called by a thread."""
        while True:
            if stop_event:
                if stop_event.is_set():
                    return

            self.state = CAMERA_STATES.CAPTURING
            if barrier:
                barrier.wait()

            triggered = False
            file_path = None

            # timing point
            self.update_message = 'before capture'
            self.notify()
            before_capture_ts = datetime.now()
            while not triggered:
                try:
                    # file_path = self._gp_camera.capture(gp.GP_CAPTURE_IMAGE, GPhotoCam._context)
                    self._gp_camera.trigger_capture(GPhotoCam._context)
                    event = self._gp_camera.wait_for_event(100, GPhotoCam._context)
                    count = 0
                    while event[0] != gp.GP_EVENT_FILE_ADDED and count < 1000 and self._image_count % 5 == 0:
                        sleep(0.01)
                        event = self._gp_camera.wait_for_event(100, GPhotoCam._context)
                        count += 1

                    if event[0] == gp.GP_EVENT_FILE_ADDED:
                        file_path = event[1]

                    triggered = True
                except gp.GPhoto2Error:
                    pass

            if (datetime.now() - before_capture_ts).total_seconds() > 1.5:
                file_path = None

            # Timing point
            self.update_message = 'before preview fetch'
            self.notify()

            camera_file = None
            try:
                if file_path is not None:
                    camera_file = self._gp_camera.file_get(file_path.folder, file_path.name,
                                                           gp.GP_FILE_TYPE_PREVIEW,
                                                           GPhotoCam._context)
            except gp.GPhoto2Error:
                self._logger.error('Error retrieving preview, is the capturetarget correctly set?')
                raise

            self.update_message = 'after preview fetch'
            self.notify()
            if camera_file is not None:
                file_data = camera_file.get_data_and_size()
                # Make a copy, so that we can release the file_data object
                self.data = memoryview(file_data).tobytes()
                self._fresh_capture = True
                del camera_file

            self._image_count += 1
            self.state = CAMERA_STATES.INITIALISED

            if self.calibrate_func is not None:
                if self.calibrate_step > 0:
                    if self._image_count % self.calibrate_step == 0:
                        self.calibrate_func()

            if not continuous:
                return self.data

    def reset(self, settings: dict):
        self.state = CAMERA_STATES.UNINITIALISED
        self._setup_camera(settings)

    def get_state_as_string(self):
        return self.state.name

    def get_cam_image_count(self):
        return self._image_count
