"""Behaviour tests for the home page."""

from time import sleep

from .behaviour_test_case import BehaviourTestCase, TriCapAppTestCase

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import json

from app import app, views, tricap_manager, altimeter, talkbox, session_logger

import unittest

from flask import url_for

from support.configure import TricapConfig

from config import CAMERA_STATES, CAM_MANAGER_STATES, ALTIMETER_STATE, BUTTON_CODE
from app.views.home import CAM_STATE_COLOURS, CAM_MAN_STATE_COLOURS, ALTI_STATE_COLOURS

from support.talkbox import TALK_REPLY


class TestHome(unittest.TestCase):
    """All non-behaviour tests for the home page."""

    def test_colour_state_matches(self):
        """Ensure that each state has an appropriate number of colours associated with it.

        Each colour state list has a dummy entry, so that the indices match up.
        """
        self.assertEqual(len(CAM_STATE_COLOURS), len(CAMERA_STATES)+1)
        self.assertEqual(len(CAM_MAN_STATE_COLOURS), len(CAM_MANAGER_STATES)+1)
        self.assertEqual(len(ALTI_STATE_COLOURS), len(ALTIMETER_STATE)+1)


class TestAppHome(TriCapAppTestCase):
    """TestAppHome."""

    def _setup_dummies(self):
        triconfig = TricapConfig()

        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        web_settings['alti_required'] = 'dummy'
        web_settings['cams_required'] = 'dummy'
        triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
        triconfig.save_to_file()

    def test_talkbox_messaging(self):
        '''Test talkbox message.'''
        self._setup_dummies()

        with self.client:
            self.client.get(url_for('home.index'))
            # response = self.client.get('/_submit_talkbox_msg?msg='+str('Test Message 1'),
            #                            content_type='application/json')
            self.send_ajax_request('/_submit_talkbox_msg', {'msg': 'Test Message 1'})

            msgs = [tmsg.msg for tmsg in talkbox.talk_msgs]
            self.assertEqual(msgs[0], 'Test Message 1')

            # response = self.client.get('/_change_message_reply?msg='+str('Test Message 1')+'&reply_code='+str(TALK_REPLY.YES.value),
            #                            content_type='application/json')
            self.send_ajax_request('/_change_message_reply', {'msg': 'Test Message 1',
                                                              'reply_code': str(TALK_REPLY.YES.value)})

            replies = [tmsg.reply for tmsg in talkbox.talk_msgs]
            self.assertEqual(replies[0], TALK_REPLY.YES)

    def test_button_presses(self):
        """Test that the button presses do what they should do."""
        self._setup_dummies()

        with self.client:  # access the web page through a 'client', as if a browser
            # open home page
            self.client.get(url_for('home.index'))

            # Start
            response = self.client.get('/_button_click?buttonCode='+str(BUTTON_CODE.START.value),
                                       content_type='application/json')

            self.assertEqual(tricap_manager.state == CAM_MANAGER_STATES.STARTED, True)
            self.assertEqual(altimeter.state == ALTIMETER_STATE.MEASURING, True)

            # Stop
            response = self.client.get('/_button_click?buttonCode='+str(BUTTON_CODE.STOP.value),
                                       content_type='application/json')

            self.assertEqual(tricap_manager.state == CAM_MANAGER_STATES.STARTED, False)
            self.assertEqual(altimeter.state == ALTIMETER_STATE.MEASURING, False)

            # StartStop
            response = self.client.get('/_button_click?buttonCode='+str(BUTTON_CODE.STARTSTOP.value),
                                       content_type='application/json')

            self.assertEqual(tricap_manager.state == CAM_MANAGER_STATES.STARTED, True)
            self.assertEqual(altimeter.state == ALTIMETER_STATE.MEASURING, True)

            # Stop
            response = self.client.get('/_button_click?buttonCode='+str(BUTTON_CODE.STARTSTOP.value),
                                       content_type='application/json')

            self.assertEqual(tricap_manager.state == CAM_MANAGER_STATES.STARTED, False)
            self.assertEqual(altimeter.state == ALTIMETER_STATE.MEASURING, False)


class TestBehaviourHome(BehaviourTestCase):
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
            self.open_page('home.index', 'btn_menu')
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

    def test_index_slash_redirection(self):
        """Test that the page opens when the url is only a slash."""
        with self.client:  # access the web page through a 'client', as if a browser
            self.open_page('home.index_slash', 'btn_menu')
            h_main_status = self.driver.find_element_by_id('h_main_status')
            self.assertEqual(h_main_status.get_attribute('innerHTML'), 'TriCap')

    def test_no_server_response(self):
        """Test that the home page shows an error message when the server does not respond."""
        # Make it so that the timeout_period is very short
        triconfig = TricapConfig()
        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        web_settings['timeout_period'] = '500'
        triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
        triconfig.save_to_file()

        with self.client:  # access the web page through a 'client', as if a browser
            self.open_page('home.index', 'btn_menu')

            sleep(1)

            alt_main_status = self.driver.find_element_by_id('alt_main_status')
            self.assertEqual(self.has_class(alt_main_status, 'alert-danger'), True)

            h_main_status = self.driver.find_element_by_id('h_main_status')
            self.assertEqual(h_main_status.get_attribute('innerHTML'), 'No Response From Server')

    def test_request_session_description_on_start(self):
        """Test that the user is requested to enter a session description on pressing start.

        But not when pressing stop. Also, the text box should be filled with a default description.
        """
        new_session_description = 'TEST1'

        triconfig = TricapConfig()
        misc_settings = triconfig.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
        default_session_description = misc_settings['session_description']

        with self.client:  # access the web page through a 'client', as if a browser
            self.open_page('home.index', 'btn_menu')

            # make the modal appear
            self.driver.find_element_by_css_selector('[name="btn_startstop"]').click()

            # wait for the modal to appear
            wait = WebDriverWait(self.driver, 5)
            wait.until(ec.visibility_of_element_located((By.ID, 'modal_session_description')))

            # check if default session description is correct
            modal_input = self.driver.find_element_by_css_selector('#input_modal_session_description')
            self.assertEqual(modal_input.get_property('value'), default_session_description)

            # clear input and send own values
            modal_input.clear()
            modal_input.send_keys(new_session_description)

            # make the modal go away
            self.driver.find_element_by_css_selector('#btn_modal_session_description_submit').click()

            # get the session description to actually change
            self.send_ajax_request('/_submit_session_description', {'sessionDescription': new_session_description})

            # start capture to create the session
            self.send_ajax_request('/_button_click', {'buttonCode': str(BUTTON_CODE.STARTSTOP.value)})
            self.assertEqual(session_logger.get_description(), new_session_description)
            # stop capture
            self.send_ajax_request('/_button_click', {'buttonCode': str(BUTTON_CODE.STARTSTOP.value)})

            # confirm the modal is not displayed
            modal = self.driver.find_element_by_css_selector('#modal_session_description')
            self.assertEqual(modal.is_displayed(), False)
