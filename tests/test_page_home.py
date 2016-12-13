"""Behaviour tests for the home page."""

from time import sleep

from .behaviour_test import BehaviourTest

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from app import app

from flask import url_for

from sensors.configure import TricapConfig


class TestBehaviourHome(BehaviourTest):
    """docstring for TestBehaviourHome."""

    def test_no_error_msg(self):
        """If no error messages have been logged, then the page should say so."""
        triconfig = TricapConfig()

        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        refresh_rate = web_settings['refresh_rate']
        web_settings['alti_required'] = 'dummy'
        web_settings['cams_required'] = 'dummy'
        triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
        triconfig.save_to_file()

        with self.client:  # access the web page through a 'client', as if a browser
            self._open_page('home.index', 'btn_startstop')
            # get the update info from the server
            response = self.client.get(url_for('home.provide_state_data'))

            self.assertEqual(len(response.json['sys']['msgs']), 0)

            json_str = str(response.json).replace('True', 'true').replace('False', 'false')
            self.driver.execute_script('return updatePage(data='+json_str+');')

            wait = WebDriverWait(self.driver, 5)
            wait.until(ec.visibility_of_element_located((By.ID, 'input_sys_msg0')))

            sys_msgs = self.driver.find_elements_by_css_selector('#alt_msgs_sys input')

            self.assertEqual(len(sys_msgs), 1)
            self.assertEqual(sys_msgs[0].get_attribute('value'), 'No errors to report')
