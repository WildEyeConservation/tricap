import unittest
import logging
import tempfile
import os
import pdb

from flask import url_for
from app import app
from flask_testing import TestCase

from app.views import settings

from sensors.configure import TricapConfig

from config import DEFAULT_CONFIG_FP, SERVER_LOG_DIR, CONFIG_FP

class TestViewSettings(TestCase):
# class TestViewSettings(unittest.TestCase):

    def create_app(self):
        # app.config.from_object('config.TestConfiguration')
        return app

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
        for index in range(self.temp_file_count):
            os.remove(os.path.join(self.tempdir, str(index)+'.temp'))
        os.rmdir(self.tempdir)

    def create_a_temp_config(self):
        self.temp_config_fp = os.path.join(self.tempdir, str(self.temp_file_count)+'.temp')
        with open(self.temp_config_fp, 'w') as config_file:
            config_file.write('[Tricap]\n')
            config_file.write('shutterspeed: 1/2500\n')
            config_file.write('image_capture_interval: 3.0\n')

        self.temp_file_count += 1

    def test_revert(self):
        self.create_a_temp_config()

        new_config = TricapConfig(self.logger, config_fp_to_read = self.temp_config_fp)
        new_config_dict = new_config.get_dict()
        new_config_dict['image_capture_interval'] = -99.99
        new_config.save_config_dict_to_file(new_config_dict)
        self.assertEqual(new_config.get('image_capture_interval'), '-99.99')

        default_config = TricapConfig(self.logger, config_fp_to_read = DEFAULT_CONFIG_FP)

        self.assertNotEqual(new_config.get_dict(), default_config.get_dict())

        new_config = None

        # pdb.set_trace()

        with self.client:
            self.client.post(url_for('settings.settings'))

            settings._revert_to_default_settings(save_to_fp = self.temp_config_fp)

            new_config = TricapConfig(self.logger, config_fp_to_read = self.temp_config_fp)

            self.assertEqual(new_config.get_dict(), default_config.get_dict())            
