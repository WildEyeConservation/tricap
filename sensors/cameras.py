import os
import traceback
import pdb

# No gphoto2 for windows, have to use dummmies while working
# TODO Implement a Windows Canon6DCam, which uses the Canon EDSDK to communicate with the camera
try:
    import gphoto2 as gp
    GPHOTO2_IMPORTED = True
except ImportError:
    GPHOTO2_IMPORTED = False

from .configure import TricapConfig

from config import CE6D_CAP_TARGET_SD_CARD, CE6D_FORMAT_RAW_AND_TINY_JPEG, DISPLAY_DOWNLOAD_DIR
from config import CAM_IMAGE_PREFIX, CAM_STATE_STRINGS, RET_ERROR, RET_OK, CAMERA_STATES

# TODO currently, we are coding in a mess of C vs C++ styles. Fix this.

class Cam():
    """ Base class for all camera handlers. Serves as a fake class for testing purposes."""

    def __init__(self):
        self.state = CAMERA_STATES.INITIALISED
        self.serial_num = None
        self._settings_dict = {'shutterspeed': '1/4', 'iso': '100', 'image_capture_interval': '3.0'}

    def reset(self):
        self.state = CAMERA_STATES.INITIALISED

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

class Canon6DCam(Cam):
    """ Hander for the Canon EOS 6D Camera. Uses gphoto2 to handle the actual communication. """

    def __init__(self, context, port_info, logger):
        Cam.__init__(self)

        self._context = context
        self._gp_camera = None

        self._logger = logger
        self._port_info = port_info

        self.state = CAMERA_STATES.UNINITIALISED

        self._initialise_camera()

        if self.state == CAMERA_STATES.INITIALISED:
            self._logger.info('Canon EOS 6D Camera %s on port %s succesfully initialised'
                              %(self.serial_num, self._port_info.get_path() ))
        else:
            self._logger.error('Canon EOS 6D Camera not succesfully initialised')

    def _setup_camera(self):
        self._gp_camera = gp.Camera()
        try:
            self._gp_camera.set_port_info(self._port_info)
            self._gp_camera.init(self._context)
        except gp.GPhoto2Error as ex:
            self._logger.error('GPhoto2 error: %d: %s' %(ex.code, ex.string))
            return RET_ERROR
        except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
            self._logger.error(traceback.format_exc())
            return RET_ERROR

        init_configs = TricapConfig(self._logger)

        # get configuration tree
        gp_config = gp.check_result(gp.gp_camera_get_config(self._gp_camera, self._context))

        ret_val = 0
        ret_val += self._set_config_value(gp_config, 'capturetarget', CE6D_CAP_TARGET_SD_CARD)
        ret_val += self._set_config_value_by_string(gp_config, 'shutterspeed',
                                                    init_configs.get('shutterspeed'))
        ret_val += self._set_config_value_by_string(gp_config, 'iso', init_configs.get('iso'))
        ret_val += self._set_config_value(gp_config, 'imageformat', CE6D_FORMAT_RAW_AND_TINY_JPEG)
        ret_val += self._obtain_serial_num(gp_config)

        return ret_val

    def _initialise_camera(self):
        ret_val = self._setup_camera()

        if ret_val == 0:
            self.state = CAMERA_STATES.INITIALISED
        else:
            self.state = CAMERA_STATES.ERROR_CONFIG

    # TODO The naming convention for configs and settings is a mess. Sort it out

    def _get_list_of_valid_config_names(self, config):
        config_names = []
        try:
            config_count = gp.check_result(gp.gp_widget_count_children(config))
            for choice_index in range(config_count):
                child = gp.check_result(gp.gp_widget_get_child(config, choice_index))
                config_name = gp.check_result(gp.gp_widget_get_name(child))
                if config_name:
                    config_names.append(config_name)

                grandchildren_names = self._get_list_of_valid_config_names(child)
                config_names+=grandchildren_names

        except gp.GPhoto2Error as ex:
            self._logger.error('Error getting list of camera config names')
            self._logger.error('GPhoto2 Error: %d : %s' %(ex.code, ex.string))
            self.state = CAMERA_STATES.ERROR_CONFIG
            return None
        except Exception:
            self._logger.error(traceback.format_exc())
            return None

        return config_names


    def _get_list_of_valid_config_choices(self, config, config_str):
        config_choices = []
        try:
            config_widget = gp.check_result(gp.gp_widget_get_child_by_name(config, config_str))
            choice_count = gp.check_result(gp.gp_widget_count_choices(config_widget))
            for choice_index in range(choice_count):
                choice = gp.check_result(gp.gp_widget_get_choice(config_widget, choice_index))
                if choice:
                    config_choices.append(choice)
        except gp.GPhoto2Error as ex:
            self._logger.error('Error getting list of choices for %s' %(config_str))
            self._logger.error('GPhoto2 Error: %d : %s' %(ex.code, ex.string))
            self.state = CAMERA_STATES.ERROR_CONFIG
            return None
        except Exception:
            self._logger.error(traceback.format_exc())
            return None

        return config_choices

    def _set_config_value_by_string(self, config, config_str, val_string):
        valid_choices = self._get_list_of_valid_config_choices(config, config_str)
        if val_string in valid_choices:
            return self._set_config_value(config, config_str, valid_choices.index(val_string))
        else:
            return RET_ERROR

    def _set_config_value(self, config, config_str, config_value):
        try:
            # find the capture target config item
            config_widget = gp.check_result(gp.gp_widget_get_child_by_name(config, config_str))
            # get the value bit
            value = gp.check_result(gp.gp_widget_get_choice(config_widget, config_value))
            # set the value
            gp.check_result(gp.gp_widget_set_value(config_widget, value))
            # set the widget back to the config tree
            gp.check_result(gp.gp_camera_set_config(self._gp_camera, config, self._context))

        except gp.GPhoto2Error as ex:
            self._logger.error('Error setting value %s for config %s' %(config_value, config_str))
            self._logger.error('GPhoto2 Error: %d : %s' %(ex.code, ex.string))
            self.state = CAMERA_STATES.ERROR_CONFIG
            return RET_ERROR
        except Exception:
            self._logger.error(traceback.format_exc())
            return RET_ERROR

        self._logger.debug('Succesfully set %s on camera.' % config_str)

        return RET_OK

    def _get_config_value(self, config_str):
        # get configuration tree
        config = gp.check_result(gp.gp_camera_get_config(self._gp_camera, self._context))

        try:
            config_widget = gp.check_result(gp.gp_widget_get_child_by_name(config, config_str))
            value = gp.check_result(gp.gp_widget_get_value(config_widget))
        except gp.GPhoto2Error as ex:
            self._logger.error('Error getting config value for %s' %config_str)
            self._logger.error('GPhoto2 Error: %d : %s' %(ex.code, ex.string))
            self.state = CAMERA_STATES.ERROR_CONFIG
            return RET_ERROR
        except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
            self._logger.error(traceback.format_exc())
            return RET_ERROR

        return value

    def _obtain_serial_num(self, config):
        # get serial number
        try:
            eossernum_config = gp.check_result(gp.gp_widget_get_child_by_name(config,
                                                                              'eosserialnumber'))
            eossernum = gp.check_result(gp.gp_widget_get_value(eossernum_config))
        except gp.GPhoto2Error as ex:
            self._logger.error('GPhoto2 Error: %d : %s' %(ex.code, ex.string))
            self.state = CAMERA_STATES.ERROR_CONFIG
            return RET_ERROR
        except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
            self._logger.error(traceback.format_exc())
            return RET_ERROR

        self._logger.info('Succesfully retrieved camera serial number %s' % eossernum)

        self.serial_num = eossernum

        return RET_OK

    def reset(self):
        self.state = CAMERA_STATES.UNINITIALISED
        self._initialise_camera()

    def set_setting(self, setting_str, val_str):
        try:
            config = gp.check_result(gp.gp_camera_get_config(self._gp_camera, self._context))
        except gp.GPhoto2Error as ex:
            self._logger.error('GPhoto2 Error: %d : %s' %(ex.code, ex.string))
            return RET_ERROR
        except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
            self._logger.error(traceback.format_exc())
            return RET_ERROR

        return self._set_config_value_by_string(config, setting_str, val_str)

    def get_setting(self, setting_str):
        return self._get_config_value(setting_str)

    def get_choices_for_setting(self, config_str):
        """ External method for getting the choices. If there are any errors (like the config does
        not exist or there are its not a radio type config) then return None """

        choices = None

        config = gp.check_result(gp.gp_camera_get_config(self._gp_camera, self._context))
        valid_config_names = self._get_list_of_valid_config_names(config)
        if valid_config_names is not None and len(valid_config_names) > 0:
            if config_str in valid_config_names:
                choices = self._get_list_of_valid_config_choices(config, config_str)

        return choices

    # TODO We are not letting the user know there was an error downloading an image, should we?

    def create_single_capture_func(self):
        def worker(cam_num):
            if self.state == CAMERA_STATES.INITIALISED:
                self.state = CAMERA_STATES.CAPTURING
                try:
                    # capture an image
                    file_path = gp.check_result(gp.gp_camera_capture(self._gp_camera,
                                                                     gp.GP_CAPTURE_IMAGE,
                                                                     self._context))
                    # prepare the small jpeg filename
                    img_name, _ = os.path.splitext(file_path.name)
                    download_fp = os.path.join(DISPLAY_DOWNLOAD_DIR,
                                               CAM_IMAGE_PREFIX+str(cam_num)+'.JPG')
                    if os.path.isfile(download_fp) is True:
                        os.remove(download_fp)

                    # get the file object
                    camera_file = gp.check_result(gp.gp_camera_file_get(self._gp_camera,
                                                                        file_path.folder,
                                                                        img_name+'.JPG',
                                                                        gp.GP_FILE_TYPE_NORMAL,
                                                                        self._context))
                    # download the image
                    gp.check_result(gp.gp_file_save(camera_file, download_fp))

                except gp.GPhoto2Error as ex:
                    self.state = CAMERA_STATES.ERROR_CAPTURE
                    self._logger.error('Error capturing image')
                    self._logger.error('GPhoto2 Error: %d : %s' %(ex.code, ex.string))
                except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
                    self._logger.error(traceback.format_exc())
                    self.state = CAMERA_STATES.ERROR_CAPTURE

                # TODO Not sure if this needs to be exception handled
                self._gp_camera.exit(self._context)

                if self.state == CAMERA_STATES.CAPTURING:
                    self.state = CAMERA_STATES.INITIALISED
                    return RET_OK
                else:
                    return RET_ERROR

            #if the camera had not been initialised (or was in another state)
            return RET_ERROR

        return worker

    def get_state_as_string(self):
        return CAM_STATE_STRINGS[self.state]
