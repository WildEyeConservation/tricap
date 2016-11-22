""" D Joubert 18 November 2016 - Configurator - handles reading and saving the initial config """

import configparser

from config import CE6D_SHUTTER_SPEED_1_2500, CE6D_SHUTTER_SPEED_1_640, CE6D_SHUTTER_SPEED_1_4
from config import CONFIG_FP, DEFAULT_IMAGE_CAPTURE_INTERVAL, RET_OK, RET_ERROR
from config import DEFAULT_SHUTTER_SPEED

import pdb

SECTION_HEADER = 'Tricap'

class TricapConfig():
    """ Configurator - Object that reads and writes configuration information, handling the
        translation from machine code to human readable format, and back again """

    def __init__(self, logger, config_fp_to_read = CONFIG_FP):
        self._parser = configparser.ConfigParser()

        self._config_fp = config_fp_to_read
        self._logger = logger

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

    # @staticmethod
    # def convert_shutterspeed_str_to_code(val_str):
    #     if val_str == '1/2500':
    #         config_val = CE6D_SHUTTER_SPEED_1_2500
    #     elif val_str == '1/640':
    #         config_val = CE6D_SHUTTER_SPEED_1_640
    #     elif val_str == '1/4':
    #         config_val = CE6D_SHUTTER_SPEED_1_4
    #     else:
    #         return None
    #     return config_val

    # @staticmethod
    # def convert_shutterspeed_code_to_str(config_code):
    #     if isinstance(config_code, str) is True:
    #         config_code = int(config_code)
    #
    #     if config_code == CE6D_SHUTTER_SPEED_1_2500:
    #         val_str = '1/2500'
    #     elif config_code == CE6D_SHUTTER_SPEED_1_640:
    #         val_str = '1/640'
    #     elif config_code == CE6D_SHUTTER_SPEED_1_4:
    #         val_str = '1/4'
    #     else:
    #         return None
    #
    #     return val_str


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
            # val_str = configparser.ConfigParser.get(self, SECTION_HEADER, id_str)
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

    def save_config_dict_to_file(self, config_dict, config_fp = None):
        if self._ready_flag is None:
            return None

        if config_fp is None:
            config_fp = self._config_fp

        for key in config_dict.keys():
            try:
                # # check specific, troublesome settings:
                # if key == 'shutterspeed':
                #     if self.convert_shutterspeed_str_to_code(config_dict[key]) is None:
                #         self._logger.error('Bad shutterspeed %s' % str(config_dict[key]))
                #         return RET_ERROR

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


# def save_config(new_config, save_to_fp=None):
#     # TODO Do a check before overwriting the config file
#     if save_to_fp is None:
#         save_to_fp = CONFIG_FP
#
#     with open(save_to_fp, 'w') as config_file:
#         for key in new_config.keys():
#             if key == 'shutterspeed':
#                 val_str = translate_code_to_shutterspeed_str(new_config[key])
#             else:
#                 val_str =  str(new_config[key])
#             line = key + ' = ' + val_str + '\n'
#             config_file.write(line)
#
#     return RET_OK
#
# def read_init_config(config_fp=CONFIG_FP):
#     init_configs = {}
#
#     with open(config_fp, 'r') as config_file:
#         for line in config_file:
#             parts = line.split('=')
#             init_configs[parts[0].strip()] = parts[1].strip()
#
#     config_val = CE6D_SHUTTER_SPEED_1_2500
#     if 'shutterspeed' in init_configs.keys():
#         val_str = init_configs['shutterspeed']
#         config_val = translate_shutterspeed_str_to_code(val_str)
#
#         if config_val == RET_ERROR:
#             # TODO There should really be an error here, or some sort of error handling
#             config_val = CE6D_SHUTTER_SPEED_1_2500
#
#     init_configs['shutterspeed'] = config_val
#
#     config_val = DEFAULT_IMAGE_CAPTURE_INTERVAL
#     if 'image_capture_interval' in init_configs.keys():
#         config_val = float(init_configs['image_capture_interval'] )
#     init_configs['image_capture_interval'] = config_val
#
#     return init_configs
