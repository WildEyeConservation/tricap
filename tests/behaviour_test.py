"""Base class for all behaviour tests."""

import tempfile
import os
import shutil

from flask import url_for
from flask_testing import TestCase

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from config import CONFIG_FP

from app import app


class BehaviourTest(TestCase):
    """Base class for all behaviour tests."""

    STATIC_DIRPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'static')

    def setUp(self):
        """Instantiate a temporary directory and backup the config file. Serves as an init."""
        self.temp_file_count = 0
        self.temp_dir = None
        self.bk_config_fp = None

        self.tempdir = tempfile.mkdtemp()
        self.bk_config_fp = os.path.join(self.tempdir, 'initial.cfg_bk')
        shutil.copyfile(CONFIG_FP, self.bk_config_fp)

        self.temp_file_count = 0

        self.driver = webdriver.Chrome()

    def tearDown(self):
        """Restore the config file and destroy the temporary directory."""
        shutil.copyfile(self.bk_config_fp, CONFIG_FP)

        for root, _, filenames in os.walk(self.tempdir):
            for filename in filenames:
                os.remove(os.path.join(root, filename))

        shutil.rmtree(self.tempdir)

        self.driver.quit()

    def create_app(self):
        """Additional setup function needed for flask tests."""
        # So that form validation behaves as normally
        app.config['WTF_CSRF_ENABLED'] = False
        # So that the error catching does not prevent us from seeing exceptions
        app.config['TESTING'] = True

        return app

    @staticmethod
    def _get_form_data_as_dict(driver):
        """Get the form fields of a rendered page as a dict."""
        serial_str = driver.execute_script('return $("form").serialize()')

        ret_dict = {}
        serial_parts = serial_str.split('&')
        for part in serial_parts:
            eq_parts = part.split('=')
            ret_dict[eq_parts[0]] = eq_parts[1]

        return ret_dict

    def _create_temp_file(self):
        temp_fp = os.path.join(self.tempdir, str(self.temp_file_count) + '.temp')
        ftemp = open(temp_fp, 'w')
        ftemp.close()
        self.temp_file_count += 1
        return temp_fp

    def _open_page(self, page_str, wait_for_element_id=None):
        """Generate an html response from the flask server, open up the page in selenium.

        Assumes there is an active context.
        """
        response = self.client.get(url_for(page_str))

        temp_fp = self._create_temp_file()
        with open(temp_fp, 'wb') as temp_file:
            temp_file.write(response.data.replace(b'/static', self.STATIC_DIRPATH.encode()))

        self.driver.get("file:///" + temp_fp)
        if wait_for_element_id is not None:
            wait = WebDriverWait(self.driver, 10)
            wait.until(ec.visibility_of_element_located((By.ID, wait_for_element_id)))
