"""D Joubert - 16 November 2016 - Test the tricap camera"""

import unittest
import logging
import os
import threading

from time import sleep

from sensors.cameras import Canon6DCam

from config import CAMERA_STATES, SERVER_LOG_DIR, RET_OK, RET_ERROR

try:
    import gphoto2 as gp
    GPHOTO2_IMPORTED = True
except ImportError:
    GPHOTO2_IMPORTED = False

class TestBaseCanon6DCam(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger('test_canon6d_log')
        format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
        formatter = logging.Formatter(format_str)
        log_fp = os.path.join(SERVER_LOG_DIR, 'test_canon6d.log')
        handler = logging.FileHandler(filename=log_fp)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)

        self.context = gp.Context()

        self.port_info_list = gp.PortInfoList()
        self.port_info_list.load()
        self.port_info = None
        for name, addr in self.context.camera_autodetect():
            if name == "Canon EOS 6D":
                idx = self.port_info_list.lookup_path(addr)
                self.port_info = self.port_info_list[idx]
                break

class TestDeviceCanon6DCam(TestBaseCanon6DCam):

    def test_init(self):
        cam = Canon6DCam(self.context, self.port_info, self.logger)

        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)

    def test_set_shutterspeed(self):
        cam = Canon6DCam(self.context, self.port_info, self.logger)

        self.assertEqual(cam.set_setting('shutterspeed', '1/640'), RET_OK)
        self.assertEqual(cam.get_setting('shutterspeed'), '1/640')

        self.assertEqual(cam.set_setting('shutterspeed', '1/X'), RET_ERROR)
        self.assertEqual(cam.get_setting('shutterspeed'), '1/640')

    def test_capture_func(self):
        cam = Canon6DCam(self.context, self.port_info, self.logger)
        thread_worker = cam.create_single_capture_func()
        self.assertEqual(thread_worker(0), RET_OK)

    def test_cap_func_as_thread(self):
        cam = Canon6DCam(self.context, self.port_info, self.logger)
        thread = threading.Thread(target=cam.create_single_capture_func(),
                                  args=[0])
        thread.start()
        thread.join()
        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)

    def test_setting_iso(self):
        cam = Canon6DCam(self.context, self.port_info, self.logger)
        cam.set_setting('iso', '100')
        self.assertEqual(cam.get_setting('iso'), '100')
        cam.set_setting('iso', '200')
        self.assertEqual(cam.get_setting('iso'), '200')

class TestInteractiveCanon6DCam(TestBaseCanon6DCam):
    def test_cable_remove(self):
        input('Press enter to conduct cable remove test')
        cam = Canon6DCam(self.context, self.port_info, self.logger)
        thread_worker = cam.create_single_capture_func()
        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)

        print('Remove the cable - you have 2 seconds')
        sleep(2)
        self.assertEqual(thread_worker(0), RET_ERROR)
