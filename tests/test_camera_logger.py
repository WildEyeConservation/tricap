"""Unit test for the camera logger."""

import os
from time import sleep
from unittest import TestCase
from support.basic import Subject
from sensors.camera_logger import cameraLoggingObserver
from config import SERVER_LOG_DIR


class BogusCamera(Subject):
    """docstring for test_camera."""

    def __init__(self):
        """Constructor."""
        super(BogusCamera, self).__init__()
        self.update_message = 'test camera update message.'
        self.im_count = 0

    def get_cam_image_count(self):
        """Return bogus image count, incremented everytime this function is called."""
        val = self.im_count
        self.im_count += 1
        return val


class TestCameraLoggingObserver(TestCase):
    """Test class for cameraLoggingObserver."""

    def test_logging(self):
        """Check the logging."""
        bc = BogusCamera()

        log_fp = os.path.join(SERVER_LOG_DIR, 'test_cam_logger.log')

        if os.path.isfile(log_fp) is True:
            os.remove(log_fp)

        cam_logger = cameraLoggingObserver(log_fp=log_fp, subject_cameras=bc)

        bc.notify()
        sleep(1)
        bc.notify()
        sleep(1)
        bc.notify()
        sleep(1)

        with open(log_fp, 'r') as log_file:
            lines = log_file.readlines()
            self.assertEqual(len(lines), 4)

        del cam_logger
