"""Flask App and Behaviour for TriCap.

Important to note that this is not using a live server, (the LiveServerTestCase seems to be broken).
Lots of work arounds to accomodate this, and most importantly, these work arounds prevents testing
in Firefox, because Firefox stops you from loading local files directly (or something).
"""

import os
import threading

from time import sleep

from urllib.request import urlopen
from urllib.error import URLError
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from common_tests.flask_test_case import FlaskAppTestCase, FlaskBehaviourTestCase
from .tricap_tempfile_test_case import TriCapTempFilerTestCase

from support.configure import TricapConfig
from app import app


class TriCapAppTestCase(FlaskAppTestCase, TriCapTempFilerTestCase):
    """Base class for all behaviour tests."""

    def _setup_dummies(self):
        triconfig = TricapConfig()

        web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        web_settings['alti_required'] = 'dummy'
        web_settings['cams_required'] = 'dummy'
        triconfig.set_section(web_settings, TricapConfig.WEB_SECTION_HEADER)
        triconfig.save_to_file()

    def create_app(self):
        """Additional setup function needed for flask tests."""
        # So that form validation behaves as normally
        app.config['WTF_CSRF_ENABLED'] = False
        # So that the error catching does not prevent us from seeing exceptions
        app.config['TESTING'] = True

        return app


class TriCapBehaviourTestCase(FlaskBehaviourTestCase, TriCapAppTestCase):
    """Base class for all behaviour tests.

    TO BE DEPRECATED SOMETIME IN THE FAR FUTURE."""

    STATIC_DIRPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'static')

    def setUp(self):
        """Just set the static dirpath correctly."""
        super().setUp()
        self.static_dirpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                             'app', 'static')


class TriCapLiveServerTestCase(FlaskBehaviourTestCase, TriCapAppTestCase):
    """Base class for all LiveServer Tests."""

    def setUp(self):
        """Set up for all tests - instantiate process control members to none."""
        self._process = None
        self._stop_event = False

        super().setUp()

    def tearDown(self):
        """Tear down for all tests - stop the server if it is running."""
        self.stop_server()

        super().tearDown()

    @staticmethod
    def run_app():
        """Run the app - to be called in the live server process."""
        app.run(debug=False, use_reloader=False)

    def app_controller(self):
        """External top level function for running the app.

        Needed for the multiprocessing to work.
        """
        athread = threading.Thread(target=self.run_app)
        athread.start()

        while not self._stop_event.is_set():
            sleep(1)

        try:
            urlopen('http://127.0.0.1:5000/_reset')
        except (ConnectionRefusedError, URLError):
            pass

        athread.join()

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
        """Wait until the element has been loaded."""
        if driver is None:
            driver = self.driver
        wait = WebDriverWait(driver, 10)
        wait.until(ec.visibility_of_element_located((By.ID, element_id)))

    def start_server(self):
        """Start the server in separate process."""
        self._stop_event = threading.Event()
        self._process = threading.Thread(target=self.app_controller)
        self._process.start()
        # TODO Also, this sleep is necessary to give flask app a chance to start up. Should be a
        # better way to do this
        sleep(1)

    def stop_server(self):
        """Stop the server."""
        if self._process and self._process.is_alive():
            self._stop_event.set()
            self._process.join()
