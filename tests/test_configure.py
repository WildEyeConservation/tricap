"""Unittest for the TriCap configure class."""

import logging
import os
import configparser

from config import (
    CONFIG_FP,
    SERVER_LOG_DIR,
    SONY_IMAGE_FORMAT_CAMERA_SETTING,
    SONY_IMAGE_FORMAT_CONFIG_KEY,
)
from support.configure import TricapConfig, TricapConfigError

from .tricap_tempfile_test_case import TriCapTempFilerTestCase


class TestConfigure(TriCapTempFilerTestCase):
    """Child of TricapTempFilerTestCase, with logging of only the configure module."""

    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    handler = logging.FileHandler(filename=os.path.join(SERVER_LOG_DIR, 'test_configure.log'))
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(format_str))
    handler.addFilter(logging.Filter(name='sensors.configure'))
    rootLogger = logging.getLogger('')
    rootLogger.addHandler(handler)
    rootLogger.setLevel(logging.DEBUG)

    def test_init(self):
        """Test if the config can read from file, instantiate itself correctly."""
        config = TricapConfig()
        self.assertEqual(config.is_ready(), True)

    def test_old_config_defaults_to_camera_image_format(self):
        """Older configs should leave the Sony camera's format untouched."""
        old_config_fp = os.path.join(self.tempdir, 'old.cfg')
        with open(old_config_fp, 'w') as old_config:
            old_config.write('[Camera]\nshutterspeed = 1/2500\n')

        config = TricapConfig(config_fp_to_read=old_config_fp)

        self.assertEqual(
            config.get(
                SONY_IMAGE_FORMAT_CONFIG_KEY,
                TricapConfig.CAMERA_SECTION_HEADER,
            ),
            SONY_IMAGE_FORMAT_CAMERA_SETTING,
        )

    def test_bad_config_fp(self):
        """Test whether an exception is thrown when file reading/writing error occurs."""
        with self.assertRaises(Exception):
            TricapConfig(config_fp_to_read='/I/Dont/Exist.cfg')

        config = TricapConfig()
        with self.assertRaises(Exception):
            config.save_to_file(config_fp='/I/Dont/Exist.cfg')

    def test_bad_section_header(self):
        """Check response on using a non-existent header."""
        config = TricapConfig()
        with self.assertRaises(configparser.Error):
            config.get_section_dict('BadHeader')

        with self.assertRaises(KeyError):
            config.get('shutterspeed', 'BadHeader')

        camera_dict = config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
        with self.assertRaises(KeyError):
            config.set_section(camera_dict, 'BadHeader')

    def test_setting_non_existent_setting(self):
        """If a setting is not in the original config file, it should be rejected."""
        config = TricapConfig()
        camera_dict = config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
        camera_dict['NotPreExisting'] = 42
        with self.assertRaises(TricapConfigError):
            config.set_section(camera_dict, TricapConfig.CAMERA_SECTION_HEADER)

    def test_value_getting(self):
        """Test if we get a correct value."""
        config = TricapConfig()

        # get the values manually
        with open(CONFIG_FP) as config_file:
            for line in config_file:
                line = line.replace('=', ':')
                if ':' in line:
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
        """Test if we set a value correctly."""
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
