from time import sleep

from support.configure import TricapConfig

from .tricap_flask_live_server_test_case import TriCapLiveServerTestCase

class TestLiveServerCamera(TriCapLiveServerTestCase):
    """Live server testing of the camera page."""

    run_headless = False  # Without opening chrome

    def get_camera_url(self):
        return 'http://127.0.0.1:5000/camera'

    def test_camera_buttons(self):
        """Test the functionality of the buttons"""

        triconfig = TricapConfig()
        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        web_settings['alti_required'] = 'dummy'
        web_settings['cams_required'] = 'dummy'
        triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
        triconfig.save_to_file()

        self.start_server()
        self.open_page(self.get_camera_url(), wait_for_element_id='rig_info')
        sleep(1)
        h_main_status = self.driver.find_element_by_id('h_camera_status')
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'Camera Rig Information')

        self.driver.find_element_by_id('refresh').click()  # First click for manual start
        sleep(2)
        h_main_status = self.driver.find_element_by_id('h_camera_status')
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'Camera Rig Information')

        self.driver.find_element_by_id('home_cam').click()  # First click for manual start
        sleep(2)
        h_main_status = self.driver.find_element_by_id('btn_startstop_m')
        self.assertEqual(h_main_status.get_attribute('innerHTML'), 'Start Manual')

    def test_state_of_cameras(self):
        """Test if the cameras are in the correct state with regard to the information given"""

        triconfig = TricapConfig()
        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        web_settings['alti_required'] = 'dummy'
        web_settings['cams_required'] = 'dummy'
        triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
        triconfig.save_to_file()

        self.start_server()
        # Get local server page and test for no error messages
        self.open_page(self.get_camera_url(), wait_for_element_id='rig_info')
        sleep(1)
        cam = self.driver.find_elements_by_id('middle_camera')
        self.assertEqual(cam[0].get_attribute('class'), 'alert alert-info')

        cam = self.driver.find_elements_by_id('front_camera')
        self.assertEqual(cam[0].get_attribute('class'), 'alert alert-info')

        cam = self.driver.find_elements_by_id('back_camera')
        self.assertEqual(cam[0].get_attribute('class'), 'alert alert-danger')
