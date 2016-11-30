# coding=utf-8
"""Configuration variables and classes for tricap.py"""

# Get all the machine specific configurations (stuff like file locations)
from enum import Enum, IntEnum

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

CE6D_FORMAT_RAW_AND_TINY_JPEG = 15
CE6D_FORMAT_RAW = 32

# Altimeter default configs
ALTI_NUM_AVG_FRAMES = 2
ALTI_MEASURE_TIMEOUT = 2

NUM_DUMMY_CAMS = 3

CAMERA_STATES = Enum("CamState", ["UNINITIALISED", "INITIALISED", "CAPTURING", "ERROR_CONFIG", "ERROR_CAPTURE"])
CAM_MANAGER_STATES = Enum("CamManagerState", ["STOPPED", "STARTED", "ERROR_NO_CAMS", "ERROR_CONFIG"])
ALTIMETER_STATE = Enum("AltiState", ["NOT_CONNECTED", "CONNECTED", "MEASURING", "ERROR"])
BUTTON_CODE = IntEnum("ButtonCode", {"START": 0, "STOP": 1, "TEST": 2, "RESET": 3})
LOG_CODES = Enum("LogCode", "ALL")
