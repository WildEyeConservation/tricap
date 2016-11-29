""" D Joubert - 18 November 2016 - Unittest for the TriCap configure class """

import logging
import os
import shutil
import tempfile
import unittest

from config import CONFIG_FP, SERVER_LOG_DIR, RET_OK
from sensors.configure import TricapConfig


class TestBaseConfigure(unittest.TestCase):
    logger = logging.getLogger('test_configure')
    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    formatter = logging.Formatter(format_str)
    log_fp = os.path.join(SERVER_LOG_DIR, 'test_configure.log')
    handler = logging.FileHandler(filename=log_fp)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
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

    def test_value_getting(self):
        config = TricapConfig()

        # get the values manually
        with open(CONFIG_FP) as config_file:
            for line in config_file:
                if ':' in line:
                    parts = line.split(':')
                    if parts[0].strip() == 'shutterspeed':
                        ss_string = parts[1].strip()
                    elif parts[0].strip() == 'image_capture_interval':
                        ici_string = parts[1].strip()

        self.assertEqual(config.get('shutterspeed', TricapConfig.CAMERA_SECTION_HEADER), ss_string)
        self.assertEqual(config.get('image_capture_interval', TricapConfig.MISC_SECTION_HEADER,
                                    type_str=config.TYPE_STRING), ici_string)
        self.assertEqual(config.get('image_capture_interval', TricapConfig.MISC_SECTION_HEADER,
                                    type_str=config.TYPE_FLOAT), float(ici_string))

        # bad requests
        self.assertEqual(config.get('shutterspeed', TricapConfig.CAMERA_SECTION_HEADER,
                         type_str=config.TYPE_FLOAT), None)

    def test_value_setting(self):
        config = TricapConfig()

        section_dict = config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
        section_dict['shutterspeed'] = '1/640'
        section_dict['iso'] = '200'

        self.assertEqual(config.set_section(section_dict, TricapConfig.CAMERA_SECTION_HEADER),
                                            RET_OK)
        self.assertEqual(config.save_to_file(), RET_OK)

        new_config = TricapConfig()
        self.assertEqual(new_config.get('shutterspeed', TricapConfig.CAMERA_SECTION_HEADER),
                         '1/640')
        self.assertEqual(new_config.get('iso',
                                        TricapConfig.CAMERA_SECTION_HEADER,
                                        type_str=config.TYPE_FLOAT), 200.0)
