"""Various tests to do with the settings page."""

import logging
import os

from flask import url_for
from selenium.webdriver.support.ui import Select

from app.views import settings

from support.configure import TricapConfig

from .tricap_tempfile_test_case import TriCapTempFilerTestCase
from .tricap_flask_test_case import TriCapAppTestCase, TriCapBehaviourTestCase

from config import DEFAULT_CONFIG_FP, SERVER_LOG_DIR


class TestSettings(TriCapAppTestCase):
    """Test stuff that requires modifying the config file here.

    We have more control when calling the functions directly than when accessing the page through
    Selenium, i.e. during behaviour testing.
    """

    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    handler = logging.FileHandler(filename=os.path.join(SERVER_LOG_DIR, 'test_settings.log'))
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(format_str))
    rootlogger = logging.getLogger('')
    rootlogger.addHandler(handler)
    rootlogger.setLevel(logging.DEBUG)

    def test_form_creation(self):
        """Test if the form is created with correct number of fields."""
        with self.client:  # access the web page through a 'client', as if a browser
            self.client.get(url_for('settings.settings'))
            form = settings.get_form_for_display()

            # check that the shutterspeed setting was correctly instantiated
            labels = [cam_select.label for cam_select in form.cam_selects]
            self.assertEqual('shutterspeed' in labels, True)
            choices = form.cam_selects[labels.index('shutterspeed')].choices
            ss_choices = [ct[1] for ct in choices]
            self.assertEqual('1/640' in ss_choices, True)

            # check that the iso setting was correctly instantiated
            self.assertEqual('iso' in labels, True)
            choices = form.cam_selects[labels.index('iso')].choices
            iso_choices = [ct[1] for ct in choices]
            self.assertEqual('100' in iso_choices, True)

            self.assertEqual('sony_image_format' in labels, True)
            choices = form.cam_selects[labels.index('sony_image_format')].choices
            image_format_choices = [ct[1] for ct in choices]
            self.assertEqual(
                image_format_choices,
                ['Default', 'RAW', 'JPEG'],
            )

            labels = [misc_string.label for misc_string in form.misc_strings]
            self.assertEqual('session_description' in labels, True)

    def test_revert(self):
        """Test if the rever button correctly restored the config file to default."""
        # create a new config file, change it and save it
        new_config = TricapConfig()
        section_dict = new_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
        section_dict['image_capture_interval'] = -99.99
        new_config.set_section(section_dict, TricapConfig.MISC_SECTION_HEADER)
        new_config.save_to_file()
        self.assertEqual(new_config.get('image_capture_interval', TricapConfig.MISC_SECTION_HEADER),
                         '-99.99')

        # load the default
        default_config = TricapConfig(config_fp_to_read=DEFAULT_CONFIG_FP)
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


class TestMiscSettings(TriCapTempFilerTestCase):
    """Test the misc settings handler used in the settings view."""

    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    handler = logging.FileHandler(filename=os.path.join(SERVER_LOG_DIR, 'test_settings.log'))
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(format_str))
    rootlogger = logging.getLogger('')
    rootlogger.addHandler(handler)
    rootlogger.setLevel(logging.DEBUG)

    def test_set_and_get_settings(self):
        """Test the getting and setting of settings."""
        misc_handler = settings.MiscSettingHandler()
        misc_handler.config['session_description'] = 'test_misc_handler'
        self.assertEqual(misc_handler.config['session_description'], 'test_misc_handler')

        misc_handler.config['image_capture_interval'] = '-99.99'
        self.assertEqual(misc_handler.config['image_capture_interval'], '-99.99')

        with self.assertRaises(KeyError):
            misc_handler.config['non_existent'] = -1


class TestBehaviourSettings(TriCapBehaviourTestCase):
    """Test stuff that needs interaction from a browser here."""

    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    handler = logging.FileHandler(filename=os.path.join(SERVER_LOG_DIR, 'test_settings.log'))
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(format_str))
    rootlogger = logging.getLogger('')
    rootlogger.addHandler(handler)
    rootlogger.setLevel(logging.DEBUG)

    def test_page(self):
        """Test that the settings page has the correct number of fields."""
        with self.client:  # access the web page through a 'client', as if a browser
            self.open_page('settings.settings', 'btn_save')            

            # Check that all the config fields have been created
            new_config = TricapConfig()
            num_fields = 0
            for sh in TricapConfig.SECTION_HEADERS:
                section_dict = new_config.get_section_dict(sh)
                num_fields += len(section_dict.keys())

            input_fields = self.driver.find_elements_by_class_name("form-control")
            self.assertEqual(len(input_fields), num_fields)

    def test_save(self):
        """Test the save button."""
        with self.client:  # access the web page through a 'client', as if a browser
            self.open_page('settings.settings', 'btn_save')

            config = TricapConfig()
            new_ss = '1/2500'
            if config.get('shutterspeed', TricapConfig.CAMERA_SECTION_HEADER) == new_ss:
                new_ss = '1/4'  # pragma: no cover

            new_iso = '500'
            if config.get('iso', TricapConfig.CAMERA_SECTION_HEADER) == new_iso:
                new_iso = '100'  # pragma: no cover

            new_ici = '5.0'
            if config.get('image_capture_interval', TricapConfig.MISC_SECTION_HEADER) == new_ici:
                new_ici = '9.0'  # pragma: no cover

            # Change settings on the form
            ss_select = Select(self.driver.find_element_by_css_selector("[id$='shutterspeed']"))
            ss_select.select_by_visible_text(new_ss)

            iso_select = Select(self.driver.find_element_by_css_selector("[id$='iso']"))
            iso_select.select_by_visible_text(new_iso)

            ici_string = self.driver.find_element_by_css_selector("[id$='image_capture_interval']")
            ici_string.clear()
            ici_string.send_keys(new_ici)

            # simulate posting the data through the save button
            form_data = self.get_form_data_as_dict(self.driver)

            form_data['save'] = 'Save'

            self.client.post(url_for('settings.settings'), data=form_data, follow_redirects=True)

            new_config = TricapConfig()
            section_dict = new_config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
            self.assertEqual(section_dict['shutterspeed'], new_ss)
            self.assertEqual(section_dict['iso'], new_iso)
            section_dict = new_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
            self.assertEqual(section_dict['image_capture_interval'], new_ici)

    def test_revert_button(self):
        """Test the revert button."""
        # create a new config file, change it and save it
        new_config = TricapConfig()
        section_dict = new_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
        section_dict['image_capture_interval'] = -99.99
        new_config.set_section(section_dict, TricapConfig.MISC_SECTION_HEADER)
        new_config.save_to_file()
        self.assertEqual(new_config.get('image_capture_interval', TricapConfig.MISC_SECTION_HEADER),
                         '-99.99')

        # load the default
        default_config = TricapConfig(config_fp_to_read=DEFAULT_CONFIG_FP)
        self.assertNotEqual(new_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER),
                            default_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER))

        with self.client:
            self.open_page('settings.settings', 'btn_save')

            # simulate posting the data through the revert button
            form_data = self.get_form_data_as_dict(self.driver)
            form_data['revert'] = 'Revert'
            self.client.post(url_for('settings.settings'), data=form_data, follow_redirects=True)

            # check that the config file was overwritten with the default values
            new_config = None
            new_config = TricapConfig()
            self.assertEqual(new_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER),
                             default_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER))
