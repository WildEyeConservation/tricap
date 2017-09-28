from time import sleep
import logging
from support.log_list import LogListAccessor
from support.configure import TricapConfig
from app import altimeter

from .tricap_flask_live_server_test_case import TriCapLiveServerTestCase

class TestLiveServerHome(TriCapLiveServerTestCase):
    """Live server testing of the home page."""

    run_headless = False  # Without opening chrome
    _logger = logging.getLogger(__name__)

    def get_altitude(self):
        """Get the altitude from the page."""
        alti_str = self.driver.find_element_by_id('h_alti').get_attribute('innerHTML')
        return int(alti_str.split(' ')[1])

    def test_no_error_msg(self):
        """If no error messages have been logged, then the page should say so."""

        triconfig = TricapConfig()
        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        web_settings['alti_required'] = 'dummy'
        web_settings['cams_required'] = 'dummy'
        triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
        triconfig.save_to_file()

        self.start_server()
        # Get local server page and test for no error messages
        self.open_page(self.get_server_url(), wait_for_element_id='btn_startstop_m')

        sleep(5)  # Wait for 5 seconds

        sys_msgs = self.driver.find_elements_by_css_selector('#alt_msgs_sys input')
        self.assertEqual(len(sys_msgs), 1)
        self.assertEqual(sys_msgs[0].get_attribute('value'), 'No errors to report')

    def test_camera_msg(self):
        """If camera page is requested then one of two pages can be shown. Either camera detail or wait page is shown"""

        triconfig = TricapConfig()
        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        web_settings['alti_required'] = 'dummy'
        web_settings['cams_required'] = 'dummy'
        triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
        triconfig.save_to_file()

        self.start_server()
        # Get local server page and test for no error messages
        self.open_page(self.get_server_url(), wait_for_element_id='btn_startstop_m')

        self.driver.find_element_by_id('btn_menu').click()  # First click for manual start
        sleep(1)
        self.driver.find_element_by_id('a_check_camera').click()  # First click for manual start
        sleep(1)

        h_main_status = self.driver.find_element_by_id('h_camera_status')
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'Camera Rig Information')

        self.driver.find_element_by_id('home_cam').click()  # First click for manual start
        sleep(2)

        self.driver.find_element_by_name('btn_startstop').click()  # First click for manual start
        sleep(1)
        self.driver.find_element_by_id('btn_modal_session_description_submit').click()
        sleep(1)

        self.driver.find_element_by_id('btn_menu').click()  # First click for manual start
        sleep(1)
        self.driver.find_element_by_id('a_check_camera').click()  # First click for manual start
        sleep(1)

        h_main_status = self.driver.find_element_by_id('wait_mes')
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'Please wait until cameras has stopped capturing')

    def test_shutdown(self):
        """Test to see if shutdown is pressed and signal is received"""

        triconfig = TricapConfig()
        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        web_settings['alti_required'] = 'dummy'
        web_settings['cams_required'] = 'dummy'
        triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
        triconfig.save_to_file()

        self.start_server()
        # Get local server page and test for no error messages
        self.open_page(self.get_server_url(), wait_for_element_id='btn_startstop_m')

        self.driver.find_element_by_id('btn_menu').click()  #
        sleep(1)
        self.driver.find_element_by_id('a_shutdown').click()  #
        sleep(1)
        self.driver.find_element_by_id('confirm_shutdown').click()  #
        sleep(1)
        h_main_status = self.driver.find_element_by_id('shutdown')
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'Shutting down server')
    #
    # def test_error(self):
    #     """Test to see if shutdown is pressed and signal is received"""
    #     count = 0
    #     triconfig = TricapConfig()
    #     web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
    #     web_settings['alti_required'] = 'dummy'
    #     web_settings['cams_required'] = 'dummy'
    #     triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
    #     triconfig.save_to_file()
    #     self.start_server()
    #     # Get local server page and test for no error messages
    #     self.open_page(self.get_server_url(), wait_for_element_id='btn_startstop_m')
    #
    #     sleep(10)
    #     h_main_status = self.driver.find_element_by_id('h_alti_target')
    #     self.assertEqual(h_main_status.get_attribute('innerHTML'), 'Above altimeter range')

    def test_title(self):
        """Test the title and that it shows the correct name in all the states with button clicks"""

        triconfig = TricapConfig()  # Change settings in config for testing
        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        web_settings['alti_required'] = 'dummy'
        web_settings['cams_required'] = 'dummy'
        triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
        triconfig.save_to_file()

        self.start_server()  # Start the live server
        self.open_page(self.get_server_url(), wait_for_element_id='btn_startstop_m')

        h_main_status = self.driver.find_element_by_id('h_main_status')
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'TriCap')

        sleep(2)
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'TriCap Automatic: NOT capturing')

        self.driver.find_element_by_name('btn_startstop').click()  # First click for manual start
        sleep(1)
        self.driver.find_element_by_id('btn_modal_session_description_submit').click()
        sleep(1)
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'TriCap Manual: Capturing')

        self.driver.find_element_by_name('btn_startstop').click()  # Stop manual start
        sleep(1)
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'TriCap: NOT capturing')

        self.driver.find_element_by_name('btn_startstop').click()  # Start automatic switching
        sleep(2)
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'TriCap Automatic: NOT capturing')

        while self.get_altitude() <= 150:
            sleep(1)
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'TriCap Automatic: Capturing')

        sleep(1)
        self.driver.find_element_by_name('btn_startstop').click()  # Stop automatic start
        sleep(1)
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'TriCap: NOT capturing')

    def test_start_stop_button_title(self):
        """Test the start/stop button to have the correct title at the correct state"""

        triconfig = TricapConfig()  # Change settings in config for testing
        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        web_settings['alti_required'] = 'dummy'
        web_settings['cams_required'] = 'dummy'
        triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
        triconfig.save_to_file()

        self.start_server()  # Start the live server
        self.open_page(self.get_server_url(), wait_for_element_id='btn_startstop_m')

        btn_startstop_m = self.driver.find_element_by_id('btn_startstop_m')
        self.assertEqual(btn_startstop_m.get_attribute('innerHTML'), 'Start Manual')

        sleep(2)
        self.assertEqual(btn_startstop_m.get_attribute('innerHTML'), 'Start Manual')

        self.driver.find_element_by_name('btn_startstop').click()  # First click for manual start
        sleep(1)
        self.driver.find_element_by_id('btn_modal_session_description_submit').click()
        sleep(1)
        self.assertEqual(btn_startstop_m.get_attribute('innerHTML'), 'Stop')

        self.driver.find_element_by_name('btn_startstop').click()  # Stop manual start
        sleep(1)
        self.assertEqual(btn_startstop_m.get_attribute('innerHTML'), 'Start Auto')

        self.driver.find_element_by_name('btn_startstop').click()  # Start automatic switching
        sleep(2)
        self.assertEqual(btn_startstop_m.get_attribute('innerHTML'), 'Start Manual')

        while self.get_altitude() <= 150:
            sleep(1)
        self.assertEqual(btn_startstop_m.get_attribute('innerHTML'), 'Stop')

        sleep(1)
        self.driver.find_element_by_name('btn_startstop').click()  # Stop automatic start
        sleep(1)
        self.assertEqual(btn_startstop_m.get_attribute('innerHTML'), 'Start Auto')
