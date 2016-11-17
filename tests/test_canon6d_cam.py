"""D Joubert - 16 November 2016 - Test the tricap camera"""

import unittest
import logging
import os
import pdb

from time import sleep

from sensors.cameras import Canon6DCam

from config import CAMERA_STATES, SERVER_LOG_DIR, RET_OK, RET_ERROR

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

        self.context = gp.Context()

    def test_init(self):
        # Some kind of issue with the gp objects here, so I need to do this before every test :-(
        port_info_list = gp.PortInfoList()
        port_info_list.load()
        port_info = None
        for name, addr in self.context.camera_autodetect():
            if name == "Canon EOS 6D":
                idx = port_info_list.lookup_path(addr)
                port_info = port_info_list[idx]
                break

        cam = Canon6DCam(self.context, port_info, self.logger)

        self.assertEqual(cam.state, CAMERA_STATES.INITIALISED)

    # def test_set_shutterspeed(self):
    #     port_info_list = gp.PortInfoList()
    #     port_info_list.load()
    #     context = gp.Context()
    #     port_info = None
    #     for name, addr in context.camera_autodetect():
    #         if name == "Canon EOS 6D":
    #             idx = port_info_list.lookup_path(addr)
    #             port_info = port_info_list[idx]
    #             break
    #     cam = Canon6DCam(context, port_info, self.logger)
    #
    #     cam.set_shutterspeed('1/4')
    #     self.assertEqual(cam.get_shutter_speed_as_string(), '1/4')
    #
    #     ret_val = cam.set_shutterspeed('1/5')
    #     self.assertEqual(ret_val, RET_ERROR)
    #     self.assertEqual(cam.get_shutter_speed_as_string(), '1/4')
