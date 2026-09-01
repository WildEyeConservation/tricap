"""D Joubert 18 November 2016 - Configurator - handles reading and saving the initial config."""

import configparser
import logging
from config import (
    CONFIG_FP,
    SONY_IMAGE_FORMAT_CAMERA_SETTING,
    SONY_IMAGE_FORMAT_CONFIG_KEY,
)


class TricapConfigError(Exception):
    pass


class TricapConfig:
    """ TricapConfig: Object that reads and writes settings from/to a config file, handling the
        translation from machine code to human readable format, and back again. Uses the
        configparser to do most of the heavy lifting.
        - TricapConfig assumes that the only settings that exist are those listed in the config
          file. New optional settings may supply a backwards-compatible default for older files.
        - Note that keys in sections are case-insensitive and stored in lowercase, and that all keys
          in sections are accessible in a case-insensitive manner.
        - The TricapConfig is treated as a flight critical component, and therefore any exceptions
          raised should be raised, i.e. the system should halt and catch fire.
         """

    _logger = logging.getLogger(__name__)

    CAMERA_SECTION_HEADER = 'Camera'
    ALTI_SECTION_HEADER = 'Altimeter'
    MISC_SECTION_HEADER = 'Misc'

    # Options that older initial.cfg files may still carry but nothing reads.
    RETIRED_MISC_OPTIONS = ('session_description',)
    # Serial commands of the retired Trusense altimeter; the GRF-500 has no
    # equivalent and its driver never consumed them.
    RETIRED_ALTI_OPTIONS = ('measurement_timeout', 'num_frames_to_avg')

    TYPE_STRING = 'string'
    TYPE_INT = 'int'
    TYPE_FLOAT = 'float'

    def __init__(self, config_fp_to_read=CONFIG_FP):
        self._parser = configparser.ConfigParser()

        self._config_fp = config_fp_to_read
        self._ready_flag = False

        try:
            # Switched from using read to read_file to make the parser raise an exception if there
            # is a problem with the file
            config_file = open(self._config_fp, 'r')
            self._parser.read_file(config_file)
            config_file.close()
            # Deployed initial.cfg files predate this option. Keep their
            # behavior safe by leaving the physical camera setting untouched.
            if not self._parser.has_option(
                    self.CAMERA_SECTION_HEADER, SONY_IMAGE_FORMAT_CONFIG_KEY):
                self._parser.set(
                    self.CAMERA_SECTION_HEADER,
                    SONY_IMAGE_FORMAT_CONFIG_KEY,
                    SONY_IMAGE_FORMAT_CAMERA_SETTING,
                )
            elif self._parser.get(
                    self.CAMERA_SECTION_HEADER,
                    SONY_IMAGE_FORMAT_CONFIG_KEY) == 'Camera setting':
                self._parser.set(
                    self.CAMERA_SECTION_HEADER,
                    SONY_IMAGE_FORMAT_CONFIG_KEY,
                    SONY_IMAGE_FORMAT_CAMERA_SETTING,
                )
            for option in tuple(self._parser.options(self.CAMERA_SECTION_HEADER)):
                if option != SONY_IMAGE_FORMAT_CONFIG_KEY:
                    self._parser.remove_option(self.CAMERA_SECTION_HEADER, option)
            for retired_section in ('Web', 'SMS'):
                self._parser.remove_section(retired_section)
            for retired_option in self.RETIRED_MISC_OPTIONS:
                self._parser.remove_option(self.MISC_SECTION_HEADER, retired_option)
            for retired_option in self.RETIRED_ALTI_OPTIONS:
                self._parser.remove_option(self.ALTI_SECTION_HEADER, retired_option)
            self._ready_flag = True
        except (configparser.Error, IOError, OSError) as ex:
            self._logger.error('Error reading from config file %s', self._config_fp)
            self._logger.error('configparser exception: %s', ex.args)
            # If there is an error reading from the config file, the system should fall over
            raise

    def is_ready(self):
        return self._ready_flag

    def get_section_dict(self, section_header):
        """ Get all the parameters for a particular section """

        assert self._ready_flag

        try:
            items = self._parser.items(section_header)
        except configparser.Error as ex:
            self._logger.error(ex)
            raise

        return dict(items)

    def get(self, id_str, section_header, type_str='string'):

        assert self._ready_flag

        try:
            val_str = self._parser[section_header][id_str]
        except (configparser.Error, IOError, KeyError) as ex:
            self._logger.error('Error reading from config file %s', self._config_fp)
            self._logger.error(ex)
            raise

        ret_val = val_str
        try:
            if type_str == TricapConfig.TYPE_INT:
                ret_val = int(val_str)
            elif type_str == TricapConfig.TYPE_FLOAT:
                ret_val = float(val_str)
        except ValueError:
            self._logger.error('Error converting string %s to %s', val_str, type_str)
            raise

        return ret_val

    def set_section(self, section_dict: dict, section_header):
        """Change the values stored in the internal configparser.

        Note that settings will only be changed. Nothing gets added or removed.
        """
        # Using an assert, because this should really not happen
        assert self._ready_flag

        try:
            for key in section_dict.keys():
                if key not in self._parser[section_header]:
                    self._logger.warning('Not setting %s, which was not in the original cfg', key)
                    raise TricapConfigError
                else:
                    self._parser.set(section_header, key, str(section_dict[key]))
        except (configparser.Error, KeyError) as ex:
            self._logger.error('Error setting %s as %s in section %s', key, str(section_dict[key]),
                               section_header)
            self._logger.error('configparser exception: %s', ex.args)
            raise

    def save_to_file(self, config_fp=None):
        """ Save the values of the configparser to file. """

        assert self._ready_flag

        if config_fp is None:
            config_fp = self._config_fp

        try:
            config_file = open(config_fp, 'w')
            self._parser.write(config_file)
            config_file.close()
        except (configparser.Error, IOError) as ex:
            self._logger.error('Error writing configs to file %s', config_fp)
            self._logger.error(ex)
            raise
