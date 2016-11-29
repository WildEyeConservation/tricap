# coding=utf-8
"""Configuration variables and classes for tricap.py"""

# Get all the machine specific configurations (stuff like file locations)
import local_paths

SERVER_LOG_DIR = local_paths.SERVER_LOG_DIR
SESSION_ROOT_DIR = local_paths.SESSION_ROOT_DIR
DISPLAY_DOWNLOAD_DIR = local_paths.DISPLAY_DOWNLOAD_DIR
DUMMY_IMAGE_PATH = local_paths.DUMMY_IMAGE_PATH
CONFIG_FP = local_paths.CONFIG_FP
DEFAULT_CONFIG_FP = local_paths.DEFAULT_CONFIG_FP
TEST_STATIC_DIR = local_paths.TEST_STATIC_DIR

# other variables
CAM_IMAGE_PREFIX = 'cam'
SECRET_KEY = 'tricap-secret-key'
RET_ERROR = -1
RET_OK = 0
SERVER_LOG_NAME = 'tricap_server_log'

# gphoto2 canon eos 6d configs
CE6D_CAP_TARGET_MEMORY = 0
CE6D_CAP_TARGET_SD_CARD = 1

# TODO Delete this if not used (i.e. check where this is used)
DEFAULT_IMAGE_CAPTURE_INTERVAL = 3.0
CE6D_SHUTTER_SPEED_1_2500 = 49
CE6D_SHUTTER_SPEED_1_640 = 43
CE6D_SHUTTER_SPEED_1_4 = 21
DEFAULT_SHUTTER_SPEED = CE6D_SHUTTER_SPEED_1_2500

CE6D_FORMAT_RAW_AND_TINY_JPEG = 15
CE6D_FORMAT_RAW = 32

# Altimeter default configs
ALTI_NUM_AVG_FRAMES = 2
ALTI_MEASURE_TIMEOUT = 2

NUM_DUMMY_CAMS = 3


class CAMERA_STATES:
    UNINITIALISED, INITIALISED, CAPTURING, ERROR_CONFIG, ERROR_CAPTURE = list(range(5))
    MAX = 5
    MIN = 0


CAM_STATE_STRINGS = ['Uninitialised', 'Ready', 'Capturing',
                     'Configuration Error', 'Capture Error']


class CAM_MANAGER_STATES:
    STOPPED, STARTED, ERROR_NO_CAMS, ERROR_CONFIG = list(range(4))
    MAX = 3
    MIN = 0


class ALTIMETER_STATE:
    NOT_CONNECTED, CONNECTED, MEASURING, ERROR = list(range(4))
    MAX = 2
    MIN = 0


ALTI_STATE_STRINGS = ['Not connected', 'Connected', 'Measuring', 'Error']


class BUTTON_CODES:
    START, STOP, TEST, RESET = list(range(4))
    MAX = 3
    MIN = 0


class LOG_CODES:
    ALL = list(range(1))
    MAX = 1
    MIN = 0
