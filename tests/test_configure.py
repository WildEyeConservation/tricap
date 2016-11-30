""" D Joubert - 18 November 2016 - Unittest for the TriCap configure class """

import logging
import os
import shutil
import tempfile
import unittest
import pdb
import configparser

from config import CONFIG_FP, SERVER_LOG_DIR, RET_OK
from sensors.configure import TricapConfig, TricapConfigError

class TestBaseConfigure(unittest.TestCase):

    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    handler = logging.FileHandler(filename=os.path.join(SERVER_LOG_DIR, 'test_configure.log'))
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(format_str))
    handler.addFilter(logging.Filter(name='sensors.configure'))
    rootLogger = logging.getLogger('')
    rootLogger.addHandler(handler)
    rootLogger.setLevel(logging.DEBUG)

    def setUp(self):
        # backup the actual initial.cfg
        self.tempdir = tempfile.mkdtemp()
        self.bk_config_fp = os.path.join(self.tempdir, 'initial.cfg_bk')
        shutil.copyfile(CONFIG_FP, self.bk_config_fp)

    def tearDown(self):
        # copy back the initial.cfg
        shutil.copyfile(self.bk_config_fp, CONFIG_FP)

        for root, _, filenames in os.walk(self.tempdir):
            for filename in filenames:
                os.remove(os.path.join(root, filename))

        shutil.rmtree(self.tempdir)

class TestConfigure(TestBaseConfigure):
    def test_init(self):
        config = TricapConfig()
        self.assertEqual(config.is_ready(), True)

    def test_bad_config_fp(self):
        """ Tests whether the correct error behaviour is obtained when something goes wrong with
            reading the config file. Which in this case, is to throw an exception."""
        with self.assertRaises(Exception):
            TricapConfig(config_fp_to_read='/I/Dont/Exist.cfg')

        config = TricapConfig()
        with self.assertRaises(Exception):
            config.save_to_file(config_fp='/I/Dont/Exist.cfg')

    def test_bad_section_header(self):
        """ Check response on using a non-existent header. """
        config = TricapConfig()
        with self.assertRaises(configparser.Error):
            config.get_section_dict('BadHeader')

        with self.assertRaises(KeyError):
            config.get('shutterspeed', 'BadHeader')

        camera_dict = config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
        with self.assertRaises(KeyError):
            config.set_section(camera_dict, 'BadHeader')

    def test_setting_non_existent_setting(self):
        """ If a setting is not in the original config file, it should be rejected """
        config = TricapConfig()
        camera_dict = config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
        camera_dict['NotPreExisting'] = 42
        with self.assertRaises(TricapConfigError):
            config.set_section(camera_dict, TricapConfig.CAMERA_SECTION_HEADER)

    def test_value_getting(self):
        config = TricapConfig()

        # get the values manually
        with open(CONFIG_FP) as config_file:
            for line in config_file:
                if ':' in line or '=' in line:
                    parts = line.split(':')
                    if parts[0].strip() == 'shutterspeed':
                        ss_string = parts[1].strip()
                    elif parts[0].strip() == 'image_capture_interval':
                        ici_string = parts[1].strip()
                    elif parts[0].strip() == 'num_frames_to_avg':
                        num_frames_string = parts[1].strip()

        self.assertEqual(config.get('shutterspeed', TricapConfig.CAMERA_SECTION_HEADER), ss_string)
        self.assertEqual(config.get('image_capture_interval', TricapConfig.MISC_SECTION_HEADER,
                                    type_str=config.TYPE_STRING), ici_string)
        self.assertEqual(config.get('image_capture_interval', TricapConfig.MISC_SECTION_HEADER,
                                    type_str=config.TYPE_FLOAT), float(ici_string))
        self.assertEqual(config.get('num_frames_to_avg', TricapConfig.ALTI_SECTION_HEADER,
                                    type_str=config.TYPE_INT), int(num_frames_string))

        # bad requests
        with self.assertRaises(ValueError):
            config.get('shutterspeed', TricapConfig.CAMERA_SECTION_HEADER,
                       type_str=config.TYPE_FLOAT)
        with self.assertRaises(ValueError):
            config.get('shutterspeed', TricapConfig.CAMERA_SECTION_HEADER,
                       type_str=config.TYPE_INT)


    def test_value_setting(self):
        config = TricapConfig()

        section_dict = config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
        section_dict['shutterspeed'] = '1/640'
        section_dict['iso'] = '200'

        # Not checking for indications from the functions itself if there was an error, the
        #  assumptions is that if there was an error, an exception would have been thrown.
        config.set_section(section_dict, TricapConfig.CAMERA_SECTION_HEADER)
        config.save_to_file()

        new_config = TricapConfig()
        self.assertEqual(new_config.get('shutterspeed', TricapConfig.CAMERA_SECTION_HEADER),
                         '1/640')
        self.assertEqual(new_config.get('iso',
                                        TricapConfig.CAMERA_SECTION_HEADER,
                                        type_str=config.TYPE_FLOAT), 200.0)
