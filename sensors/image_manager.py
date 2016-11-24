""" D Joubert - 17 November 2016 - Innoventix Consulting
    Image Manager, handles images taken from cameras for the webserver"""

import os

import hashlib

from abc import ABCMeta, abstractmethod

from config import CAM_MANAGER_STATES, DUMMY_IMAGE_PATH
from config import DISPLAY_DOWNLOAD_DIR, CAM_IMAGE_PREFIX


class ImageManager():
    """Abstract class all Image Managers should inherit. An ImageManager checks the freshness of
    images from multiple cameras and gives the full paths to those images."""
    __metaclass__ = ABCMeta

    def __init__(self):
        pass

    @abstractmethod
    def is_cam_image_fresh(self, cam_num):
        pass

    @abstractmethod
    def get_cam_image_fp(self, cam_num):
        pass


class DummyImageManager(ImageManager):
    """A dummy image manager, which returns a path to the same default image"""

    def __init__(self):
        ImageManager.__init__(self)

    def is_cam_image_fresh(self, cam_num):
        return True

    def get_cam_image_fp(self, cam_num):
        return DUMMY_IMAGE_PATH


class SameFileImageManager(ImageManager):
    """ An ImageManager which assumes each camera has a single image which it is constantly
    updating/replacing."""

    def __init__(self):
        ImageManager.__init__(self)
        self._image_hashes = {}

    def is_cam_image_fresh(self, cam_num):
        cam_image_fp = os.path.join(DISPLAY_DOWNLOAD_DIR, CAM_IMAGE_PREFIX + str(cam_num) + '.JPG')
        if os.path.isfile(cam_image_fp) is False:
            return False

        image_hash = hashlib.sha1(open(cam_image_fp, 'rb').read()).hexdigest()

        if str(cam_num) in list(self._image_hashes.keys()):
            if self._image_hashes[str(cam_num)] == image_hash:
                return False

        self._image_hashes[str(cam_num)] = image_hash
        return True

    def get_cam_image_fp(self, cam_num):
        cam_image_fp = os.path.join(DISPLAY_DOWNLOAD_DIR, CAM_IMAGE_PREFIX + str(cam_num) + '.JPG')
        if os.path.isfile(cam_image_fp) is False:
            return None
        else:
            return cam_image_fp

# Recode the queue image manager to use the base ImageManager abstract class, if we think it one
#  day necessary

# class QueueImageManager(object):
#     # The point of the Queue Image Manager is to process the queue and keep track of the latest image for each camera
#     def __init__(self, cam_fp_queue):
#         self._cam_fp_queue = cam_fp_queue
#         self._cam_fps = {}
#         self._last_provided_cam_fps = {}
#
#     def _process_queue(self):
#         while self._cam_fp_queue.empty() is False:
#             cam_num_fp_tuple = self._cam_fp_queue.get()
#             self._cam_fps[str(cam_num_fp_tuple[0])] = cam_num_fp_tuple[1]
#             self._cam_fp_queue.task_done()
#
#     def is_cam_image_fresh(self, cam_num):
#         self._process_queue()
#
#         if len(list(self._cam_fps.keys())) == 0:
#             return False
#
#         if str(cam_num) not in self._last_provided_cam_fps:
#             return True
#
#         if self._last_provided_cam_fps[str(cam_num)] == self._cam_fps[str(cam_num)]:
#             return False
#         else:
#             return True
#
#     def get_cam_image_fp(self, cam_num):
#         if str(cam_num) in self._cam_fps:
#             print('Returning queue item : ' + self._cam_fps[str(cam_num)])
#
#             dir_with_filename, ext = os.path.splitext(self._cam_fps[str(cam_num)])
#
#             self._last_provided_cam_fps[str(cam_num)] = self._cam_fps[str(cam_num)]
#
#             return dir_with_filename + '.JPG'
#         else:
#             return None
