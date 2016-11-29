# coding=utf-8
import os
import traceback

from config import CAM_IMAGE_PREFIX, CAM_STATE_STRINGS, RET_ERROR, RET_OK, CAMERA_STATES
from config import CE6D_CAP_TARGET_SD_CARD, CE6D_FORMAT_RAW_AND_TINY_JPEG, DISPLAY_DOWNLOAD_DIR
from .configure import TricapConfig

# TODO currently, we are coding in a mess of C vs C++ styles. Fix this.

try:
    import gphoto2 as gp

    class GPhotoCam(object):
        """ Handler for the Canon EOS 6D Camera. Uses gphoto2 to handle the actual communication. """

        _port_info_list = gp.PortInfoList()
        _port_info_list.load()
        _context = gp.Context()

        def __init__(self, address, logger):

            self._gp_camera = None

            self._logger = logger
            self.state = CAMERA_STATES.UNINITIALISED
            self._address = address
            self._initialise_camera()
            self._fresh_capture = False
            self._download_fp = None

            if self.state == CAMERA_STATES.INITIALISED:
                self._logger.info('GPhoto Camera %s at address %s successfully initialised'
                                  % (self.serial_num, address))
            else:
                self._logger.error('GPhoto Camera not successfully initialised')

        def is_cam_image_fresh(self):
            return self._fresh_capture

        def get_cam_image_fp(self):
            self._fresh_capture = False
            return self._download_fp

        @staticmethod
        def autodetect():
            return GPhotoCam._context.camera_autodetect()

        def _setup_camera(self, address):
            self._gp_camera = gp.Camera()
            try:
                port_info = GPhotoCam._port_info_list[GPhotoCam._port_info_list.lookup_path(address)]
                self._gp_camera.set_port_info(port_info)
                self._gp_camera.init(GPhotoCam._context)
            except gp.GPhoto2Error as ex:
                self._logger.error('GPhoto2 error: %d: %s' % (ex.code, ex.string))
                return RET_ERROR
            except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
                self._logger.error(traceback.format_exc())
                return RET_ERROR

            init_configs = TricapConfig(self._logger)

            # get configuration tree
            gp_config = gp.check_result(gp.gp_camera_get_config(self._gp_camera, GPhotoCam._context))

            ret_val = 0
            ret_val += self._set_config_value(gp_config, 'capturetarget', CE6D_CAP_TARGET_SD_CARD)
            ret_val += self._set_config_value_by_string(gp_config, 'shutterspeed',
                                                        init_configs.get('shutterspeed'))
            ret_val += self._set_config_value_by_string(gp_config, 'iso', init_configs.get('iso'))
            ret_val += self._set_config_value(gp_config, 'imageformat', CE6D_FORMAT_RAW_AND_TINY_JPEG)
            ret_val += self._obtain_serial_num(gp_config)

            return ret_val

        def _initialise_camera(self):
            ret_val = self._setup_camera(self._address)

            if ret_val == 0:
                self.state = CAMERA_STATES.INITIALISED
            else:
                self.state = CAMERA_STATES.ERROR_CONFIG

        # TODO The naming convention for configs and settings is a mess. Sort it out

        def _get_list_of_valid_config_names(self, config, critical=True):
            config_names = []
            try:
                config_count = gp.check_result(gp.gp_widget_count_children(config))
                for choice_index in range(config_count):
                    child = gp.check_result(gp.gp_widget_get_child(config, choice_index))
                    config_name = gp.check_result(gp.gp_widget_get_name(child))
                    if config_name:
                        config_names.append(config_name)

                    grandchildren_names = self._get_list_of_valid_config_names(child)
                    config_names += grandchildren_names

            except gp.GPhoto2Error as ex:
                self._logger.error('Error getting list of camera config names')
                self._logger.error('GPhoto2 Error: %d : %s' % (ex.code, ex.string))
                if critical is True:
                    self.state = CAMERA_STATES.ERROR_CONFIG
                return None
            except Exception:
                self._logger.error(traceback.format_exc())
                return None

            return config_names

        # TODO Correctly handle whether not being able to set/get a config is critical or not
        def _get_list_of_valid_config_choices(self, config, config_str, critical=True):
            config_choices = []
            try:
                config_widget = gp.check_result(gp.gp_widget_get_child_by_name(config, config_str))
                choice_count = gp.check_result(gp.gp_widget_count_choices(config_widget))
                for choice_index in range(choice_count):
                    choice = gp.check_result(gp.gp_widget_get_choice(config_widget, choice_index))
                    if choice:
                        config_choices.append(choice)
            except gp.GPhoto2Error as ex:
                self._logger.error('Error getting list of choices for %s' % config_str)
                self._logger.error('GPhoto2 Error: %d : %s' % (ex.code, ex.string))
                if critical is True:
                    self.state = CAMERA_STATES.ERROR_CONFIG
                return None

            except Exception:
                self._logger.error(traceback.format_exc())
                return None

            return config_choices

        def _set_config_value_by_string(self, config, config_str, val_string, critical=True):
            valid_choices = self._get_list_of_valid_config_choices(config, config_str, critical=critical)
            if valid_choices is None:
                return RET_ERROR

            if val_string in valid_choices:
                return self._set_config_value(config, config_str, valid_choices.index(val_string),
                                              critical=critical)
            else:
                return RET_ERROR

        def _set_config_value(self, config, config_str, config_value, critical=True):
            try:
                # find the capture target config item
                config_widget = gp.check_result(gp.gp_widget_get_child_by_name(config, config_str))
                # get the value bit
                value = gp.check_result(gp.gp_widget_get_choice(config_widget, config_value))
                # set the value
                gp.check_result(gp.gp_widget_set_value(config_widget, value))
                # set the widget back to the config tree
                gp.check_result(gp.gp_camera_set_config(self._gp_camera, config, GPhotoCam._context))

            except gp.GPhoto2Error as ex:
                self._logger.error('Error setting value %s for config %s' % (config_value, config_str))
                self._logger.error('GPhoto2 Error: %d : %s' % (ex.code, ex.string))
                if critical is True:
                    self.state = CAMERA_STATES.ERROR_CONFIG
                return RET_ERROR

            except Exception:
                self._logger.error(traceback.format_exc())
                return RET_ERROR

            self._logger.debug('Successfully set %s on camera.' % config_str)

            return RET_OK

        def _get_config_value(self, config_str, critical=True):
            # get configuration tree
            config = gp.check_result(gp.gp_camera_get_config(self._gp_camera, GPhotoCam._context))

            try:
                config_widget = gp.check_result(gp.gp_widget_get_child_by_name(config, config_str))
                value = gp.check_result(gp.gp_widget_get_value(config_widget))
            except gp.GPhoto2Error as ex:
                self._logger.error('Error getting config value for %s' % config_str)
                self._logger.error('GPhoto2 Error: %d : %s' % (ex.code, ex.string))
                if critical is True:
                    self.state = CAMERA_STATES.ERROR_CONFIG
                return None

            except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
                self._logger.error(traceback.format_exc())
                return None

            return value

        def _obtain_serial_num(self, config):
            # get serial number
            try:
                eossernum_config = gp.check_result(gp.gp_widget_get_child_by_name(config,
                                                                                  'eosserialnumber'))
                eossernum = gp.check_result(gp.gp_widget_get_value(eossernum_config))
            except gp.GPhoto2Error as ex:
                self._logger.error('GPhoto2 Error: %d : %s' % (ex.code, ex.string))
                self.state = CAMERA_STATES.ERROR_CONFIG
                return RET_ERROR

            except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
                self._logger.error(traceback.format_exc())
                return RET_ERROR

            self._logger.info('Successfully retrieved camera serial number %s' % eossernum)

            self.serial_num = eossernum

            return RET_OK

        def reset(self):
            self.state = CAMERA_STATES.UNINITIALISED
            self._initialise_camera()

        def set_setting(self, setting_str, val_str):
            try:
                config = gp.check_result(gp.gp_camera_get_config(self._gp_camera, GPhotoCam._context))
            except gp.GPhoto2Error as ex:
                self._logger.error('GPhoto2 Error: %d : %s' % (ex.code, ex.string))
                return RET_ERROR

            except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
                self._logger.error(traceback.format_exc())
                return RET_ERROR

            return self._set_config_value_by_string(config, setting_str, val_str, critical=False)

        def get_setting(self, setting_str):
            """ This external method is used to get settings from the Cannon EOS 6D using gphoto2. If
                the setting does not exist, then the method returns None. The underlying
                self._get_config_value records an error though. """
            return self._get_config_value(setting_str, critical=False)

        def get_choices_for_setting(self, config_str):
            """ External method for getting the choices. If there are any errors (like the config does
            not exist or there are its not a radio type config) then return None """

            choices = None

            config = gp.check_result(gp.gp_camera_get_config(self._gp_camera, GPhotoCam._context))
            valid_config_names = self._get_list_of_valid_config_names(config, critical=False)
            if valid_config_names is not None and len(valid_config_names) > 0:
                if config_str in valid_config_names:
                    choices = self._get_list_of_valid_config_choices(config, config_str, critical=False)

            return choices

        # TODO We are not letting the user know there was an error downloading an image, should we?

        def capture(self, cam_num):
            if self.state == CAMERA_STATES.INITIALISED:
                self.state = CAMERA_STATES.CAPTURING
                try:
                    # capture an image
                    file_path = gp.check_result(gp.gp_camera_capture(self._gp_camera,
                                                                     gp.GP_CAPTURE_IMAGE,
                                                                     GPhotoCam._context))
                    # prepare the small jpeg filename
                    img_name, _ = os.path.splitext(file_path.name)
                    self._download_fp = os.path.join(DISPLAY_DOWNLOAD_DIR,
                                                     CAM_IMAGE_PREFIX + str(cam_num) + '.JPG')
                    if os.path.isfile(self._download_fp) is True:
                        os.remove(self._download_fp)

                    # get the file object
                    camera_file = gp.check_result(gp.gp_camera_file_get(self._gp_camera,
                                                                        file_path.folder,
                                                                        img_name + '.JPG',
                                                                        gp.GP_FILE_TYPE_NORMAL,
                                                                        GPhotoCam._context))
                    # download the image
                    gp.check_result(gp.gp_file_save(camera_file, self._download_fp))
                    self._fresh_capture = True

                except gp.GPhoto2Error as ex:
                    self.state = CAMERA_STATES.ERROR_CAPTURE
                    self._logger.error('Error capturing image')
                    self._logger.error('GPhoto2 Error: %d : %s' % (ex.code, ex.string))

                except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
                    self._logger.error(traceback.format_exc())
                    self.state = CAMERA_STATES.ERROR_CAPTURE

                # TODO Not sure if this needs to be exception handled
                self._gp_camera.exit(GPhotoCam._context)

                if self.state == CAMERA_STATES.CAPTURING:
                    self.state = CAMERA_STATES.INITIALISED
                    return RET_OK
                else:
                    return RET_ERROR

            # if the camera had not been initialised (or was in another state)
            return RET_ERROR

        def get_state_as_string(self):
            return CAM_STATE_STRINGS[self.state]


    Camera = GPhotoCam

