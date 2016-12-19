"""Base class for all behaviour tests. Instantiates an app."""

import os

from flask import url_for
from flask_testing import TestCase as FlaskTestCase, LiveServerTestCase

from .tempfile_test_case import TricapTempFilerTestCase

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from app import app


class AppTestCase(FlaskTestCase, TricapTempFilerTestCase):
    """Base class for all behaviour tests."""

    def create_app(self):
        """Additional setup function needed for flask tests."""
        # So that form validation behaves as normally
        app.config['WTF_CSRF_ENABLED'] = False
        # So that the error catching does not prevent us from seeing exceptions
        app.config['TESTING'] = True

        return app

    def send_ajax_request(self, ajax_url: str, args=None):
        """Send a correctly formatted ajax request to the app server."""
        if args is None:
            return self.client.get(ajax_url, content_type='application/json')

        args_str = None
        for index, key in enumerate(args.keys()):
            if index == 0:
                args_str = '?'+key+'='+args[key]
            else:
                args_str += '&'+key+'='+args[key]

        return self.client.get(ajax_url+args_str, content_type='application/json')


class BehaviourTestCase(AppTestCase):
    """Base class for all behaviour tests."""

    STATIC_DIRPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'static')

    def setUp(self):
        """Instantiate a temporary directory and backup the config file and start the webdriver."""
        super().setUp()
        self.driver = webdriver.Chrome()

    def tearDown(self):
        """Restore the config file and destroy the temporary directory and the webdriver."""
        super().tearDown()

        self.driver.quit()

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

    def has_class(self, elem, class_name: str):
        """Check if the selenium element has the specified class."""
        class_str = elem.get_attribute('class')
        classes = class_str.split(' ')
        return class_name in classes
