# D Joubert Innoventix Consulting 27 October 2016

import local_paths

SERVER_LOG_DIR = local_paths.SERVER_LOG_DIR
SESSION_ROOT_DIR = local_paths.SESSION_ROOT_DIR
DISPLAY_DOWNLOAD_DIR = local_paths.DISPLAY_DOWNLOAD_DIR

CAM_IMAGE_PREFIX = 'cam'
IMAGE_CAPTURE_INTERVAL = 3.0

# gphoto2 canon eos 6d configs
CE6D_CAP_TARGET_MEMORY = 0
CE6D_CAP_TARGET_SD_CARD = 1

CE6D_SHUT_SPEED_1_2500 = 49
CE6D_SHUT_SPEED_1_640 = 43
CE6D_SHUT_SPEED_1_4 = 21

CE6D_FORMAT_RAW_AND_TINY_JPEG = 15
CE6D_FORMAT_RAW = 32


class TRICAP_CAM_STATES:
    UNINITIALISED, INITIALISED, CAPTURING, ERROR_CONFIG, ERROR_CAPTURE = range(5)
    MAX = 5
    MIN = 0

TRICAP_CAM_STATE_STRINGS = ['Uninitialised', 'Ready', 'Capturing',
                            'Configuration Error', 'Capture Error']

class TRICAP_CAMS_MANAGER_STATES:
    STOPPED, STARTED, ERROR_NO_CAMS = range(3)
    MAX = 2
    MIN = 0


class ALTIMETER_STATE:
    NOT_CONNECTED, CONNECTED, MEASURING, ERROR = range(4)
    MAX = 2
    MAX = 0


class BUTTON_CODES:
    START, STOP, TEST, RESET = range(4)
    MAX = 3
    MIN = 0

class LOG_CODES:
    ALL = range(1)
    MAX = 1
    MIN = 0
