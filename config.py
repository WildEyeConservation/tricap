"""Configuration variables and classes for tricap.py

   D Joubert Innoventix Consulting 27 October 2016."""

import local_paths

SERVER_LOG_DIR = local_paths.SERVER_LOG_DIR
SESSION_ROOT_DIR = local_paths.SESSION_ROOT_DIR
DISPLAY_DOWNLOAD_DIR = local_paths.DISPLAY_DOWNLOAD_DIR
WORKING_OS = local_paths.WORKING_OS
DUMMY_IMAGE_PATH = local_paths.DUMMY_IMAGE_PATH
CONFIG_FP = local_paths.CONFIG_FP

CAM_IMAGE_PREFIX = 'cam'
DEFAULT_IMAGE_CAPTURE_INTERVAL = 3.0
SECRET_KEY = 'tricap-secret-key'

# gphoto2 canon eos 6d configs
CE6D_CAP_TARGET_MEMORY = 0
CE6D_CAP_TARGET_SD_CARD = 1

# TODO Going to need to support all possible shutter speeds, because we will want to experiment
CE6D_SHUTTER_SPEED_1_2500 = 49
CE6D_SHUTTER_SPEED_1_640 = 43
CE6D_SHUTTER_SPEED_1_4 = 21
DEFAULT_SHUTTER_SPEED = CE6D_SHUTTER_SPEED_1_2500

CE6D_FORMAT_RAW_AND_TINY_JPEG = 15
CE6D_FORMAT_RAW = 32

# Altimeter default configs
ALTI_NUM_AVG_FRAMES = 2
ALTI_MEASURE_TIMEOUT = 2

RET_ERROR = -1
RET_OK = 0


class CAMERA_STATES:
    UNINITIALISED, INITIALISED, CAPTURING, ERROR_CONFIG, ERROR_CAPTURE = list(range(5))
    MAX = 5
    MIN = 0

CAM_STATE_STRINGS = ['Uninitialised', 'Ready', 'Capturing',
                            'Configuration Error', 'Capture Error']

class CAM_MANAGER_STATES:
    STOPPED, STARTED, ERROR_NO_CAMS = list(range(3))
    MAX = 2
    MIN = 0


class ALTIMETER_STATE:
    NOT_CONNECTED, CONNECTED, MEASURING, ERROR = list(range(4))
    MAX = 2
    MAX = 0

ALTI_STATE_STRINGS = ['Not connected', 'Connected', 'Measuring', 'Error']


class BUTTON_CODES:
    START, STOP, TEST, RESET = list(range(4))
    MAX = 3
    MIN = 0


class LOG_CODES:
    ALL = list(range(1))
    MAX = 1
    MIN = 0
