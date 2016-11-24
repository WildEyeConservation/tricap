""" D Joubert - 18 November 2016 - Unittest for the TriCap configure class """

import unittest
import os
import tempfile
import logging
import pdb
import shutil

from sensors.configure import TricapConfig

from config import CONFIG_FP, SERVER_LOG_DIR, RET_OK, RET_ERROR

class TestBaseConfigure(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger('test_configure')
        format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
        formatter = logging.Formatter(format_str)
        log_fp = os.path.join(SERVER_LOG_DIR, 'test_configure.log')
        handler = logging.FileHandler(filename=log_fp)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)

        self.temp_file_count = 0
        self.tempdir = tempfile.mkdtemp()
        self.real_config_fp = CONFIG_FP
        self.temp_config_fp = None

    def tearDown(self):
        for root, _, filenames in os.walk(self.tempdir):
            for filename in filenames:
                os.remove(os.path.join(root, filename))

        shutil.rmtree(self.tempdir)

    def create_a_temp_config(self):
        self.temp_config_fp = os.path.join(self.tempdir, str(self.temp_file_count)+'.temp')
        with open(self.temp_config_fp, 'w') as config_file:
            config_file.write('[Tricap]\n')
            config_file.write('shutterspeed: 1/2500\n')
            config_file.write('image_capture_interval: 3.0\n')

        self.temp_file_count += 1

class TestConfigure(TestBaseConfigure):
    def test_init(self):
        self.create_a_temp_config()
        config = TricapConfig(self.logger, config_fp_to_read = self.temp_config_fp)
        self.assertEqual(config.is_ready(), True)

    def test_value_getting(self):
        self.create_a_temp_config()
        config = TricapConfig(self.logger, config_fp_to_read = self.temp_config_fp)

        self.assertEqual(config.get('shutterspeed'), '1/2500')
        self.assertEqual(config.get('image_capture_interval', type_str=config.TYPE_STRING), '3.0')
        self.assertEqual(config.get('image_capture_interval', type_str=config.TYPE_FLOAT), 3.0)

        # bad requests
        self.assertEqual(config.get('image_capture_interval', type_str=config.TYPE_INT), None)
        self.assertEqual(config.get('shutterspeed', type_str=config.TYPE_FLOAT), None)

    def test_value_setting(self):
        self.create_a_temp_config()
        config = TricapConfig(self.logger, config_fp_to_read = self.temp_config_fp)

        config_dict = config.get_dict()
        config_dict['shutterspeed'] = '1/640'
        config_dict['image_capture_interval'] = 5.0
        self.assertEqual(config.save_config_dict_to_file(config_dict), RET_OK)

        new_config = TricapConfig(self.logger, config_fp_to_read = self.temp_config_fp)
        self.assertEqual(new_config.get('shutterspeed'), '1/640')
        self.assertEqual(new_config.get('image_capture_interval', type_str=config.TYPE_FLOAT), 5.0)
