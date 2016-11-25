""" D Joubert 16 November 2016 - Unit Tests for tricap.
    These tests instantiate a flask instant of the app, i.e. the webserver is started.
    Typically, these tests are more integration and behaviour tests.
"""

import unittest

from tests.test_settings import TestSettings

DO_BEHAVIOUR_TESTS = True

if DO_BEHAVIOUR_TESTS is True:
    from tests.test_settings import TestBehaviourSettings

if __name__ == '__main__':
    unittest.main()
