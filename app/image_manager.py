import subprocess32
import os

from config import TRICAP_CAMS_MANAGER_STATES

class DummyImageManager(object):
    def __init__(self):
        self.state = 0

    def is_cam_image_fresh(self, cam_num):
        return True

    def get_cam_image_fp(self, cam_num):
        # dd_fp = '/home/deon/tmp/deepdream/frame'+str(self.state) + '.jpg'
        self.state += 1

        if self.state > 9:
            self.state = 0

        dd_fp = 'C:/Users/Public/Pictures/Sample Pictures/Jellyfish.jpg'

        return dd_fp


class DummyTricapManager(object):
    def __init__(self, num_cams):
        self._num_cams = num_cams
        self.state = TRICAP_CAMS_MANAGER_STATES.STOPPED

    def start_capturing(self):
        self.state = TRICAP_CAMS_MANAGER_STATES.STARTED

    def stop_capturing(self):
        self.state = TRICAP_CAMS_MANAGER_STATES.STOPPED

    def get_cam_fp_queue(self):
        return None

    def get_num_cams(self):
        return self._num_cams


class QueueImageManager(object):
    # The point of the Queue Image Manager is to process the queue and keep track of the latest image for each camera
    def __init__(self, cam_fp_queue):
        self._cam_fp_queue = cam_fp_queue
        self._cam_fps = {}
        self._last_provided_cam_fps = {}

    def _process_queue(self):
        while self._cam_fp_queue.empty() is False:
            cam_num_fp_tuple = self._cam_fp_queue.get()
            self._cam_fps[str(cam_num_fp_tuple[0])] = cam_num_fp_tuple[1]
            self._cam_fp_queue.task_done()

    def is_cam_image_fresh(self, cam_num):
        self._process_queue()

        if len(self._cam_fps.keys()) == 0:
            return False

        if str(cam_num) not in self._last_provided_cam_fps:
            return True

        if self._last_provided_cam_fps[str(cam_num)] == self._cam_fps[str(cam_num)]:
            return False
        else:
            return True

    def get_cam_image_fp(self, cam_num):
        if str(cam_num) in self._cam_fps:
            print 'Returning queue item : ' + self._cam_fps[str(cam_num)]

            dir_with_filename, ext = os.path.splitext(self._cam_fps[str(cam_num)])

            if ext.lower() == '.cr2':
                subprocess32.check_output(["ufraw-batch", "--silent", "--overwrite", "--rotate=no", "--out-type=jpg",
                                           "--size=640",
                                           self._cam_fps[str(cam_num)]])

            self._last_provided_cam_fps[str(cam_num)] = self._cam_fps[str(cam_num)]

            return dir_with_filename + '.JPG'
        else:
            return None
