"""Configuration variables and classes for tricap.py.

Imports all paths from the local_paths.py file.
"""
# coding=utf-8

from enum import Enum, IntEnum

# Get all the local file paths, specific to a system
from local_paths import *

# other variables
CAM_IMAGE_PREFIX = 'cam'
SECRET_KEY = 'tricap-secret-key'
RET_ERROR = -1
RET_OK = 0
SERVER_LOG_NAME = 'tricap_server_log'

# gphoto2 canon eos 6d configs
CE6D_CAP_TARGET_MEMORY = 'Internal RAM'
CE6D_CAP_TARGET_SD_CARD = 'Memory card'

CE6D_FORMAT_RAW = 'RAW'

# Altimeter default configs
ALTI_NUM_AVG_FRAMES = 2
ALTI_MEASURE_TIMEOUT = 2

NUM_DUMMY_CAMS = 3

MOUNT_POINT = "/mnt/ext_cam_storage"
SONY_TEMPFS_MOUNT_POINT = "/home/radxa/SonySDKWrapper/memoryFs"

CAMERA_STATES = Enum("CamState", ["UNINITIALISED", "INITIALISED", "CAPTURING", 
                                  "ERROR_CONFIG", "ERROR_CAPTURE"])
CAM_MANAGER_STATES = Enum("CamManagerState", ["STOPPED", "STARTED", "ERROR_NO_CAMS", "ERROR_CONFIG", "COPYING", "LOADING_PREVIEW"])
ALTIMETER_STATE = Enum("AltiState", ["NOT_CONNECTED", "CONNECTED", "MEASURING", 
                                     "ERROR"])
BUTTON_CODE = IntEnum("ButtonCode", {"START": 0, "STOP": 1, "TEST": 2,
                                     "RESET": 3, "STARTSTOP": 4})
LOG_CODES = Enum("LogCode", "ALL")
OVERRIDESTATE = IntEnum("OverrideState", {"ALTISWITCH": 0, "STOPOVERRIDE": 1, 
                                          "MANUALSTART": 2})
