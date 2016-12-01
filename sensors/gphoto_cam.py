# coding=utf-8
import logging
import threading

import gphoto2 as gp

from config import CAMERA_STATES
from config import CE6D_CAP_TARGET_SD_CARD, CE6D_FORMAT_RAW
from .configure import TricapConfig
from anytree import Node
from .abstract_cam import CamConfigType

# noinspection PyUnresolvedReferences
class GPhotoCam(object):
    """ Handler for the Canon EOS 6D Camera. Uses gphoto2 to handle the actual communication. """

    _port_info_list = gp.PortInfoList()
    _port_info_list.load()
    _context = gp.Context()
    _logger = logging.getLogger(__name__)

    def __init__(self, address):

        self._gp_camera = None

        self.state = CAMERA_STATES.UNINITIALISED
        self._address = address
        self._setup_camera()
        self._fresh_capture = False
        self._download_fp = None
        self.data = None

        if self.state == CAMERA_STATES.INITIALISED:
            self._logger.info('GPhoto Camera %s at address %s successfully initialised'
                              % (self.serial_num, address))

    def is_cam_image_fresh(self):
        return self._fresh_capture

    def get_cam_image_fp(self):
        self._fresh_capture = False
        return self._download_fp

    @staticmethod
    def autodetect():
        return GPhotoCam._context.camera_autodetect()

    def _setup_camera(self):
        # In case this is a re-setup. Make sure our previous gp_camera handle gets destroyed.
        if self._gp_camera:
            del self._gp_camera
        self._gp_camera = gp.Camera()
        port_info = GPhotoCam._port_info_list[GPhotoCam._port_info_list.lookup_path(self._address)]
        self._gp_camera.set_port_info(port_info)
        self._gp_camera.init(GPhotoCam._context)
        # Do not catch exceptions here. Camera init is mission critical. If camera initialisation fails, we want top
        # level code to know about it.
        init_configs = TricapConfig()

        # get configuration tree
        gp_config = self._gp_camera.get_config(GPhotoCam._context)
        # Set the Hard Coded Values
        self._set_config_value(gp_config, 'capturetarget', CE6D_CAP_TARGET_SD_CARD)
        self._set_config_value(gp_config, 'imageformat', CE6D_FORMAT_RAW)

        # Read the camera values from the initial.cfg file
        section_dict = init_configs.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
        for key in section_dict:
            self._set_config_value_by_string(gp_config, key, section_dict[key])

        self.state = CAMERA_STATES.INITIALISED
        self._obtain_serial_num(gp_config)

    def get_config_tree(self):
        return GPhotoCam._get_config(self._gp_camera.get_config(GPhotoCam._context))

    @staticmethod
    def _get_config(node, parent=None):
        children = [node.get_child(i) for i in range(node.count_children())]
        if len(children):
            thisnode = Node(node.get_name(), parent=parent, label=node.get_label(), type=CamConfigType(node.get_type()))
            for child in children:
                GPhotoCam._get_config(child, thisnode)
            return thisnode
        else:
            if (node.get_type() == CamConfigType.Radio):
                choices = [node.get_choice(i) for i in range(node.count_choices())]
            else:
                choices = None
            return Node(node.get_name(), parent=parent, label=node.get_label(), type=CamConfigType(node.get_type()),
                        value=node.get_value(), choices=choices)

    # TODO The naming convention for configs and settings is a mess. Sort it out
    def _get_list_of_valid_config_names(self, config):
        config_names = []
        for child in [config.get_child(index) for index in range(config.count_children())]:
            config_name = child.get_name()
            if config_name:
                config_names.append(config_name)
            grandchildren_names = self._get_list_of_valid_config_names(child)
            config_names += grandchildren_names
        return config_names

    def _get_list_of_valid_config_choices(self, config, config_str):
        config_choices = []
        config_widget = config.get_child_by_name(config_str)
        for choice in [config_widget.get_choice(i) for i in range(config_widget.count_choices())]:
            if choice:
                config_choices.append(choice)
        return config_choices

    def _set_config_value_by_string(self, config, config_str, val_str):
        valid_choices = self._get_list_of_valid_config_choices(config, config_str)
        self._set_config_value(config, config_str, valid_choices.index(val_str))

    def _set_config_value(self, config, config_str, config_value):
        # find the capture target config item
        config_widget = config.get_child_by_name(config_str)
        # get the value bit
        value = config_widget.get_choice(config_value)
        # set the value
        config_widget.set_value(value)
        # set the widget back to the config tree
        self._gp_camera.set_config(config, GPhotoCam._context)
        self._logger.debug('Successfully set %s on camera.' % config_str)

    def _get_config_value(self, config_str):
        return self._gp_camera.get_config(GPhotoCam._context).get_child_by_name(config_str).get_value()

    # TODO : make serial number a read-only property
    def _obtain_serial_num(self, config):
        self.serial_num = config.get_child_by_name('eosserialnumber').get_value()
        self._logger.info('Successfully retrieved camera serial number %s' % self.serial_num)

    def reset(self):
        self.state = CAMERA_STATES.UNINITIALISED
        self._setup_camera()

    def set_setting(self, setting_str, val_str):
        config = self._gp_camera.get_config(GPhotoCam._context)
        self._set_config_value_by_string(config, setting_str, val_str)

    def get_setting(self, setting_str):
        """ This external method is used to get settings from the Cannon EOS 6D using gphoto2. If
            the setting does not exist, then the method returns None. The underlying
            self._get_config_value records an error though. """
        return self._get_config_value(setting_str)

    def get_choices_for_setting(self, config_str):
        """ External method for getting the choices. If there are any errors (like the config does
        not exist or there are its not a radio type config) then return None """

        choices = None

        config = self._gp_camera.get_config(GPhotoCam._context)
        valid_config_names = self._get_list_of_valid_config_names(config)
        if valid_config_names is not None and len(valid_config_names) > 0:
            if config_str in valid_config_names:
                choices = self._get_list_of_valid_config_choices(config, config_str)

        return choices

    def capture(self, continuous=False, barrier: threading.Barrier = None):
        while True:
            self.state = CAMERA_STATES.CAPTURING
            if barrier:
                barrier.wait()
            file_path = self._gp_camera.capture(gp.GP_CAPTURE_IMAGE, GPhotoCam._context)
            camera_file = self._gp_camera.file_get(file_path.folder, file_path.name, gp.GP_FILE_TYPE_PREVIEW,
                                                   GPhotoCam._context)
            file_data = camera_file.get_data_and_size()
            # # Make a copy, so that we can release the file_data object
            self.data = memoryview(file_data).tobytes()
            self._fresh_capture = True
            del camera_file
            self.state = CAMERA_STATES.INITIALISED
            if not continuous:
                return self.data

    def get_state_as_string(self):
        return self.state.name