except ImportError:
    import time
    from config import DUMMY_IMAGE_PATH, NUM_DUMMY_CAMS
    # No gphoto2 for windows, have to use dummies while working
    # TODO Implement a Windows Canon6DCam, which uses the Canon EDSDK to communicate with the camera
    # TODO Have the DummyCam load variables from the config file, like the normal camera would
    class DummyCam(object):
        """ Serves as a fake camera for testing purposes."""

        @staticmethod
        def autodetect():
            return [("Dummy Cam", i) for i in range(0, NUM_DUMMY_CAMS)]

        def __init__(self, *args):
            self.state = CAMERA_STATES.INITIALISED
            self.serial_num = None
            self._fresh_capture = False
            self._settings_dict = {'shutterspeed': '1/4', 'iso': '100', 'image_capture_interval': '3.0'}

        def reset(self):
            self.state = CAMERA_STATES.INITIALISED

        def is_cam_image_fresh(self):
            return self._fresh_capture

        def get_cam_image_fp(self):
            self._fresh_capture = False
            return DUMMY_IMAGE_PATH

        def get_state_as_string(self):
            return "Base Cam has no state."

        def set_setting(self, setting_str, setting_val):
            self._settings_dict[setting_str] = setting_val
            return RET_OK

        def get_setting(self, setting_str):
            if setting_str in self._settings_dict.keys():
                return self._settings_dict[setting_str]
            else:
                return None

        def get_choices_for_setting(self, setting_str):
            # just a couple of hard coded ones
            if setting_str == 'shutterspeed':
                return ['1/4', '1/640', '1/2500']
            elif setting_str == 'iso':
                return ['100', '200', '500']
            else:
                return None

        def capture(self, cam_num):
            if self.state == CAMERA_STATES.INITIALISED:
                self.state = CAMERA_STATES.CAPTURING
                # prepare the small jpeg filename
                time.sleep(1)
                self._fresh_capture = True
                self.state = CAMERA_STATES.INITIALISED
                return RET_OK
            else:
                return RET_ERROR

    Camera = DummyCam
    gp = None
