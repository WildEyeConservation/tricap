"""D Joubert - 16 November 2016 - Test the tricap camera"""

import unittest
import logging
import os

from time import sleep

from app.cameras import Canon6DCam

from config import CAMERA_STATES, SERVER_LOG_DIR

try:
    import gphoto2 as gp
    GPHOTO2_IMPORTED = True
except ImportError:
    GPHOTO2_IMPORTED = False

class TestDeviceCanon6DCam(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger('test_canon6d_log')
        format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
        formatter = logging.Formatter(format_str)
        log_fp = os.path.join(SERVER_LOG_DIR, 'test_canon6d.log')
        handler = logging.FileHandler(filename=log_fp)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        port_info_list = gp.PortInfoList()
        port_info_list.load()

        context = gp.Context()

        port_info = None
        for name, addr in self._context.camera_autodetect():
            if name == "Canon EOS 6D":
                idx = port_info_list.lookup_path(addr)
                port_info = port_info_list[idx]

        self.cam = Canon6DCam(context, port_info, self.logger)

    def test_init(self):
        self.assertEqual(self.cam.state, CAMERA_STATES.INITIALISED)

    def test_set_shutterspeed(self):
        self.cam.set_shutterspeed('1/4')
        self.assertEqual(self.get_shutter_speed_as_string, '1/4')

        self.cam.set_shutterspeed('1/5')
        self.assertEqual(self.cam.state, CAMERA_STATES.ERROR_CONFIG)
