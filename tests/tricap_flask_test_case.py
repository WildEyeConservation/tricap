"""Flask App and Behaviour for TriCap.

Important to note that this is not using a live server, (the LiveServerTestCase seems to be broken).
Lots of work arounds to accomodate this, and most importantly, these work arounds prevents testing
in Firefox, because Firefox stops you from loading local files directly (or something).
"""

import os

from .tricap_tempfile_test_case import TriCapTempFilerTestCase
from common_tests.flask_test_case import FlaskAppTestCase, FlaskBehaviourTestCase

from app import app


class TriCapAppTestCase(FlaskAppTestCase, TriCapTempFilerTestCase):
    """Base class for all behaviour tests."""

    def create_app(self):
        """Additional setup function needed for flask tests."""
        # So that form validation behaves as normally
        app.config['WTF_CSRF_ENABLED'] = False
        # So that the error catching does not prevent us from seeing exceptions
        app.config['TESTING'] = True

        return app


class TriCapBehaviourTestCase(FlaskBehaviourTestCase, TriCapAppTestCase):
    """Base class for all behaviour tests."""

    STATIC_DIRPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'static')

    def setUp(self):
        """Just set the static dirpath correctly."""
        super().setUp()
        self.static_dirpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'static')
