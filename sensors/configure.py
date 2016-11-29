""" D Joubert 18 November 2016 - Configurator - handles reading and saving the initial config """

import configparser
import logging

from config import CONFIG_FP, RET_OK, RET_ERROR

SECTION_HEADER = 'Tricap'


class TricapConfig:
    """ Configurator - Object that reads and writes configuration information, handling the
        translation from machine code to human readable format, and back again """
    _logger = logging.getLogger(__name__)

    def __init__(self, config_fp_to_read=CONFIG_FP):
        self._parser = configparser.ConfigParser()

        self._config_fp = config_fp_to_read
        self._ready_flag = False

        self.TYPE_STRING = 'string'
        self.TYPE_INT = 'int'
        self.TYPE_FLOAT = 'float'

        try:
            self._parser.read(self._config_fp)
            self._ready_flag = True
        except configparser.Error as ex:
            self._logger.error('Error reading from config file %s' % self._config_fp)
            self._logger.error('configparser exception: %s' % ex.args)

    def is_ready(self):
        return self._ready_flag

    def get_dict(self):
        if self._ready_flag is False:
            return None
        try:
            items = self._parser.items(SECTION_HEADER)
        except configparser.Error as ex:
            self._logger.error('Error extracting items from config')
            self._logger.error('configparser exception: %s' % ex.args)
            return None

        return dict(items)

    def get(self, id_str, type_str='string'):
        if self._ready_flag is None:
            return None
        try:
            val_str = self._parser[SECTION_HEADER][id_str]

        except configparser.Error as ex:
            self._logger.error('Error reading from config file %s' % self._config_fp)
            self._logger.error('configparser exception: %s' % ex.args)
            return None

        if type_str == self.TYPE_STRING:
            return val_str

        if type_str == self.TYPE_INT:
            try:
                ret_val = int(val_str)
            except ValueError:
                self._logger.error('Error converting string %s to int' % val_str)
                return None
            return ret_val

        if type_str == self.TYPE_FLOAT:
            try:
                ret_val = float(val_str)
            except ValueError:
                self._logger.error('Error converting string %s to float' % val_str)
                return None
            return ret_val

    def clear_config(self):
        self._parser.clear()
        self._parser[SECTION_HEADER] = {}

    def save_config_dict_to_file(self, config_dict, config_fp=None):
        """ Save the values in a config dict to the config file. Note that settings will only be
            added and changed. Nothing gets removed """

        if self._ready_flag is None:
            return None

        if config_fp is None:
            config_fp = self._config_fp

        for key in config_dict.keys():
            try:
                self._parser.set(SECTION_HEADER, key, str(config_dict[key]))
            except configparser.Error as ex:
                self._logger.error('Error setting %s with value %s' % (key, str(config_dict[key])))
                self._logger.error('configparser exception: %s' % ex.args)
                return RET_ERROR
        try:
            config_file = open(config_fp, 'w')
            self._parser.write(config_file)
            config_file.close()
        except configparser.Error as ex:
            self._logger.error('Error writing configs to file %s' % config_fp)
            self._logger.error('configparser exception: %s' % ex.args)
            return RET_ERROR
        except Exception as ex:
            self._logger.error('Error writing configs to file %s' % config_fp)
            self._logger.error('general exception: %s' % ex.args)
            return RET_ERROR

        return RET_OK
