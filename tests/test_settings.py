import unittest
import logging
import tempfile
import os
import pdb
import shutil

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

from config import DEFAULT_CONFIG_FP, SERVER_LOG_DIR, CONFIG_FP, TEST_STATIC_DIR, SERVER_LOG_NAME

# TODO Create a temp file test base class, from which all tests can inherit that uses temp files
# TODO Remove all old style tearDowns (i.e. with file counting), temp_file_counts

class BaseTestSettings(TestCase):

    logger = logging.getLogger(SERVER_LOG_NAME)
    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    formatter = logging.Formatter(format_str)
    log_fp = os.path.join(SERVER_LOG_DIR, 'test_settings.log')
    handler = logging.FileHandler(filename=log_fp)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    rootlogger = logging.getLogger('')
    rootlogger.addHandler(handler)
    rootlogger.setLevel(logging.DEBUG)

    def create_app(self):
        app.config['WTF_CSRF_ENABLED'] = False
        return app

    def setUp(self):
        # backup the actual initial.cfg
        self.tempdir = tempfile.mkdtemp()
        self.bk_config_fp = os.path.join(self.tempdir, 'initial.cfg_bk')
        shutil.copyfile(CONFIG_FP, self.bk_config_fp)

        self.temp_file_count = 0

    def tearDown(self):
        # copy back the initial.cfg
        shutil.copyfile(self.bk_config_fp, CONFIG_FP)

        for root, _, filenames in os.walk(self.tempdir):
            for filename in filenames:
                os.remove(os.path.join(root, filename))

        shutil.rmtree(self.tempdir)

    def create_temp_file(self):
        temp_fp = os.path.join(self.tempdir, str(self.temp_file_count) + '.temp')
        ftemp = open(temp_fp, 'w')
        ftemp.close()
        self.temp_file_count += 1
        return temp_fp

class TestSettings(BaseTestSettings):
    """Test stuff that requires modifying the config file here, as we have more control when
    calling the functions directly than when accessing the page through Selenium, i.e. during
    behaviour testing."""

    def test_form_creation(self):
        with self.client: # access the web page through a 'client', as if a browser
            self.client.get(url_for('settings.settings'))
            form = settings.get_form_for_display()

            # check that the shutterspeed setting was correctly instantiated
            labels = [cam_select.label for cam_select in form.cam_selects]
            print(labels)
            self.assertEqual('shutterspeed' in labels, True)
            choices = form.cam_selects[labels.index('shutterspeed')].choices
            ss_choices = [ct[1] for ct in choices]
            self.assertEqual('1/640' in ss_choices, True)

            # check that the iso setting was correctly instantiated
            self.assertEqual('iso' in labels, True)
            choices = form.cam_selects[labels.index('iso')].choices
            iso_choices = [ct[1] for ct in choices]
            self.assertEqual('100' in iso_choices, True)

            labels = [misc_string.label for misc_string in form.misc_strings]
            self.assertEqual('session_description' in labels, True)

    def test_revert(self):
        # create a new config file, change it and save it
        new_config = TricapConfig()
        section_dict = new_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
        section_dict['image_capture_interval'] = -99.99
        new_config.set_section(section_dict, TricapConfig.MISC_SECTION_HEADER)
        new_config.save_to_file()
        self.assertEqual(new_config.get('image_capture_interval', TricapConfig.MISC_SECTION_HEADER),
                        '-99.99')

        # load the default
        default_config = TricapConfig(config_fp_to_read = DEFAULT_CONFIG_FP)
        self.assertNotEqual(new_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER),
                            default_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER))

        with self.client:
            self.client.get(url_for('settings.settings'))

            # revert to the default settings
            settings.revert_to_default_settings()

            # check that the config file was overwritten with the default values
            new_config = None
            new_config = TricapConfig()
            self.assertEqual(new_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER),
                             default_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER))

class TestBehaviourSettings(BaseTestSettings):
    """Test stuff that needs interaction from a browser here."""

    def _get_form_data_as_dict(self, driver):
        serial_str = driver.execute_script('return $("form").serialize()')

        ret_dict = {}
        serial_parts = serial_str.split('&')
        for part in serial_parts:
            eq_parts = part.split('=')
            ret_dict[eq_parts[0]] = eq_parts[1]

        return ret_dict

    def test_page(self):
        with self.client:  # access the web page through a 'client', as if a browser
            response = self.client.get(url_for('settings.settings'))

            # Dump the page contents to a temp file, which we can then open using selenium. We have
            #  replace the /static relative paths with absolute paths to get this to work
            temp_fp = self.create_temp_file()
            with open(temp_fp, 'wb') as temp_html_file:
                temp_html_file.write(response.data.replace(b'/static', TEST_STATIC_DIR))

            # display = Display(visible=0, size=(800,600))
            # display.start()

            # Open the dumped page using chrome (through Selenium) and
            #  wait untill the page has finished loading
            driver = webdriver.Chrome()#executable_path='/usr/lib/chromium-browser/chromedriver')
            driver.get("file:///"+temp_fp)
            wait = WebDriverWait(driver, 10)
            wait.until(EC.visibility_of_element_located((By.ID, "btn_test")))

            # Check that all the config fields have been created
            new_config = TricapConfig()
            section_dict = new_config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
            num_fields = len(section_dict.keys())
            section_dict = new_config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)
            num_fields += len(section_dict.keys())
            section_dict = new_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
            num_fields += len(section_dict.keys())

            input_fields = driver.find_elements_by_class_name("form-control")
            self.assertEqual(len(input_fields), num_fields)

            driver.quit()

    def test_save(self):
        with self.client:  # access the web page through a 'client', as if a browser
            response = self.client.get(url_for('settings.settings'))

            temp_fp = self.create_temp_file()
            with open(temp_fp, 'wb') as temp_html_file:
                temp_html_file.write(response.data.replace(b'/static', TEST_STATIC_DIR))

            driver = webdriver.Chrome()
            driver.get("file:///"+temp_fp)
            wait = WebDriverWait(driver, 10)
            wait.until(EC.visibility_of_element_located((By.ID, "btn_test")))

            # Change settings on the form
            ss_select = Select(driver.find_element_by_id('shutterspeed'))
            ss_select.select_by_visible_text("1/2500")

            iso_select = Select(driver.find_element_by_id('iso'))
            iso_select.select_by_visible_text("500")

            ici_string = driver.find_element_by_id('image_capture_interval')
            ici_string.clear()
            ici_string.send_keys('9.0')

            # simulate posting the data through the save button
            form_data = self._get_form_data_as_dict(driver)
            print(form_data)

            form_data['save'] = 'Save'
            response = self.client.post(url_for('settings.settings'),
                                        data=form_data,
                                        follow_redirects=True)

            # check that the data has changed
            # get the values manually
            with open(CONFIG_FP) as config_file:
                for line in config_file:
                    if ':' in line:
                        parts = line.split(':')
                        key = parts[0].strip()
                        value = parts[1].strip()
                        if key == 'shutterspeed':
                            ss_string = value
                        elif key == 'image_capture_interval':
                            ici_string = value
                        elif key == 'iso':
                            iso_string = value

            new_config = TricapConfig()
            section_dict = new_config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
            self.assertEqual(section_dict['shutterspeed'], ss_string)
            self.assertEqual(section_dict['iso'], iso_string)
            section_dict = new_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
            self.assertEqual(section_dict['image_capture_interval'], ici_string)

            driver.quit()
