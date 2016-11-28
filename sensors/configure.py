""" D Joubert 18 November 2016 - Configurator - handles reading and saving the initial config """

import configparser
import logging

from config import CONFIG_FP, RET_OK, RET_ERROR, SERVER_LOG_NAME

import pdb

# TODO Do better than a bunch of RET_OK, RET_ERRORS

class TricapConfig():
    """ TricapConfig - Object that reads and writes settings from/to a config file, handling the
        translation from machine code to human readable format, and back again.
        TricapConfig assumes that the only settings that exist are those list in the config file.
        All others will be ignored. """

    # TODO Need to edit the clear_config functions when adding/removing a section
    CAMERA_SECTION_HEADER = 'Camera'
    ALTI_SECTION_HEADER = 'Altimeter'
    MISC_SECTION_HEADER = 'Misc'

    TYPE_STRING = 'string'
    TYPE_INT = 'int'
    TYPE_FLOAT = 'float'

    def __init__(self, config_fp_to_read = CONFIG_FP, logger_name = SERVER_LOG_NAME):
        self._parser = configparser.ConfigParser()

        self._config_fp = config_fp_to_read
        self._logger = logging.getLogger(logger_name)

        self._ready_flag = False

        try:
            self._parser.read(self._config_fp)
            self._ready_flag = True
        except configparser.Error as ex:
            self._logger.error('Error reading from config file %s', self._config_fp)
            self._logger.error('configparser exception: %s', ex.args)

    def is_ready(self):
        return self._ready_flag

    def get_section_dict(self, section_header):
        if self._ready_flag is False:
            return None
        try:
            items = self._parser.items(section_header)
        except configparser.Error as ex:
            self._logger.error(ex)
            return None

        return dict(items)

    def get(self, id_str, section_header, type_str='string'):
        if self._ready_flag is None:
            return None
        try:
            val_str = self._parser[section_header][id_str]
        except (configparser.Error, IOError) as ex:
            self._logger.error('Error reading from config file %s', self._config_fp)
            self._logger.error(ex)
            return None

        if type_str == TricapConfig.TYPE_STRING:
            ret_val = val_str
        elif type_str == TricapConfig.TYPE_INT:
            try:
                ret_val = int(val_str)
            except ValueError:
                self._logger.error('Error converting string %s to int', val_str)
                return None
        elif type_str == TricapConfig.TYPE_FLOAT:
            try:
                ret_val = float(val_str)
            except ValueError:
                self._logger.error('Error converting string %s to float', val_str)
                return None

        return ret_val

    # def clear_config(self):
    #     # TODO There should be a cleaner way to do this
    #     self._parser.clear()
    #     self._parser[TricapConfig.ALTI_SECTION_HEADER] = {}
    #     self._parser[TricapConfig.MISC_SECTION_HEADER] = {}
    #     self._parser[TricapConfig.CAMERA_SECTION_HEADER] = {}

    def set_section(self, section_dict, section_header):
        """ Change the values stored in the internal configparser.
            Note that settings will only be changed. Nothing gets added or removed """
        # TODO Replace with an assert?
        if self._ready_flag is None:
            return None

        for key in section_dict.keys():
            if key not in self._parser[section_header]:
                self._logger.warning('Not setting %s, which was not in the original cfg', key)
            else:
                try:
                    self._parser.set(section_header, key, str(section_dict[key]))
                except configparser.Error as ex:
                    self._logger.error('Error setting %s as %s', key, str(section_dict[key]))
                    self._logger.error('configparser exception: %s', ex.args)
                    return RET_ERROR

        return RET_OK

    def save_to_file(self, config_fp = None):
        """ Save the values of the configparser to file. """

        if self._ready_flag is None:
            return None

        if config_fp is None:
            config_fp = self._config_fp

        try:
            config_file = open(config_fp, 'w')
            self._parser.write(config_file)
            config_file.close()
        except (configparser.Error, IOError) as ex:
            self._logger.error('Error writing configs to file %s', config_fp)
            self._logger.error(ex)
            return RET_ERROR

        return RET_OK
