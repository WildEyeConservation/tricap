"""The LiveServer test case for TriCap."""

import os
import multiprocessing

from time import sleep

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

try:
    from pyvirtualdisplay import Display
    VIRTUAL_DISPLAY = True
except ImportError:
    VIRTUAL_DISPLAY = False

from .tricap_tempfile_test_case import TriCapTempFilerTestCase

def run_app():
    """External function to start the TriCap app."""
    from app import app
    app.run(use_reloader=False, debug=False)

class TriCapLiveServerTestCase(TriCapTempFilerTestCase):
    """Base class for all TriCap LiveServer Tests.

    Uses processes instead of threads to ensure separation between tests. This can be done
    because there is no shared database that needs to be updated before the test actually starts
    (as in ESSWeb and Skeye).
    """

    run_headless = True

    def setUp(self):
        self._process = multiprocessing.Process(target=run_app)
        self._all_drivers = []

        if VIRTUAL_DISPLAY:
            self.display = Display(visible=0, size=(800, 600))
            self.display.start()

        self.driver = self.create_driver()

    def tearDown(self):
        self._process.terminate()

        for driver in self._all_drivers:
            driver.quit()

        if VIRTUAL_DISPLAY:
            self.display.stop()

    def start_server(self):
        """Start the server in separate process."""
        self._process.start()
        # TODO Also, this sleep is necessary to give flask app a chance to start up. Should be a
        # better way to do this
        sleep(1)

    def stop_server(self):
        """Stop the server."""
        self._process.terminate()

    def create_driver(self):
        """Return a selenium chrome webdriver.

        If this is linux and Chromedriver is installed, the driver will be created using it.
        """
        driver = None

        chrome_options = Options()
        chrome_options.add_experimental_option('prefs', {
            'credentials_enable_service': False,
            'profile': {
                'password_manager_enabled': False
            }
        })
        chrome_options.add_argument("--start-maximized")

        if os.path.isfile('/usr/lib/chromium-browser/chromedriver'):
            driver = webdriver.Chrome("/usr/lib/chromium-browser/chromedriver",
                                      chrome_options=chrome_options)
        else:
            # add the windows option of running headlessly (need the latest chrome (59) and
            # chromedriver installed for this to work.)
            # chrome_options.binary_location = 'C:/Projects/System/chromedriver.exe'
            if self.run_headless:
                chrome_options.add_argument('headless')
            driver = webdriver.Chrome('C:/Projects/System/chromedriver.exe',
                                      chrome_options=chrome_options)

        self._all_drivers.append(driver)

        return driver

    @staticmethod
    def get_form_data_as_dict(driver):
        """Get the form fields of a rendered page as a dict."""
        serial_str = driver.execute_script('return $("form").serialize();')

        ret_dict = {}
        serial_parts = serial_str.split('&')
        for part in serial_parts:
            eq_parts = part.split('=')
            ret_dict[eq_parts[0]] = eq_parts[1]

        return ret_dict

    @staticmethod
    def get_server_url():
        """Return the url for the server."""
        return 'http://127.0.0.1:5000'

    def open_page(self, url, wait_for_element_id=None, driver=None):
        """Open up the page in selenium."""
        if driver is None:
            driver = self.driver

        driver.get(url)

        if wait_for_element_id is not None:
            wait = WebDriverWait(driver, 10)
            wait.until(ec.visibility_of_element_located((By.ID, wait_for_element_id)))

    def wait_for(self, element_id, driver=None):
        """Wait untill the element has been loaded."""
        if driver is None:
            driver = self.driver
        wait = WebDriverWait(driver, 10)
        wait.until(ec.visibility_of_element_located((By.ID, element_id)))

    def has_class(self, elem, class_name: str):
        """Check if the selenium element has the specified class."""
        class_str = elem.get_attribute('class')
        classes = class_str.split(' ')
        return class_name in classes
