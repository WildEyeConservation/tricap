import unittest
import logging
import tempfile
import os
import pdb

from flask import url_for
from app import app
from flask_testing import TestCase
from wtforms import StringField, SelectField
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from app.views import settings

from sensors.configure import TricapConfig

from config import DEFAULT_CONFIG_FP, SERVER_LOG_DIR, CONFIG_FP

class BaseTestSettings(TestCase):
    def create_app(self):
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

    def create_temp_file(self):
        temp_fp = os.path.join(self.tempdir, str(self.temp_file_count)+'.temp')
        ftemp = open(temp_fp, 'w')
        ftemp.close()
        self.temp_file_count += 1
        return temp_fp

    def create_a_temp_config(self):
        self.temp_config_fp = os.path.join(self.tempdir, str(self.temp_file_count)+'.temp')
        with open(self.temp_config_fp, 'w') as config_file:
            config_file.write('[Tricap]\n')
            config_file.write('shutterspeed: 1/2500\n')
            config_file.write('image_capture_interval: 3.0\n')
            config_file.write('iso: 100\n')
            config_file.write('dummy nonsense: something or other\n')

        self.temp_file_count += 1

class TestSettings(BaseTestSettings):
    """Test stuff that requires modifying the config file here"""

    def test_form_creation(self):
        self.create_a_temp_config()

        with self.client:
            self.client.post(url_for('settings.settings'))
            form = settings._get_setting_form(config_fp = self.temp_config_fp)
            string_lables, select_labels = settings._get_setting_labels(form)

            self.assertEqual('shutterspeed' in select_labels, True)
            choices = form.select_settings[select_labels.index('shutterspeed')].choices
            ss_choices = [ct[1] for ct in choices]
            self.assertEqual('1/640' in ss_choices, True)

            self.assertEqual('iso' in select_labels, True)
            choices = form.select_settings[select_labels.index('iso')].choices
            iso_choices = [ct[1] for ct in choices]
            self.assertEqual('100' in iso_choices, True)

            self.assertEqual('dummy nonsense' in string_lables, True)


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


class TestBehaviourSettings(BaseTestSettings):
    """Test stuff that uses the initial config file here"""
    def test_settings_page_creation(self):
        with self.client:
            response = self.client.get(url_for('settings.settings'))

            temp_fp = self.create_temp_file()

            # dump the page contents to a file, which we can then open using selenium
            with open(temp_fp, 'wb') as temp_html_file:
                #TODO Replace the static replacement with something from config
                folder_path = b'file:///C:/Projects/IndlovuCode/tricap/Code/tricap/app/static'
                temp_html_file.write(response.data.replace(b'/static', folder_path))

            driver = webdriver.Chrome()
            driver.get("file:///"+temp_fp)

            wait = WebDriverWait(driver, 10)
            wait.until(EC.visibility_of_element_located((By.ID, "btn_test")))

            # input_fields = driver.find_elements_by_xpath("//a[contains(@class, 'form-control')]")
            input_fields = driver.find_elements_by_class_name("form-control")
            config_dict = TricapConfig(self.logger).get_dict()
            self.assertEqual(len(input_fields), len(config_dict.keys()))

            driver.quit()
