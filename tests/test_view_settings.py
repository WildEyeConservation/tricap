import unittest
import shutil
import tempfile
import os
import pdb

# from flask_testing import TestCase

from app.views import settings
from sensors.utilities import read_init_config

from config import CONFIG_FP, DEFAULT_CONFIG_FP

# class TestViewSettings(TestCase):
class TestViewSettings(unittest.TestCase):
    # def create_app(self):
    #     app.config.from_object('config.TestConfiguration')
    #     return app

    def setUp(self):
        self.temp_file_count = 0
        self.tempdir = tempfile.mkdtemp()
        self.real_config_fp = CONFIG_FP
        self.temp_config_fp = None

    def tearDown(self):
        for index in range(self.temp_file_count):
            os.remove(os.path.join(self.tempdir, str(index)+'.temp'))
        os.rmdir(self.tempdir)

    def _create_a_temp_config(self):
        self.temp_config_fp = os.path.join(self.tempdir, str(self.temp_file_count)+'.temp')
        shutil.copyfile(self.real_config_fp, self.temp_config_fp)
        self.temp_file_count += 1
        # change the global config_fp

    def test_init(self):
        self._create_a_temp_config()

        with open(self.temp_config_fp, 'w') as tc_file:
            tc_file.write('Bogus nonsense = 23')

        new_config = read_init_config(config_fp = self.temp_config_fp)
        default_config = read_init_config(config_fp = DEFAULT_CONFIG_FP)

        self.assertNotEqual(new_config, default_config)
        
        settings._revert_to_default_settings(save_to_fp = self.temp_config_fp)

        new_config = read_init_config(config_fp = self.temp_config_fp)
        self.assertEqual(new_config, default_config)
