"""Sensor integration tests For TriCap. These tests do not instantiate a Flask WebServer."""

import unittest

from tests.test_trusense_altimeter import TestDeviceTruSense
from tests.test_canon6d_cam import TestDeviceCanon6DCam
#except ImportError:
#    print('Not testing GPhoto2 related testcases due to GPhoto2 not being installed.')


if __name__ == '__main__':
    unittest.main()
