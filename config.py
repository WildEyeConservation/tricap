"""Shared configuration paths, constants, and states for SkySeeker."""
# coding=utf-8

import os
from enum import Enum

# Deployment paths on the rig.
SERVER_LOG_DIR = '/home/radxa/tricap/logs'
CONFIG_FP = '/home/radxa/tricap/initial.cfg'

# Shipped defaults for every supported option; initial.cfg only holds overrides.
DEFAULT_CONFIG_FP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'default.cfg')

# Below this the capture loop skips triggers rather than firing late.
CAPTURE_INTERVAL_MIN_SEC = 0.5

# Sony Camera Remote SDK image formats. Default deliberately does not write
# the SDK property, leaving the format selected on each camera untouched.
SONY_IMAGE_FORMAT_CONFIG_KEY = 'sony_image_format'
SONY_IMAGE_FORMAT_CAMERA_SETTING = 'Default'
SONY_IMAGE_FORMAT_JPEG = 'JPEG'
SONY_IMAGE_FORMAT_RAW = 'RAW'
SONY_IMAGE_FORMAT_CHOICES = (
    SONY_IMAGE_FORMAT_CAMERA_SETTING,
    SONY_IMAGE_FORMAT_RAW,
    SONY_IMAGE_FORMAT_JPEG,
)
SONY_IMAGE_FORMAT_FILE_TYPES = {
    SONY_IMAGE_FORMAT_JPEG: 1,
    SONY_IMAGE_FORMAT_RAW: 2,
}
# The Sony SDK uses a separate property to choose which files are transferred
# during PC-remote capture.  Zero means transfer every format produced by the
# camera, which is the only safe counterpart to "Default".
SONY_PC_IMAGE_FORMAT_FILE_TYPES = {
    SONY_IMAGE_FORMAT_CAMERA_SETTING: 0,
    SONY_IMAGE_FORMAT_JPEG: 1,
    SONY_IMAGE_FORMAT_RAW: 2,
}

MOUNT_POINT = "/mnt/ext_cam_storage"
MOUNT_POINT_SSD = "/mnt/ssd_cam_storage"
FALLBACK_TELEMETRY_DIR = "/home/radxa/SkySeeker_Data"

CAMERA_STATES = Enum("CamState", ["UNINITIALISED", "INITIALISED", "CAPTURING", 
                                  "ERROR_CONFIG", "ERROR_CAPTURE"])
CAM_MANAGER_STATES = Enum("CamManagerState", ["STOPPED", "STARTED", "ERROR_NO_CAMS", "ERROR_CONFIG", "COPYING", "LOADING_PREVIEW"])
ALTIMETER_STATE = Enum("AltiState", ["NOT_CONNECTED", "CONNECTED", "MEASURING", 
                                     "ERROR"])
