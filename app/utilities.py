""" D Joubert 16 November 2016 - Utility functions used throughout tricap app """

from config import CE6D_SHUTTER_SPEED_1_2500, CE6D_SHUTTER_SPEED_1_640, CE6D_SHUTTER_SPEED_1_4
from config import CONFIG_FP, DEFAULT_IMAGE_CAPTURE_INTERVAL, RET_OK, RET_ERROR

def translate_shutterspeed_str_to_code(val_str):
    if val_str == '1/2500':
        config_val = CE6D_SHUTTER_SPEED_1_2500
    elif val_str == '1/640':
        config_val = CE6D_SHUTTER_SPEED_1_640
    elif val_str == '1/4':
        config_val = CE6D_SHUTTER_SPEED_1_4
    else:
        return RET_ERROR

    return config_val

def save_config(new_config):
    # TODO Do a check before overwriting the config file
    with open(CONFIG_FP, 'w') as config_file:
        for key in new_config.keys():
            line = key + ' = ' + new_config[key] + '\n'
            config_file.write(line)

    return RET_OK

def read_init_config(config_fp=CONFIG_FP):
    init_configs = {}

    with open(config_fp, 'r') as config_file:
        for line in config_file:
            parts = line.split('=')
            init_configs[parts[0].strip()] = parts[1].strip()

    config_val = CE6D_SHUTTER_SPEED_1_2500
    if 'shutterspeed' in init_configs.keys():
        val_str = init_configs['shutterspeed']
        config_val = translate_shutterspeed_str_to_code(val_str)

        if config_val == RET_ERROR:
            config_val = CE6D_SHUTTER_SPEED_1_2500

    init_configs['shutterspeed'] = config_val

    config_val = DEFAULT_IMAGE_CAPTURE_INTERVAL
    if 'image_capture_interval' in init_configs.keys():
        config_val = float(init_configs['image_capture_interval'] )
    init_configs['image_capture_interval'] = config_val

    return init_configs
