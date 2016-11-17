""" D Joubert 16 November 2016 - Unit Tests For TriCap"""

import unittest

from tests.test_trusense_altimeter import TestDeviceTruSense
from tests.test_canon6d_cam import TestDeviceCanon6DCam
from tests.test_view_settings import TestViewSettings

DO_INTERACTIVE_TESTS = True

if DO_INTERACTIVE_TESTS is True:
    from tests.test_canon6d_cam import TestInteractiveCanon6DCam

if __name__ == '__main__':
    unittest.main()
